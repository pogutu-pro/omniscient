from __future__ import annotations

from pydantic import BaseModel, Field


class SearchPaperContentParams(BaseModel):
    """Input for semantic search across the text of past papers.

    Kept separate from `PastPaperSearchParams` on purpose: that one is a
    metadata lookup (course code, year), this one is a full-text semantic
    search over the indexed PDF content. A student asking "how do I
    integrate by parts" has no course code to give and needs the second.
    """

    query: str = Field(min_length=2, max_length=500, description="The question or phrase to look for.")
    top_k: int | None = Field(default=None, ge=1, le=20, description="How many excerpts to return.")
