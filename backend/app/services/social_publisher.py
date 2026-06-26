"""Social media publishing service.

Publishes rendered vertical videos to TikTok, YouTube Shorts, and
Instagram Reels. Each platform has its own OAuth flow and upload API;
this module wraps them in a single ``SocialPublisher`` interface so the
rest of the app stays platform-agnostic.

## How it works

  1. The user connects an account via OAuth (one-time, per platform)
     - The OAuth flow is implemented in the router layer
     - The resulting access/refresh tokens are stored in ``social_accounts``
  2. When the user clicks "Publish", we look up the token, refresh if
     needed, and call the platform's upload API
  3. We log every publish attempt to ``social_publications`` (with
     status: success / failed / pending) so the user can see history

## Modes

  - ``MOCK`` (default if no credentials): simulates the full flow with
    a fake success after 2 seconds. Useful for demos and UI dev.
  - ``REAL``: calls the actual platform API. Requires OAuth credentials
    in the .env (see below).

## Credentials needed (per platform)

  - TikTok: TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET
            (https://developers.tiktok.com/apps/)
  - YouTube: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET
            (https://console.cloud.google.com/apis/credentials)
  - Instagram: INSTAGRAM_APP_ID, INSTAGRAM_APP_SECRET
              (https://developers.facebook.com/apps/)
"""
from __future__ import annotations

import asyncio
import json
import secrets
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Literal

import httpx

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ── Types ─────────────────────────────────────────────────────────────────

Platform = Literal["tiktok", "youtube", "instagram"]
PLATFORMS: list[Platform] = ["tiktok", "youtube", "instagram"]

PLATFORM_LABELS = {
    "tiktok": "TikTok",
    "youtube": "YouTube Shorts",
    "instagram": "Instagram Reels",
}

PLATFORM_ICONS = {
    "tiktok": "🎵",
    "youtube": "▶️",
    "instagram": "📸",
}


class PublishStatus(str, Enum):
    """Status of a single publish attempt."""
    PENDING = "pending"
    UPLOADING = "uploading"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass
class OAuthCredentials:
    """OAuth tokens for a connected social account."""
    platform: Platform
    access_token: str
    refresh_token: str | None = None
    expires_at: float = 0.0                # unix timestamp; 0 = never
    open_id: str | None = None            # platform-specific user id
    account_handle: str | None = None     # @username or channel name
    scope: str | None = None


@dataclass
class PublishRequest:
    """What to publish."""
    platform: Platform
    video_path: Path
    title: str
    description: str
    hashtags: list[str] = field(default_factory=list)
    # Optional: publish_at — ISO 8601 timestamp for scheduled posts
    publish_at: str | None = None


@dataclass
class PublishResult:
    """The result of a publish attempt."""
    platform: Platform
    status: PublishStatus
    post_id: str | None = None           # platform's post/video id
    post_url: str | None = None          # public URL of the post
    error_message: str | None = None
    is_mock: bool = False                # True if MOCK provider was used

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "status": self.status.value,
            "platform": str(self.platform),
        }


# ── Abstract base ─────────────────────────────────────────────────────────

class SocialPublisher(ABC):
    """Base class for all platform publishers."""

    platform: Platform

    @abstractmethod
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> OAuthCredentials:
        """Exchange the OAuth authorization code for access/refresh tokens."""

    @abstractmethod
    async def refresh_access_token(self, creds: OAuthCredentials) -> OAuthCredentials:
        """Refresh the access token if it's about to expire."""

    @abstractmethod
    async def publish(self, creds: OAuthCredentials, req: PublishRequest) -> PublishResult:
        """Upload the video and publish it. Returns a PublishResult."""

    @abstractmethod
    def get_authorize_url(self, redirect_uri: str, state: str) -> str:
        """Return the URL the user should visit to authorize this app."""


# ── Mock publisher (for dev/demos) ───────────────────────────────────────

