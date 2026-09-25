from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import orchestrator
from app.agents.providers.base import ChatTurn, LLMProvider
from app.api.deps import (
    get_current_student,
    get_db_session,
    get_llm_provider_dep,
    get_optional_student,
    get_settings_dep,
    get_tool_context,
    get_tool_registry,
)
from app.core.config import Settings
from app.core.logging import get_logger
from app.core.rate_limit import enforce_chat_rate_limit
from app.models.student import Student
from app.repositories.chat_repository import SqlChatRepository
from app.repositories.student_repository import SqlStudentRepository
from app.schemas.chat import ChatRequest
from app.services import personalization_service
from app.tools.registry import ToolContext, ToolRegistry

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = get_logger(component="chat_api")


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("", dependencies=[Depends(enforce_chat_rate_limit)])
async def chat(
    request: Request,
    payload: ChatRequest,
    settings: Settings = Depends(get_settings_dep),
    session_db: AsyncSession = Depends(get_db_session),
    ctx: ToolContext = Depends(get_tool_context),
    registry: ToolRegistry = Depends(get_tool_registry),
    provider: LLMProvider = Depends(get_llm_provider_dep),
    student: Student | None = Depends(get_optional_student),
) -> StreamingResponse:
    chat_repo = SqlChatRepository(session_db)
    student_repo = SqlStudentRepository(session_db)

    if payload.session_id:
        chat_session = await chat_repo.get_session(payload.session_id)
        if not chat_session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    else:
        chat_session = await chat_repo.create_session(student.id if student else None)
        await chat_repo.set_title(chat_session.id, payload.message.strip())

    history_messages = await chat_repo.list_messages(chat_session.id)
    history = [ChatTurn(role=m.role, content=m.content) for m in history_messages]

    user_message = await chat_repo.add_message(chat_session.id, "user", payload.message)
    remembered_preferences = (
        personalization_service.sanitize_preferences(student.preferences) if student else {}
    )

    async def event_stream():
        final_text_parts: list[str] = []
        final_intent = "general"
        preference_updates: dict = {}

        yield _sse({"type": "session", "session_id": chat_session.id})

        try:
            async for event in orchestrator.run(
                message=payload.message,
                history=history,
                ctx=ctx,
                registry=registry,
                provider=provider,
                remembered_preferences=remembered_preferences,
            ):
                event_dict = event.model_dump(exclude_none=True)
                await chat_repo.add_trace_event(chat_session.id, user_message.id, event.type, event_dict)

                if event.type == "answer_chunk" and event.message:
                    final_text_parts.append(event.message)
                if event.type == "done" and event.data:
                    final_intent = event.data.get("intent", final_intent)
                    preference_updates = event.data.get("preference_updates") or {}

                yield _sse(event_dict)
        except Exception:
            logger.exception("chat_stream_failed", session_id=chat_session.id)
            yield _sse({"type": "error", "message": "Omniscient is temporarily unable to process that request."})

        final_text = "".join(final_text_parts).strip()
        if final_text:
            await chat_repo.add_message(chat_session.id, "assistant", final_text, final_intent)
        if student and preference_updates:
            await student_repo.update_preferences(student.id, preference_updates)

        yield _sse({"type": "stream_end", "session_id": chat_session.id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    session_db: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    chat_repo = SqlChatRepository(session_db)
    chat_session = await chat_repo.get_session(session_id)
    if not chat_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    messages = await chat_repo.list_messages(session_id)
    return [
        {"id": m.id, "role": m.role, "content": m.content, "intent": m.intent, "created_at": m.created_at.isoformat()}
        for m in messages
    ]


@router.get("/sessions")
async def list_my_sessions(
    student: Student = Depends(get_current_student),
    session_db: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    from sqlalchemy import select

    from app.models.chat import ChatSession

    stmt = (
        select(ChatSession)
        .where(ChatSession.student_id == student.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(50)
    )
    result = await session_db.execute(stmt)
    return [
        {"id": s.id, "title": s.title, "created_at": s.created_at.isoformat(), "updated_at": s.updated_at.isoformat()}
        for s in result.scalars().all()
    ]
