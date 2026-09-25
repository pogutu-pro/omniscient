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