class MockPublisher(SocialPublisher):
    """Fake publisher that simulates the full flow.

    Use this when:
      - The user has not configured real OAuth credentials
      - The user wants to demo the UI without burning real quota
      - Tests are running in CI

    It returns a fake success after a 2-second sleep.
    """

    platform: Platform = "tiktok"  # overridden in factory

    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> OAuthCredentials:
        await asyncio.sleep(0.5)
        return OAuthCredentials(
            platform=self.platform,
            access_token=f"mock_access_{secrets.token_hex(8)}",
            refresh_token=f"mock_refresh_{secrets.token_hex(8)}",
            expires_at=time.time() + 3600,
            open_id=f"mock_user_{secrets.token_hex(4)}",
            account_handle=f"@mock_user_{secrets.token_hex(2)}",
            scope="mock.full",
        )

    async def refresh_access_token(self, creds: OAuthCredentials) -> OAuthCredentials:
        await asyncio.sleep(0.1)
        creds.access_token = f"mock_access_{secrets.token_hex(8)}"
        creds.expires_at = time.time() + 3600
        return creds

    async def publish(self, creds: OAuthCredentials, req: PublishRequest) -> PublishResult:
        logger.info("mock_publish_start", platform=req.platform, file=req.video_path.name)
        # Simulate upload progress
        for pct in (0, 25, 50, 75, 100):
            await asyncio.sleep(0.4)
            logger.info("mock_publish_progress", platform=req.platform, pct=pct)
        # Verify the file exists (real check, just no upload)
        if not req.video_path.exists():
            return PublishResult(
                platform=req.platform,
                status=PublishStatus.FAILED,
                error_message=f"Video file not found: {req.video_path}",
                is_mock=True,
            )
        post_id = f"mock_{secrets.token_hex(8)}"
        return PublishResult(
            platform=req.platform,
            status=PublishStatus.PUBLISHED,
            post_id=post_id,
            post_url=f"https://{req.platform}.com/mock/{post_id}",
            is_mock=True,
        )

    def get_authorize_url(self, redirect_uri: str, state: str) -> str:
        # Point to our own /callback endpoint with a flag that says "mock"
        # The router detects this and skips the real OAuth dance.
        return (
            f"/api/v1/social/{self.platform}/callback"
            f"?code=mock_auth_code&state={state}&redirect_uri={redirect_uri}&mock=1"
        )


# ── Real publishers (stubs that work when credentials are configured) ───
#
# Each one implements the OAuth + upload flow per the platform's docs.
# They are not "complete" because each platform has subtle variations
# (chunked upload, file size limits, content policies, etc.) that need
# real-world testing. The structure here is correct; the integration
# details are documented inline.
#
# To enable a real provider, set the corresponding env vars in .env
# and uncomment the relevant code path in ``get_publisher_for_platform``.


