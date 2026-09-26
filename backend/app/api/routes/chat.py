from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import orchestrator
from app.agents.providers.base import AttachmentContent, ChatTurn, LLMProvider
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
from app.repositories.message_rating_repository import MessageNotFound, SqlMessageRatingRepository
from app.repositories.student_repository import SqlStudentRepository
from app.schemas.chat import ChatRequest, RatingIn, RatingOut, ShareIn, ShareOut
from app.services import personalization_service
from app.services.storage.factory import get_storage_backend
from app.tools.registry import ToolContext, ToolRegistry

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = get_logger(component="chat_api")

# How often to send a keep-alive comment frame while waiting on a slow
# provider (or nothing new to report). SSE comment lines (": ...") are
# invisible to EventSource/fetch readers that only look at "data:" lines,
# but they keep intermediate proxies/load balancers from timing out an
# idle-looking connection, and give the frontend a clear "still connected"
# signal distinct from "the connection died".
HEARTBEAT_SECONDS = 15


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


_QUEUE_DONE = object()


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

    storage = get_storage_backend(settings)
    attachment_records: list[dict] = []
    attachment_contents: list[AttachmentContent] = []
    for attachment in payload.attachments:
        try:
            data = await storage.read(attachment.key)
        except FileNotFoundError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Attachment not found: {attachment.file_name}")
        url = storage.url_for(attachment.key)
        attachment_records.append(
            {"key": attachment.key, "content_type": attachment.content_type, "file_name": attachment.file_name, "url": url}
        )
        attachment_contents.append(
            AttachmentContent(filename=attachment.file_name, content_type=attachment.content_type, data=data, url=url)
        )

    user_message = await chat_repo.add_message(
        chat_session.id, "user", payload.message, attachments=attachment_records or None
    )
    remembered_preferences = (
        personalization_service.sanitize_preferences(student.preferences) if student else {}
    )

    async def event_stream():
        final_text_parts: list[str] = []
        final_intent = "general"
        preference_updates: dict = {}
        content_blocks: list[dict] = []

        yield _sse({"type": "session", "session_id": chat_session.id})

        # The orchestrator (and all DB writes for this request) run in a
        # single background task feeding a queue, so this generator is
        # free to emit heartbeat frames on a timer without ever touching
        # `session_db` concurrently from two coroutines.
        queue: asyncio.Queue = asyncio.Queue()

        async def produce() -> None:
            try:
                async for event in orchestrator.run(
                    message=payload.message,
                    history=history,
                    ctx=ctx,
                    registry=registry,
                    provider=provider,
                    remembered_preferences=remembered_preferences,
                    attachments=attachment_contents or None,
                ):
                    event_dict = event.model_dump(exclude_none=True)
                    await chat_repo.add_trace_event(chat_session.id, user_message.id, event.type, event_dict)
                    await queue.put(event_dict)
            except Exception:
                logger.exception("chat_stream_failed", session_id=chat_session.id)
                await queue.put(
                    {"type": "error", "message": "Omniscient is temporarily unable to process that request."}
                )
            finally:
                await queue.put(_QUEUE_DONE)

        producer_task = asyncio.create_task(produce())

        try:
            while True:
                try:
                    event_dict = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                if event_dict is _QUEUE_DONE:
                    break

                if event_dict.get("type") == "answer_chunk" and event_dict.get("message"):
                    final_text_parts.append(event_dict["message"])
                if event_dict.get("type") == "content_block" and event_dict.get("data"):
                    content_blocks.append(event_dict["data"])
                if event_dict.get("type") == "done" and event_dict.get("data"):
                    final_intent = event_dict["data"].get("intent", final_intent)
                    preference_updates = event_dict["data"].get("preference_updates") or {}

                yield _sse(event_dict)
        finally:
            # Never leaves the producer running past the response: if the
            # client disconnects mid-stream, this generator is closed and
            # we cancel the background task rather than leaking it.
            if not producer_task.done():
                producer_task.cancel()
            await asyncio.gather(producer_task, return_exceptions=True)

        final_text = "".join(final_text_parts).strip()
        assistant_message_id: str | None = None
        if final_text or content_blocks:
            assistant_message = await chat_repo.add_message(
                chat_session.id, "assistant", final_text, final_intent, content_blocks=content_blocks or None
            )
            # Hand the client the id the database assigned. While a reply is
            # streaming the frontend only has a temporary local id, and any
            # action addressed to that id (rating an answer, say) would 404
            # against the server. Without this the copy/share/rate row is
            # inert on every freshly produced answer and only works after a
            # reload.
            assistant_message_id = assistant_message.id
        if student and preference_updates:
            await student_repo.update_preferences(student.id, preference_updates)

        yield _sse(
            {
                "type": "stream_end",
                "session_id": chat_session.id,
                "message_id": assistant_message_id,
            }
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    student: Student | None = Depends(get_optional_student),
    session_db: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    chat_repo = SqlChatRepository(session_db)
    chat_session = await chat_repo.get_session(session_id)
    if not chat_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    messages = await chat_repo.list_messages(session_id)
    # The student's own verdicts ride along with the history so reopening a
    # conversation shows the thumbs they already pressed, rather than
    # resetting the control and inviting them to rate the same reply twice.
    # Deliberately optional auth: history has always been readable without a
    # token, and requiring one here would be a breaking change unrelated to
    # ratings. An anonymous caller simply gets no ratings rather than someone
    # else's.
    ratings = (
        await SqlMessageRatingRepository(session_db).ratings_for_messages([m.id for m in messages], student.id)
        if student
        else {}
    )
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "intent": m.intent,
            "created_at": m.created_at.isoformat(),
            "content_blocks": m.content_blocks,
            "attachments": m.attachments,
            "rating": ratings.get(m.id),
        }
        for m in messages
    ]


