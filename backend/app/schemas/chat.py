from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Domain = Literal["housing", "academics", "past_papers", "complaints", "general"]


class AttachmentIn(BaseModel):
    """A file already uploaded via POST /api/files/upload, attached to a
    chat message. Only the storage key + metadata travel over the wire -
    never raw bytes in the chat request body."""

    key: str = Field(min_length=1, max_length=500)
    content_type: str = Field(min_length=1, max_length=100)
    file_name: str = Field(min_length=1, max_length=255)


class AttachmentOut(BaseModel):
    key: str
    content_type: str
    file_name: str
    url: str


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)
    attachments: list[AttachmentIn] = Field(default_factory=list, max_length=4)


class IntentResult(BaseModel):
    """Structured output of the router. Never free-form text from the model."""

    intent: Domain
    confidence: float = Field(ge=0.0, le=1.0)
    parameters: dict[str, Any] = Field(default_factory=dict)


class TraceEventOut(BaseModel):
    type: Literal["status", "tool_call", "tool_result", "content_block", "answer_chunk", "error", "done"]
    message: str | None = None
    tool: str | None = None
    status: str | None = None
    summary: str | None = None
    data: dict[str, Any] | None = None
    # The tool's validated, merged arguments, so the activity trace can show
    # what was actually searched for ("max_budget_ksh=8000, area=Boma")
    # rather than only that a search happened. These are the arguments the
    # tool's own Pydantic model accepted, not raw model output.
    arguments: dict[str, Any] | None = None
    # Server-measured wall time for the step. Measured here rather than in the
    # browser so it reflects real work and does not include network latency.
    duration_ms: int | None = None


class RatingIn(BaseModel):
    """A thumbs verdict. Constrained to the two values a control can send,
    so the database's own CHECK constraint is never the first line of
    defence."""

    rating: Literal[1, -1]


class RatingOut(BaseModel):
    message_id: str
    rating: Literal[1, -1] | None


class ShareIn(BaseModel):
    """Where an answer was shared. A free string rather than an enum because
    the frontend can also report the OS share sheet ("native") and a
    clipboard fallback ("clipboard"), and new targets should not need a
    backend change to be counted."""

    target: str = Field(min_length=1, max_length=40)


class ShareOut(BaseModel):
    message_id: str
    share_count: int
    target: str
