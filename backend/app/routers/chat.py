from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.schemas import ChatRequest, ChatResponse, ChatMessageOut, MessageResponse
from app.models.project import ChatMessage
from app.services.project_service import project_service
from app.services.ai_service import ai_service
from app.services.rag_service import rag_service
from app.utils.security import validate_model_name, sanitize_text_input
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["chat"])


@router.post("/{project_id}/chat", response_model=ChatResponse)
async def chat(
    project_id: int,
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get(db, project_id)

    if not project.transcription or not project.transcription.text:
        raise HTTPException(status_code=400, detail="No transcription available for this project")

    question = sanitize_text_input(request.message, max_length=2000)
    model = validate_model_name(request.model)

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.project_id == project_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
    )
    history = [
        {"role": msg.role, "content": msg.content}
        for msg in reversed(result.scalars().all())
    ]

    context, retrieved_chunks = rag_service.retrieve(
        query=question,
        transcript_text=project.transcription.text,
        segments=project.transcription.segments,
        top_k=5,
    )

    response_text = await ai_service.chat_with_context(
        question=question,
        context=context,
        model=model,
        conversation_history=history,
    )

    user_msg = ChatMessage(
        project_id=project_id,
        role="user",
        content=question,
        model_used=model,
    )
    db.add(user_msg)
    await db.flush()

    assistant_msg = ChatMessage(
        project_id=project_id,
        role="assistant",
        content=response_text,
        context_used=context[:500] if context else None,
        model_used=model,
    )
    db.add(assistant_msg)
    await db.flush()
    await db.refresh(assistant_msg)

    logger.info("chat_response", project_id=project_id, model=model, chunks=len(retrieved_chunks))

    return ChatResponse(
        response=response_text,
        context_used=context[:300] + "..." if len(context) > 300 else context,
        model_used=model,
        message_id=assistant_msg.id,
    )


@router.get("/{project_id}/chat/history", response_model=list[ChatMessageOut])
async def get_chat_history(
    project_id: int,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    await project_service.get_simple(db, project_id)
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.project_id == project_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


@router.delete("/{project_id}/chat/history", response_model=MessageResponse)
async def clear_chat_history(project_id: int, db: AsyncSession = Depends(get_db)):
    await project_service.get_simple(db, project_id)
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.project_id == project_id)
    )
    messages = result.scalars().all()
    for msg in messages:
        await db.delete(msg)
    await db.flush()
    return MessageResponse(message=f"Deleted {len(messages)} messages")