@router.post("/messages/{message_id}/share", response_model=ShareOut)
async def record_share(
    message_id: str,
    payload: ShareIn,
    student: Student = Depends(get_current_student),
    session_db: AsyncSession = Depends(get_db_session),
) -> ShareOut:
    """Record that a student shared an answer, and to where.

    Copying is not counted: it is a private, local action, and a student who
    copies an answer to their notes has not shared it with anyone.
    """
    from sqlalchemy import select, update

    from app.models.chat import ChatMessage

    message = await session_db.get(ChatMessage, message_id)
    if message is None or message.role != "assistant":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    await session_db.execute(
        update(ChatMessage).where(ChatMessage.id == message_id).values(share_count=ChatMessage.share_count + 1)
    )
    await session_db.commit()
    count = (
        await session_db.execute(select(ChatMessage.share_count).where(ChatMessage.id == message_id))
    ).scalar_one()
    return ShareOut(message_id=message_id, share_count=count, target=payload.target)


@router.get("/messages/{message_id}/rating", response_model=RatingOut)
async def get_message_rating(
    message_id: str,
    student: Student = Depends(get_current_student),
    session_db: AsyncSession = Depends(get_db_session),
) -> RatingOut:
    repo = SqlMessageRatingRepository(session_db)
    ratings = await repo.ratings_for_messages([message_id], student.id)
    return RatingOut(message_id=message_id, rating=ratings.get(message_id))  # type: ignore[arg-type]


@router.put("/messages/{message_id}/rating", response_model=RatingOut)
async def rate_message(
    message_id: str,
    payload: RatingIn,
    student: Student = Depends(get_current_student),
    session_db: AsyncSession = Depends(get_db_session),
) -> RatingOut:
    """Record a thumbs-up / thumbs-down on an assistant reply.

    Re-rating replaces the previous verdict rather than adding to it, and
    the same verdict twice is a no-op - so a student can change their mind
    without inflating anything.
    """
    repo = SqlMessageRatingRepository(session_db)
    try:
        rating = await repo.rate(message_id=message_id, student_id=student.id, rating=payload.rating)
    except MessageNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return RatingOut(message_id=message_id, rating=rating)  # type: ignore[arg-type]


@router.delete(
    "/messages/{message_id}/rating",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def clear_message_rating(
    message_id: str,
    student: Student = Depends(get_current_student),
    session_db: AsyncSession = Depends(get_db_session),
) -> None:
    """Clear this student's verdict - what pressing the lit thumb again does."""
    await SqlMessageRatingRepository(session_db).clear(message_id=message_id, student_id=student.id)


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
