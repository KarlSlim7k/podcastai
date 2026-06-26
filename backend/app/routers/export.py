from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.schemas import ExportRequest, ExportOut, MessageResponse
from app.models.project import Export
from app.services.project_service import project_service
from app.services.export_service import export_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["export"])

MIME_TYPES = {
    "txt": "text/plain",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "markdown": "text/markdown",
    "json": "application/json",
    "srt": "text/plain",
    "vtt": "text/vtt",
}


@router.post("/{project_id}/export", response_model=ExportOut)
async def create_export(
    project_id: int,
    request: ExportRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get(db, project_id)

    if not project.transcription or not project.transcription.text:
        if request.format not in ("srt", "vtt"):
            raise HTTPException(status_code=400, detail="No transcription available for export")

    try:
        fmt = request.format
        if fmt == "txt":
            file_path = export_service.export_txt(project)
        elif fmt == "markdown":
            file_path = export_service.export_markdown(project)
        elif fmt == "json":
            file_path = export_service.export_json(project)
        elif fmt == "srt":
            file_path = export_service.export_srt(project)
        elif fmt == "vtt":
            file_path = export_service.export_vtt(project)
        elif fmt == "docx":
            file_path = export_service.export_docx(project)
        elif fmt == "pdf":
            file_path = export_service.export_pdf(project)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")

        file_size = file_path.stat().st_size

        export = Export(
            project_id=project_id,
            export_type=fmt,
            file_path=str(file_path),
            file_size=file_size,
        )
        db.add(export)
        await db.flush()
        await db.refresh(export)

        logger.info("export_created", project_id=project_id, format=fmt, size=file_size)
        return export

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("export_failed", project_id=project_id, format=request.format, error=str(e))
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/{project_id}/export/{export_id}/download")
async def download_export(
    project_id: int,
    export_id: int,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    result = await db.execute(
        select(Export).where(Export.id == export_id, Export.project_id == project_id)
    )
    export = result.scalar_one_or_none()

    if not export:
        raise HTTPException(status_code=404, detail="Export not found")

    if not export.file_path or not Path(export.file_path).exists():
        raise HTTPException(status_code=404, detail="Export file not found on disk")

    file_path = Path(export.file_path)
    media_type = MIME_TYPES.get(export.export_type, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_path.name,
    )


@router.get("/{project_id}/exports", response_model=list[ExportOut])
async def list_exports(project_id: int, db: AsyncSession = Depends(get_db)):
    project = await project_service.get(db, project_id)
    return project.exports
