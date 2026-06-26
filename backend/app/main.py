from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
import time

from app.config import settings
from app.database import create_tables
from app.utils.logger import setup_logging, get_logger
from app.routers import projects, upload, transcription, analysis, chat, export, system, clips, vertical, social

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("starting_app", name=settings.app_name, version=settings.app_version)
    await create_tables()
    logger.info("database_ready")

    # Recover projects stuck in transient states from a previous crash.
    # Without this, a project that was 'transcribing' when the server died
    # stays stuck forever — the user can't re-transcribe because the UI
    # disables the button while status == 'transcribing'.
    await _recover_stuck_projects()

    yield
    logger.info("shutting_down")
    from app.services.ai_service import ai_service
    await ai_service.close()


async def _recover_stuck_projects():
    """Reset projects stuck in 'transcribing' or 'extracting_audio' to 'error'."""
    from app.database import AsyncSessionLocal
    from app.models.project import Project, ProjectStatus
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Project).where(
                Project.status.in_([ProjectStatus.TRANSCRIBING, ProjectStatus.EXTRACTING_AUDIO])
            )
        )
        stuck = list(result.scalars().all())
        for project in stuck:
            old_status = project.status
            logger.warning("recovering_stuck_project",
                           project_id=project.id,
                           old_status=old_status)
            project.status = ProjectStatus.ERROR
            project.error_message = f"Recovered from stuck state '{old_status}' on server restart"
        if stuck:
            await db.commit()
            logger.info("recovered_stuck_projects", count=len(stuck))


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Local AI-powered transcription and analysis platform",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def add_request_logging(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round(duration * 1000, 1),
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc) if settings.debug else None},
    )


PREFIX = "/api/v1"
app.include_router(system.router, prefix=PREFIX)
# analysis-types must be registered before projects/{project_id} to avoid int conversion conflict
app.include_router(analysis.router, prefix=PREFIX)
app.include_router(projects.router, prefix=PREFIX)
app.include_router(upload.router, prefix=PREFIX)
app.include_router(transcription.router, prefix=PREFIX)
app.include_router(chat.router, prefix=PREFIX)
app.include_router(export.router, prefix=PREFIX)
app.include_router(clips.router, prefix=PREFIX)
# vertical.router has mixed paths but all absolute, so PREFIX just prepends.
app.include_router(vertical.router, prefix=PREFIX)
app.include_router(social.router, prefix=PREFIX)


@app.get("/")
async def root():
    return {"message": f"{settings.app_name} v{settings.app_version}", "docs": "/api/docs"}