class TikTokPublisher(SocialPublisher):
    """Real TikTok publisher (Content Posting API v2.0).

    Requires:
      - TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET in .env
      - App registered at https://developers.tiktok.com/apps/
      - Approved scopes: user.info.basic, video.publish, video.upload

    Flow:
      1. User authorizes at TikTok → we get an auth code
      2. POST to /v2/oauth/token/ to exchange code for access_token
      3. POST to /v2/post/publish/video/init/ to get an upload URL
      4. PUT the video file to the upload URL (chunked for >5MB)
      5. POST to /v2/post/publish/status/fetch/ to check status
    """

    platform: Platform = "tiktok"

    def __init__(self, client_key: str, client_secret: str):
        self.client_key = client_key
        self.client_secret = client_secret
        self.base_url = "https://open.tiktokapis.com"

    def get_authorize_url(self, redirect_uri: str, state: str) -> str:
        return (
            f"https://www.tiktok.com/v2/auth/authorize/"
            f"?client_key={self.client_key}"
            f"&scope=user.info.basic,video.publish,video.upload"
            f"&response_type=code"
            f"&redirect_uri={redirect_uri}"
            f"&state={state}"
        )

    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> OAuthCredentials:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.base_url}/v2/oauth/token/",
                json={
                    "client_key": self.client_key,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
            r.raise_for_status()
            data = r.json()
            access = data["access_token"]
            refresh = data.get("refresh_token", "")
            open_id = data.get("open_id", "")
            expires_in = data.get("expires_in", 3600)
            # Fetch user info for the handle
            handle = await self._fetch_user_handle(client, access, open_id)
            return OAuthCredentials(
                platform="tiktok",
                access_token=access,
                refresh_token=refresh,
                expires_at=time.time() + expires_in,
                open_id=open_id,
                account_handle=handle,
                scope=data.get("scope", ""),
            )

    async def _fetch_user_handle(self, client: httpx.AsyncClient,
                                  access_token: str, open_id: str) -> str | None:
        try:
            r = await client.get(
                f"{self.base_url}/v2/user/info/",
                params={"fields": "display_name,username"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if r.status_code == 200:
                data = r.json().get("data", {}).get("user", {})
                return f"@{data.get('username', open_id)}"
        except Exception:
            pass
        return None

    async def refresh_access_token(self, creds: OAuthCredentials) -> OAuthCredentials:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.base_url}/v2/oauth/token/",
                json={
                    "client_key": self.client_key,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": creds.refresh_token,
                },
            )
            r.raise_for_status()
            data = r.json()
            creds.access_token = data["access_token"]
            creds.refresh_token = data.get("refresh_token", creds.refresh_token)
            creds.expires_at = time.time() + data.get("expires_in", 3600)
            return creds

    async def publish(self, creds: OAuthCredentials, req: PublishRequest) -> PublishResult:
        async with httpx.AsyncClient(timeout=300.0) as client:
            # 1. Initialize the upload — get a presigned PUT URL
            init_r = await client.post(
                f"{self.base_url}/v2/post/publish/video/init/",
                headers={"Authorization": f"Bearer {creds.access_token}"},
                json={
                    "post_info": {
                        "title": req.title,
                        "description": req.description,
                        "privacy_level": "PUBLIC_TO_EVERYONE",
                    },
                    "source_info": {
                        "source": "FILE_UPLOAD",
                        "video_size": req.video_path.stat().st_size,
                        "chunk_size": req.video_path.stat().st_size,  # single PUT
                        "total_chunk_count": 1,
                    },
                },
            )
            init_r.raise_for_status()
            upload_url = init_r.json()["data"]["upload_url"]
            publish_id = init_r.json()["data"]["publish_id"]

            # 2. PUT the video file
            with open(req.video_path, "rb") as f:
                put_r = await client.put(
                    upload_url,
                    content=f.read(),
                    headers={"Content-Type": "video/mp4"},
                    timeout=300.0,
                )
            put_r.raise_for_status()

            # 3. Poll for publish status
            for _ in range(20):
                await asyncio.sleep(3)
                status_r = await client.post(
                    f"{self.base_url}/v2/post/publish/status/fetch/",
                    headers={"Authorization": f"Bearer {creds.access_token}"},
                    json={"publish_id": publish_id},
                )
                if status_r.status_code == 200:
                    status_data = status_r.json().get("data", {})
                    if status_data.get("status") == "PUBLISH_COMPLETE":
                        return PublishResult(
                            platform="tiktok",
                            status=PublishStatus.PUBLISHED,
                            post_id=publish_id,
                            post_url=f"https://www.tiktok.com/@{creds.account_handle}/video/{publish_id}",
                        )
                    if status_data.get("status") == "PUBLISH_FAILED":
                        return PublishResult(
                            platform="tiktok",
                            status=PublishStatus.FAILED,
                            error_message=status_data.get("fail_reason", "Unknown error"),
                        )

            return PublishResult(
                platform="tiktok",
                status=PublishStatus.FAILED,
                error_message="Timeout waiting for publish to complete",
            )


class YouTubePublisher(SocialPublisher):
    """Real YouTube Shorts publisher (YouTube Data API v3).

    Requires:
      - YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET in .env
      - App at https://console.cloud.google.com/apis/credentials
      - YouTube Data API v3 enabled
      - OAuth scope: https://www.googleapis.com/auth/youtube.upload

    Flow:
      1. User authorizes at Google → we get an auth code
      2. POST to https://oauth2.googleapis.com/token to exchange
      3. Resumable upload of the MP4 to
         https://www.googleapis.com/upload/youtube/v3/videos
      4. Set the snippet.title and snippet.description (and #Shorts)
    """

    platform: Platform = "youtube"

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.upload_url = "https://www.googleapis.com/upload/youtube/v3/videos"

    def get_authorize_url(self, redirect_uri: str, state: str) -> str:
        return (
            "https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={self.client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&scope=https://www.googleapis.com/auth/youtube.upload"
            f"&access_type=offline"
            f"&state={state}"
            f"&include_granted_scopes=true"
            f"&prompt=consent"
        )

    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> OAuthCredentials:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
            r.raise_for_status()
            data = r.json()
            access = data["access_token"]
            refresh = data.get("refresh_token", "")
            expires_in = data.get("expires_in", 3600)
            handle = await self._fetch_channel_info(client, access)
            return OAuthCredentials(
                platform="youtube",
                access_token=access,
                refresh_token=refresh,
                expires_at=time.time() + expires_in,
                account_handle=handle,
                scope="youtube.upload",
            )

    async def _fetch_channel_info(self, client: httpx.AsyncClient,
                                   access_token: str) -> str | None:
        try:
            r = await client.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "snippet", "mine": "true"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if r.status_code == 200:
                items = r.json().get("items", [])
                if items:
                    return f"@{items[0]['snippet']['title']}"
        except Exception:
            pass
        return None

    async def refresh_access_token(self, creds: OAuthCredentials) -> OAuthCredentials:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": creds.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            r.raise_for_status()
            data = r.json()
            creds.access_token = data["access_token"]
            creds.expires_at = time.time() + data.get("expires_in", 3600)
            return creds

    async def publish(self, creds: OAuthCredentials, req: PublishRequest) -> PublishResult:
        # 1. Initialize the resumable upload
        title = req.title if len(req.title) <= 100 else req.title[:97] + "..."
        description = req.description
        if req.hashtags:
            description += "\n\n" + " ".join(req.hashtags)
        if "#Shorts" not in description:
            description += " #Shorts"
        metadata = {
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": "22",  # People & Blogs
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }
        async with httpx.AsyncClient(timeout=600.0) as client:
            init_r = await client.post(
                f"{self.upload_url}?uploadType=resumable&part=snippet,status",
                headers={
                    "Authorization": f"Bearer {creds.access_token}",
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Type": "video/mp4",
                    "X-Upload-Content-Length": str(req.video_path.stat().st_size),
                },
                json=metadata,
            )
            init_r.raise_for_status()
            upload_url = init_r.headers["Location"]

            # 2. Upload the video
            with open(req.video_path, "rb") as f:
                put_r = await client.put(
                    upload_url,
                    content=f.read(),
                    headers={"Content-Type": "video/mp4"},
                    timeout=600.0,
                )
            put_r.raise_for_status()
            video_id = put_r.json()["id"]
            return PublishResult(
                platform="youtube",
                status=PublishStatus.PUBLISHED,
                post_id=video_id,
                post_url=f"https://youtube.com/shorts/{video_id}",
            )


class InstagramPublisher(SocialPublisher):
    """Real Instagram Reels publisher (Graph API v18+).

    Requires:
      - INSTAGRAM_APP_ID, INSTAGRAM_APP_SECRET in .env
      - A Facebook Page connected to an Instagram Business account
      - App at https://developers.facebook.com/apps/
      - Approved scopes: instagram_basic, instagram_content_publish,
        pages_show_list, pages_read_engagement

    Flow:
      1. User authorizes at Facebook → we get an auth code
      2. Exchange for access_token
      3. POST to /{ig-user-id}/media with media_type=REELS, video_url
         → returns an "upload container" id
      4. POST to /{ig-user-id}/media_publish with the container id
         → returns the published post id
    """

    platform: Platform = "instagram"

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.graph_url = "https://graph.facebook.com/v18.0"

    def get_authorize_url(self, redirect_uri: str, state: str) -> str:
        return (
            f"https://www.facebook.com/v18.0/dialog/oauth"
            f"?client_id={self.app_id}"
            f"&redirect_uri={redirect_uri}"
            f"&state={state}"
            f"&scope=instagram_basic,instagram_content_publish,pages_show_list"
        )

    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> OAuthCredentials:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{self.graph_url}/oauth/access_token",
                params={
                    "client_id": self.app_id,
                    "client_secret": self.app_secret,
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
            )
            r.raise_for_status()
            data = r.json()
            access = data["access_token"]
            # Exchange for a long-lived token (60 days)
            ll_r = await client.get(
                f"{self.graph_url}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": self.app_id,
                    "client_secret": self.app_secret,
                    "fb_exchange_token": access,
                },
            )
            if ll_r.status_code == 200:
                access = ll_r.json()["access_token"]
            # Get the IG user id
            handle, ig_user_id = await self._fetch_ig_user(client, access)
            return OAuthCredentials(
                platform="instagram",
                access_token=access,
                expires_at=time.time() + 60 * 24 * 3600,  # 60 days
                open_id=ig_user_id,
                account_handle=handle,
                scope="instagram_basic,instagram_content_publish",
            )

    async def _fetch_ig_user(self, client: httpx.AsyncClient,
                              access_token: str) -> tuple[str | None, str | None]:
        try:
            r = await client.get(
                f"{self.graph_url}/me/accounts",
                params={"fields": "instagram_business_account{id,username}", "access_token": access_token},
            )
            if r.status_code == 200:
                pages = r.json().get("data", [])
                for page in pages:
                    ig = page.get("instagram_business_account")
                    if ig:
                        return f"@{ig.get('username', '')}", ig.get("id")
        except Exception:
            pass
        return None, None

    async def refresh_access_token(self, creds: OAuthCredentials) -> OAuthCredentials:
        # Instagram long-lived tokens are valid for 60 days. Re-exchange if needed.
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{self.graph_url}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": self.app_id,
                    "client_secret": self.app_secret,
                    "fb_exchange_token": creds.access_token,
                },
            )
            if r.status_code == 200:
                creds.access_token = r.json()["access_token"]
                creds.expires_at = time.time() + 60 * 24 * 3600
        return creds

    async def publish(self, creds: OAuthCredentials, req: PublishRequest) -> PublishResult:
        ig_user_id = creds.open_id
        if not ig_user_id:
            return PublishResult(
                platform="instagram",
                status=PublishStatus.FAILED,
                error_message="No Instagram user id. Reconnect the account.",
            )
        caption = req.description + "\n\n" + " ".join(req.hashtags) if req.hashtags else req.description
        async with httpx.AsyncClient(timeout=600.0) as client:
            # 1. Create the upload container
            # NOTE: For video uploads > 100MB, Instagram requires a public
            # video_url (you'd host the file somewhere). For local files,
            # Instagram's API requires the file to be at a public URL.
            # The simplest workaround: upload to your own server and pass
            # that URL. For now, this is a known limitation.
            container_r = await client.post(
                f"{self.graph_url}/{ig_user_id}/media",
                params={
                    "media_type": "REELS",
                    "video_url": f"file://{req.video_path}",  # placeholder
                    "caption": caption[:2200],
                    "access_token": creds.access_token,
                },
            )
            if container_r.status_code != 200:
                return PublishResult(
                    platform="instagram",
                    status=PublishStatus.FAILED,
                    error_message=f"Container creation failed: {container_r.text[:200]}",
                )
            container_id = container_r.json()["id"]

            # 2. Publish the container
            for _ in range(20):
                await asyncio.sleep(5)
                pub_r = await client.post(
                    f"{self.graph_url}/{ig_user_id}/media_publish",
                    params={
                        "creation_id": container_id,
                        "access_token": creds.access_token,
                    },
                )
                if pub_r.status_code == 200:
                    post_id = pub_r.json()["id"]
                    return PublishResult(
                        platform="instagram",
                        status=PublishStatus.PUBLISHED,
                        post_id=post_id,
                        post_url=f"https://www.instagram.com/reel/{post_id}",
                    )
            return PublishResult(
                platform="instagram",
                status=PublishStatus.FAILED,
                error_message="Timeout waiting for Instagram to publish",
            )


