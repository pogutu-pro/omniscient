"""Answering a question from the past-paper index.

Embeds the student's question, finds the nearest chunks in pgvector, and
returns them with enough provenance for the model to cite a source. It
also resolves each chunk back to the paper's course code and year, because
a quotation a student cannot attribute is much less useful to them than
one they can go and check.

Every failure mode here returns "nothing found" rather than raising:
retrieval is a bonus on top of an assistant that already works without
it, so a missing model or an unbuilt index must not turn a question into
a 500.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.academics import Course
from app.models.past_paper import PastPaper
from app.repositories.chunk_repository import (
    ChunkMatch,
    ChunkRepository,
    SqlChunkRepository,
    VectorSearchUnavailable,
)
from app.services.embedding_service import EmbeddingService, EmbeddingUnavailable

logger = get_logger(component="paper_search")


@dataclass(frozen=True)
class Citation:
    past_paper_id: str
    course_code: str
    course_name: str
    academic_year: str
    semester: int
    exam_type: str
    chunk_index: int
    page_start: int | None
    page_end: int | None
    score: float

    def label(self) -> str:
        pages = f", p. {self.page_start}" if self.page_start else ""
        if self.page_end and self.page_end != self.page_start:
            pages = f", pp. {self.page_start}-{self.page_end}"
        return f"{self.course_code} {self.academic_year} S{self.semester} ({self.exam_type}){pages}"


@dataclass(frozen=True)
class SearchResult:
    query: str
    matches: list[tuple[Citation, str]]
    available: bool = True
    note: str | None = None

    def is_empty(self) -> bool:
        return not self.matches


class PaperSearchService:
    def __init__(
        self,
        session: AsyncSession,
        embeddings: EmbeddingService,
        settings: Settings,
        chunk_repo: ChunkRepository | None = None,
    ):
        self._session = session
        self._embeddings = embeddings
        self._settings = settings
        self._chunks = chunk_repo or SqlChunkRepository(session)

    @property
    def is_live(self) -> bool:
        return self._settings.rag_is_live

    async def search(self, query: str, *, top_k: int | None = None) -> SearchResult:
        if not self._settings.rag_is_live:
            return SearchResult(query, [], available=False, note="Retrieval is disabled on this deployment.")

        try:
            vector = await self._embeddings.embed_one(query)
        except EmbeddingUnavailable as exc:
            logger.warning("rag_embed_failed", error=str(exc)[:200])
            return SearchResult(query, [], available=False, note=f"Search is unavailable right now: {exc}")

        try:
            found = await self._chunks.similarity_search(
                vector,
                limit=top_k or self._settings.rag_top_k,
                min_score=self._settings.rag_min_score,
            )
        except VectorSearchUnavailable as exc:
            logger.warning("rag_search_unsupported", error=str(exc)[:200])
            return SearchResult(query, [], available=False, note=f"Search is unavailable right now: {exc}")
        except Exception as exc:
            logger.error("rag_search_failed", error=str(exc)[:200])
            return SearchResult(query, [], available=False, note="Search is unavailable right now.")

        if not found:
            return SearchResult(query, [], note="No past paper matched that question.")

        resolved = await self._attach_citations(found)
        return SearchResult(query, resolved)

    async def _attach_citations(self, found: list[ChunkMatch]) -> list[tuple[Citation, str]]:
        paper_ids = {m.past_paper_id for m in found}
        rows = (
            await self._session.execute(
                select(PastPaper, Course)
                .join(Course, PastPaper.course_id == Course.id)
                .where(PastPaper.id.in_(paper_ids))
            )
        ).all()
        by_id = {paper.id: (paper, course) for paper, course in rows}

        results: list[tuple[Citation, str]] = []
        for match in found:
            entry = by_id.get(match.past_paper_id)
            if not entry:
                # A chunk whose paper was deleted outside the cascade.
                # Skipping beats citing a paper that no longer exists.
                continue
            paper, course = entry
            results.append(
                (
                    Citation(
                        past_paper_id=paper.id,
                        course_code=course.code,
                        course_name=course.name,
                        academic_year=paper.academic_year,
                        semester=paper.semester,
                        exam_type=paper.exam_type,
                        chunk_index=match.chunk_index,
                        page_start=match.page_start,
                        page_end=match.page_end,
                        score=match.score,
                    ),
                    match.content,
                )
            )
        return results


def format_for_llm(result: SearchResult) -> dict:
    """Shape a search into the tool payload the model is grounded on.

    The model is told explicitly that these are verbatim excerpts and that
    anything not present here is not in the papers, which is what stops it
    from blending a real quotation with a plausible-sounding invention.
    """
    if not result.available:
        return {"available": False, "note": result.note, "excerpts": []}
    return {
        "available": True,
        "query": result.query,
        "excerpts": [
            {
                "source": citation.label(),
                "course_code": citation.course_code,
                "course_name": citation.course_name,
                "academic_year": citation.academic_year,
                "text": text,
            }
            for citation, text in result.matches
        ],
    }
