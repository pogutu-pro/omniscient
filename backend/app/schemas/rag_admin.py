from __future__ import annotations

from pydantic import BaseModel, Field


class ReindexRequest(BaseModel):
    # Off by default so an accidental double-click cannot burn minutes of
    # CPU re-embedding an index that is already current.
    force: bool = Field(
        default=False,
        description="Rebuild papers that already have chunks. Without this, only new or previously "
        "unreadable papers are processed, which makes the call cheap and idempotent.",
    )
    past_paper_ids: list[str] | None = Field(
        default=None,
        max_length=200,
        description="Restrict the reindex to these paper ids. Omit to consider every paper.",
    )
    concurrency: int = Field(
        default=1,
        ge=1,
        le=4,
        description="How many papers to process at once. Embedding is CPU-bound, so higher is not faster "
        "on a small VM — it just competes with live chat traffic.",
    )


class ReindexAccepted(BaseModel):
    started: bool
    already_running: bool = False
    detail: str


class ReindexStatus(BaseModel):
    running: bool
    total_chunks: int
    indexed_papers: int
    total_papers: int
    last_report: dict | None = None
    last_error: str | None = None
    embedding_backend: str
    embedding_model: str
    rag_enabled: bool
