from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    student_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("students.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False, default="New conversation")


class ChatMessage(Base, TimestampMixin):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(String(8000), nullable=False)
    intent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Generative-UI blocks (assistant messages) built deterministically from
    # tool results - see agents/content_blocks.py. Persisted here (not just
    # in trace_events) so switching back to a past conversation renders the
    # same rich UI it did live, not just plain text.
    content_blocks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Files the student attached to a user message (already uploaded via
    # POST /api/files/upload before the chat request was sent).
    attachments: Mapped[list | None] = mapped_column(JSON, nullable=True)


class TraceEvent(Base, TimestampMixin):
    """Persisted copy of the execution-trace events streamed to the client.

    Kept for history/debugging of a session's activity panel. Payloads are
    the same safe, user-facing summaries sent over SSE — never raw model
    reasoning, prompts, or secrets (see agents/orchestrator.py).
    """

    __tablename__ = "trace_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    message_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("chat_messages.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
