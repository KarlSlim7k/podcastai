from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.schemas import ProjectCreate, ProjectUpdate, ProjectOut, ProjectListOut, MessageResponse
from app.services.project_service import project_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectListOut])
async def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    return await project_service.list(db, skip=skip, limit=limit)


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = await project_service.create(db, data)
    return await project_service.get(db, project.id)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    return await project_service.get(db, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: int, data: ProjectUpdate, db: AsyncSession = Depends(get_db)):
    await project_service.update(db, project_id, data)
    return await project_service.get(db, project_id)


@router.delete("/{project_id}", response_model=MessageResponse)
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db)):
    await project_service.delete(db, project_id)
    return MessageResponse(message=f"Project {project_id} deleted successfully")