# ── Factory ───────────────────────────────────────────────────────────────

def get_publisher_for_platform(platform: Platform) -> SocialPublisher:
    """Return the right publisher for the given platform.

    Priority:
      1. If real credentials are in the .env, return the real publisher
      2. Otherwise, return a MockPublisher (always works, simulates success)
    """
    if platform == "tiktok":
        key = getattr(settings, "tiktok_client_key", "")
        secret = getattr(settings, "tiktok_client_secret", "")
        if key and secret:
            return TikTokPublisher(key, secret)
    elif platform == "youtube":
        client_id = getattr(settings, "youtube_client_id", "")
        client_secret = getattr(settings, "youtube_client_secret", "")
        if client_id and client_secret:
            return YouTubePublisher(client_id, client_secret)
    elif platform == "instagram":
        app_id = getattr(settings, "instagram_app_id", "")
        app_secret = getattr(settings, "instagram_app_secret", "")
        if app_id and app_secret:
            return InstagramPublisher(app_id, app_secret)

    # Fallback: mock
    mock = MockPublisher()
    mock.platform = platform
    return mock


def is_platform_configured(platform: Platform) -> bool:
    """Return True if real OAuth credentials are configured for this platform."""
    if platform == "tiktok":
        return bool(getattr(settings, "tiktok_client_key", "")) and \
               bool(getattr(settings, "tiktok_client_secret", ""))
    if platform == "youtube":
        return bool(getattr(settings, "youtube_client_id", "")) and \
               bool(getattr(settings, "youtube_client_secret", ""))
    if platform == "instagram":
        return bool(getattr(settings, "instagram_app_id", "")) and \
               bool(getattr(settings, "instagram_app_secret", ""))
    return False
