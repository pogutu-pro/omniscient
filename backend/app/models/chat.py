from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
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
    # How many times this answer has been shared. A plain counter rather than
    # a row per share: the useful signal is "was this answer worth passing
    # on", not a log of who sent it where. Copying is deliberately NOT
    # counted - it is a private, local action and tracking it would be
    # surveillance of behaviour a student reasonably expects to be private.
    share_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class MessageRating(Base, TimestampMixin):
    """A student's thumbs-up / thumbs-down on one assistant reply.

    Stored rather than kept in the browser because a rating control that
    discards what it collects is worse than no control at all - it tells a
    student their feedback was heard and then throws it away. One row per
    (message, student) so re-rating replaces the previous verdict instead of
    inflating the totals, and clearing it removes the row entirely.

    `rating` is 1 or -1. Nothing here is fed to a model: it is read by the
    admin insights endpoint as already-captured signal, the same honest
    sense of "learns from users" as the rest of insights.
    """

    __tablename__ = "message_ratings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    message_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_messages.id"), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id"), nullable=False, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("message_id", "student_id", name="uq_message_ratings_message_student"),)


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
