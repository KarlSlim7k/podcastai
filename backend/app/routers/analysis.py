import asyncio
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.schemas import AnalysisRequest, AnalysisSingleRequest, AnalysisOut, MessageResponse
from app.models.project import Analysis, ProjectStatus
from app.services.project_service import project_service
from app.services.ai_service import ai_service, ANALYSIS_PROMPTS
from app.utils.security import validate_model_name
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["analysis"])


async def _run_analysis_batch(project_id: int, analysis_types: list[str], model: str):  # pragma: no cover
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        project = await project_service.get(db, project_id)
        if not project.transcription or not project.transcription.text:
            logger.error("no_transcription_for_analysis", project_id=project_id)
            return

        transcript_text = project.transcription.text

    for atype in analysis_types:
        try:
            content, elapsed = await ai_service.analyze_transcript(transcript_text, atype, model)

            async with AsyncSessionLocal() as db2:
                result = await db2.execute(
                    select(Analysis).where(
                        Analysis.project_id == project_id,
                        Analysis.analysis_type == atype,
                    )
                )
                analysis = result.scalar_one_or_none()
                if analysis:
                    analysis.content = content
                    analysis.model_used = model
                    analysis.processing_time = elapsed
                    analysis.error_message = None
                else:
                    analysis = Analysis(
                        project_id=project_id,
                        analysis_type=atype,
                        model_used=model,
                        content=content,
                        processing_time=elapsed,
                    )
                    db2.add(analysis)
                await db2.commit()

        except Exception as e:
            logger.error("analysis_failed", project_id=project_id, type=atype, error=str(e))
            async with AsyncSessionLocal() as db3:
                result = await db3.execute(
                    select(Analysis).where(
                        Analysis.project_id == project_id,
                        Analysis.analysis_type == atype,
                    )
                )
                analysis = result.scalar_one_or_none()
                if not analysis:
                    analysis = Analysis(project_id=project_id, analysis_type=atype)
                    db3.add(analysis)
                analysis.error_message = str(e)
                analysis.model_used = model
                await db3.commit()


@router.get("/analysis-types", tags=["system"])
async def get_analysis_types():
    return {"types": list(ANALYSIS_PROMPTS.keys())}


@router.post("/{project_id}/analyze", response_model=MessageResponse)
async def start_analysis(
    project_id: int,
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get(db, project_id)

    if not project.transcription or not project.transcription.text:
        raise HTTPException(status_code=400, detail="No transcription available. Please transcribe first.")

    valid_types = list(ANALYSIS_PROMPTS.keys())
    invalid = [t for t in request.analysis_types if t not in valid_types]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid analysis types: {invalid}")

    model = validate_model_name(request.model)

    background_tasks.add_task(_run_analysis_batch, project_id, request.analysis_types, model)

    return MessageResponse(
        message=f"Analysis started for {len(request.analysis_types)} type(s)",
        detail=f"Using model: {model}",
    )


@router.post("/{project_id}/analyze/single", response_model=AnalysisOut)
async def analyze_single(
    project_id: int,
    request: AnalysisSingleRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get(db, project_id)

    if not project.transcription or not project.transcription.text:
        raise HTTPException(status_code=400, detail="No transcription available")

    if request.analysis_type not in ANALYSIS_PROMPTS:
        raise HTTPException(status_code=400, detail=f"Invalid analysis type: {request.analysis_type}")

    model = validate_model_name(request.model)

    content, elapsed = await ai_service.analyze_transcript(
        project.transcription.text, request.analysis_type, model
    )

    result = await db.execute(
        select(Analysis).where(
            Analysis.project_id == project_id,
            Analysis.analysis_type == request.analysis_type,
        )
    )
    analysis = result.scalar_one_or_none()

    if analysis:
        analysis.content = content
        analysis.model_used = model
        analysis.processing_time = elapsed
        analysis.error_message = None
    else:
        analysis = Analysis(
            project_id=project_id,
            analysis_type=request.analysis_type,
            model_used=model,
            content=content,
            processing_time=elapsed,
        )
        db.add(analysis)

    await db.flush()
    await db.refresh(analysis)
    return analysis


@router.get("/{project_id}/analyses", response_model=list[AnalysisOut])
async def get_analyses(project_id: int, db: AsyncSession = Depends(get_db)):
    project = await project_service.get(db, project_id)
    return project.analyses


@router.delete("/{project_id}/analyses/{analysis_id}", response_model=MessageResponse)
async def delete_analysis(project_id: int, analysis_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Analysis).where(
            Analysis.id == analysis_id,
            Analysis.project_id == project_id,
        )
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    await db.delete(analysis)
    await db.flush()
    return MessageResponse(message="Analysis deleted")
