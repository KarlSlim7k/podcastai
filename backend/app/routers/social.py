"""Social media publishing router (Phase 12).

Endpoints:
  GET    /api/v1/social/status                          -> connection status of all 3 platforms
  GET    /api/v1/social/{platform}/auth                -> start OAuth flow
  GET    /api/v1/social/{platform}/callback            -> OAuth callback (after user authorizes)
  POST   /api/v1/social/{platform}/disconnect          -> remove the connected account
  POST   /api/v1/social/{platform}/publish             -> publish a vertical render
  GET    /api/v1/social/{project_id}/publications      -> list past publications for a project
"""
import json
import secrets
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.project import (
    SocialAccount, SocialPublication, VerticalRender, Clip,
)
from app.models.schemas import (
    SocialStatusResponse, SocialPlatformInfo,
    SocialPublishRequest, SocialPublishResponse,
    SocialPublicationOut, SocialPublicationListResponse,
    MessageResponse,
)
from app.services.social_publisher import (
    get_publisher_for_platform, is_platform_configured,
    PublishRequest as SPRequest, PLATFORMS, PLATFORM_LABELS, PLATFORM_ICONS,
    OAuthCredentials, PublishStatus,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/social", tags=["social"])


# ── Helpers ────────────────────────────────────────────────────────────────

def _platform_to_creds(account: SocialAccount) -> OAuthCredentials:
    """Convert a DB row to the in-memory OAuthCredentials used by publishers."""
    return OAuthCredentials(
        platform=account.platform,  # type: ignore
        access_token=account.access_token,
        refresh_token=account.refresh_token,
        expires_at=account.expires_at,
        open_id=account.open_id,
        account_handle=account.account_handle,
        scope=account.scope,
    )


async def _get_account(db: AsyncSession, platform: str) -> SocialAccount | None:
    r = await db.execute(
        select(SocialAccount).where(SocialAccount.platform == platform)
    )
    return r.scalar_one_or_none()


async def _build_status_for_platform(
    db: AsyncSession, platform: str
) -> SocialPlatformInfo:
    account = await _get_account(db, platform)
    return SocialPlatformInfo(
        platform=platform,
        label=PLATFORM_LABELS[platform],
        icon=PLATFORM_ICONS[platform],
        configured=is_platform_configured(platform),  # type: ignore
        connected=account is not None,
        account_handle=account.account_handle if account else None,
        is_mock_account=bool(account.is_mock) if account else False,
    )


# ── Status ────────────────────────────────────────────────────────────────

@router.get("/status", response_model=SocialStatusResponse)
async def get_social_status(db: AsyncSession = Depends(get_db)):
    """Return connection status for all 3 platforms.

    Used by the UI to show which platforms are available and whether
    the user has connected each one.
    """
    platforms: list[SocialPlatformInfo] = []
    for p in PLATFORMS:
        platforms.append(await _build_status_for_platform(db, p))
    return SocialStatusResponse(platforms=platforms)


# ── OAuth flow ────────────────────────────────────────────────────────────

@router.get("/{platform}/auth")
async def start_oauth(
    platform: str,
    redirect: str | None = Query(None, description="Optional front-end URL to redirect to after callback"),
):
    """Start the OAuth flow for the given platform.

    The user is redirected to the platform's authorization page. After
    they grant access, the platform redirects them back to our callback
    URL with an authorization code.

    For MOCK mode (no real credentials), the user is redirected directly
    to our own callback with a mock code, so the flow can be tested
    end-to-end without a real platform account.
    """
    if platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")
    publisher = get_publisher_for_platform(platform)  # type: ignore
    state = secrets.token_urlsafe(16)
    callback_uri = f"{settings.oauth_redirect_base}/api/v1/social/{platform}/callback"
    if redirect:
        # Encode the front-end redirect in the state for use in callback
        state = f"{state}|{redirect}"
    auth_url = publisher.get_authorize_url(callback_uri, state)
    logger.info("social_oauth_start", platform=platform, mock=not is_platform_configured(platform))  # type: ignore
    return RedirectResponse(url=auth_url)


@router.get("/{platform}/callback")
async def oauth_callback(
    platform: str,
    code: str = Query(...),
    state: str = Query(""),
    mock: str | None = Query(None, description="Set to '1' by the mock provider to skip real OAuth"),
    db: AsyncSession = Depends(get_db),
):
    """OAuth callback handler.

    Called by the platform (or the mock publisher) with an auth code.
    Exchanges the code for tokens, stores them in the DB, and
    redirects the user back to the front-end.
    """
    if platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")
    publisher = get_publisher_for_platform(platform)  # type: ignore
    callback_uri = f"{settings.oauth_redirect_base}/api/v1/social/{platform}/callback"
    try:
        creds = await publisher.exchange_code_for_token(code, callback_uri)
    except Exception as e:
        logger.error("social_oauth_exchange_failed", platform=platform, error=str(e))
        raise HTTPException(status_code=400, detail=f"OAuth exchange failed: {e}")
    # Persist
    existing = await _get_account(db, platform)
    if existing:
        existing.access_token = creds.access_token
        existing.refresh_token = creds.refresh_token
        existing.expires_at = creds.expires_at
        existing.open_id = creds.open_id
        existing.account_handle = creds.account_handle
        existing.scope = creds.scope
        existing.is_mock = 1 if mock == "1" else 0
        existing.connected_at = datetime.utcnow()
    else:
        db.add(SocialAccount(
            platform=platform,
            access_token=creds.access_token,
            refresh_token=creds.refresh_token,
            expires_at=creds.expires_at,
            open_id=creds.open_id,
            account_handle=creds.account_handle,
            scope=creds.scope,
            is_mock=1 if mock == "1" else 0,
        ))
    await db.commit()
    logger.info("social_account_connected", platform=platform, handle=creds.account_handle, mock=mock)
    # Redirect back to the front-end
    # Recover the user-supplied redirect from the state (if any)
    front_end_redirect = "/"
    if "|" in state:
        front_end_redirect = state.split("|", 1)[1]
    return RedirectResponse(
        url=f"http://localhost:5173{front_end_redirect}?social_connected={platform}"
    )


@router.post("/{platform}/disconnect", response_model=MessageResponse)
async def disconnect(
    platform: str, db: AsyncSession = Depends(get_db)
):
    """Remove the connected account for the given platform."""
    if platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")
    account = await _get_account(db, platform)
    if not account:
        raise HTTPException(status_code=404, detail=f"No {platform} account connected")
    await db.delete(account)
    await db.commit()
    logger.info("social_account_disconnected", platform=platform)
    return MessageResponse(message=f"{platform} account disconnected")


# ── Publish ───────────────────────────────────────────────────────────────

@router.post("/{platform}/publish", response_model=SocialPublishResponse)
async def publish_to_platform(
    platform: str,
    request: SocialPublishRequest,
    db: AsyncSession = Depends(get_db),
):
    """Publish a vertical render to the given platform.

    Flow:
      1. Look up the connected account (and refresh the token if needed)
      2. Look up the vertical render in the DB
      3. Call the publisher (real or mock)
      4. Log the result to ``social_publications``
    """
    if platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")
    # 1. Get the account
    account = await _get_account(db, platform)
    if not account:
        raise HTTPException(
            status_code=400,
            detail=f"No {platform} account connected. Visit /api/v1/social/{platform}/auth first.",
        )
    # Refresh the token if it's about to expire (within 5 min)
    creds = _platform_to_creds(account)
    if creds.expires_at and creds.expires_at - time.time() < 300 and creds.refresh_token:
        try:
            publisher = get_publisher_for_platform(platform)  # type: ignore
            creds = await publisher.refresh_access_token(creds)
            account.access_token = creds.access_token
            account.expires_at = creds.expires_at
            await db.commit()
        except Exception as e:
            logger.warning("social_token_refresh_failed", platform=platform, error=str(e))
    # 2. Look up the render
    r = await db.execute(
        select(VerticalRender).where(VerticalRender.id == request.vertical_render_id)
    )
    render = r.scalar_one_or_none()
    if not render:
        raise HTTPException(status_code=404, detail="Vertical render not found")
    if not render.output_path or not Path(render.output_path).exists():
        raise HTTPException(status_code=400, detail="Render has no output file yet")
    # 3. Create the publication log entry (status=pending)
    pub = SocialPublication(
        project_id=render.project_id,
        clip_id=render.clip_id,
        vertical_render_id=render.id,
        platform=platform,
        title=request.title,
        description=request.description,
        hashtags_json=json.dumps(request.hashtags),
        status="pending",
        is_mock=account.is_mock,
    )
    db.add(pub)
    await db.commit()
    await db.refresh(pub)
    # 4. Call the publisher
    publisher = get_publisher_for_platform(platform)  # type: ignore
    sp_req = SPRequest(
        platform=platform,  # type: ignore
        video_path=Path(render.output_path),
        title=request.title,
        description=request.description,
        hashtags=request.hashtags,
    )
    try:
        result = await publisher.publish(creds, sp_req)
    except Exception as e:
        result = None
        logger.error("social_publish_exception", platform=platform, error=str(e))
        pub.status = "failed"
        pub.error_message = str(e)[:1000]
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Publish failed: {e}")
    # 5. Update the publication log
    if result is None:
        pub.status = "failed"
        pub.error_message = "Publisher returned no result"
    elif result.status == PublishStatus.PUBLISHED:
        pub.status = "published"
        pub.post_id = result.post_id
        pub.post_url = result.post_url
        pub.published_at = datetime.utcnow()
        account.last_used_at = datetime.utcnow()
    else:
        pub.status = "failed"
        pub.error_message = result.error_message
    await db.commit()
    await db.refresh(pub)
    return SocialPublishResponse(
        success=pub.status == "published",
        publication_id=pub.id,
        platform=platform,
        post_id=pub.post_id,
        post_url=pub.post_url,
        status=pub.status,
        error_message=pub.error_message,
        is_mock=bool(pub.is_mock),
    )


# ── Publication history ───────────────────────────────────────────────────

@router.get(
    "/{project_id}/publications",
    response_model=SocialPublicationListResponse,
)
async def list_publications(
    project_id: int,
    platform: str | None = Query(None, description="Filter by platform"),
    db: AsyncSession = Depends(get_db),
):
    """List past publish attempts for a project (most recent first)."""
    stmt = select(SocialPublication).where(SocialPublication.project_id == project_id)
    if platform:
        stmt = stmt.where(SocialPublication.platform == platform)
    stmt = stmt.order_by(SocialPublication.created_at.desc()).limit(100)
    r = await db.execute(stmt)
    pubs = r.scalars().all()
    return SocialPublicationListResponse(
        publications=[
            SocialPublicationOut(
                id=p.id,
                platform=p.platform,
                title=p.title,
                status=p.status,
                post_id=p.post_id,
                post_url=p.post_url,
                is_mock=bool(p.is_mock),
                error_message=p.error_message,
                created_at=p.created_at,
                published_at=p.published_at,
            )
            for p in pubs
        ]
    )
