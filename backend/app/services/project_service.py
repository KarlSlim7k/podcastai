import shutil
from pathlib import Path
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from app.models.project import Project, ProjectStatus, Transcription, Clip, ProjectStatus
from app.models.schemas import ProjectCreate, ProjectUpdate
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ProjectService:
    async def create(self, db: AsyncSession, data: ProjectCreate) -> Project:
        project = Project(name=data.name, description=data.description)
        db.add(project)
        await db.flush()

        project_dir = settings.projects_dir / str(project.id)
        project_dir.mkdir(parents=True, exist_ok=True)

        await db.refresh(project)
        logger.info("project_created", project_id=project.id, name=project.name)
        return project

    async def get(self, db: AsyncSession, project_id: int) -> Project:
        result = await db.execute(
            select(Project)
            .where(Project.id == project_id)
            .options(
                selectinload(Project.transcription).selectinload(Transcription.clips),
                selectinload(Project.transcription).selectinload(Transcription.clips).selectinload(Clip.platforms),
                selectinload(Project.analyses),
                selectinload(Project.exports),
            )
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        return project

    async def get_simple(self, db: AsyncSession, project_id: int) -> Project:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        return project

    async def list(self, db: AsyncSession, skip: int = 0, limit: int = 50) -> list[Project]:
        result = await db.execute(
            select(Project).order_by(Project.created_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def update(self, db: AsyncSession, project_id: int, data: ProjectUpdate) -> Project:
        project = await self.get_simple(db, project_id)
        if data.name is not None:
            project.name = data.name
        if data.description is not None:
            project.description = data.description
        project.updated_at = datetime.utcnow()
        await db.flush()
        return project

    async def update_status(self, db: AsyncSession, project_id: int, status: ProjectStatus, error: str | None = None):
        project = await self.get_simple(db, project_id)
        project.status = status
        if error:
            project.error_message = error
        project.updated_at = datetime.utcnow()
        await db.flush()

    async def delete(self, db: AsyncSession, project_id: int):
        project = await self.get_simple(db, project_id)

        project_dir = settings.projects_dir / str(project_id)
        if project_dir.exists():
            shutil.rmtree(project_dir, ignore_errors=True)

        if project.original_file and Path(project.original_file).exists():
            Path(project.original_file).unlink(missing_ok=True)

        await db.delete(project)
        await db.flush()
        logger.info("project_deleted", project_id=project_id)


project_service = ProjectService()
