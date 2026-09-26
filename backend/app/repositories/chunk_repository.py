from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.past_paper_chunk import PastPaperChunk


class VectorSearchUnavailable(RuntimeError):
    """Raised when similarity search is asked for on a database that
    cannot do it — currently only reachable on SQLite, where the vector
    column is stored as text. Deliberately an error rather than an empty
    result: an empty list would be indistinguishable from "nothing
    matched", which is how a broken index turns into a silently useless
    search feature."""


@dataclass(frozen=True)
class ChunkMatch:
    """One retrieved chunk, with the metadata a citation needs."""

    chunk_id: str
    past_paper_id: str
    chunk_index: int
    content: str
    # Cosine similarity in [-1, 1]; higher is closer.
    score: float
    page_start: int | None = None
    page_end: int | None = None


class ChunkRepository(ABC):
    @abstractmethod
    async def replace_chunks(self, past_paper_id: str, chunks: list[tuple[int, str, list[float], int | None, int | None]]) -> int: ...

    @abstractmethod
    async def delete_for_paper(self, past_paper_id: str) -> int: ...

    @abstractmethod
    async def count_for_paper(self, past_paper_id: str) -> int: ...

    @abstractmethod
    async def total_count(self) -> int: ...

    @abstractmethod
    async def distinct_paper_ids(self) -> list[str]: ...

    @abstractmethod
    async def similarity_search(self, embedding: list[float], limit: int, min_score: float) -> list[ChunkMatch]: ...


class SqlChunkRepository(ChunkRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def replace_chunks(
        self, past_paper_id: str, chunks: list[tuple[int, str, list[float], int | None, int | None]]
    ) -> int:
        """Swap a paper's chunks for a freshly computed set, atomically.

        Delete-then-insert rather than diffing: a reindex is a rare admin
        action, and "the old chunks are gone and the new ones are in"
        is a much easier invariant to reason about than a merge that has
        to handle papers that shrank as well as grew.
        """
        await self.delete_for_paper(past_paper_id)
        if not chunks:
            return 0
        self._session.add_all(
            [
                PastPaperChunk(
                    past_paper_id=past_paper_id,
                    chunk_index=index,
                    content=content,
                    embedding=embedding,
                    page_start=page_start,
                    page_end=page_end,
                    char_count=len(content),
                )
                for index, content, embedding, page_start, page_end in chunks
            ]
        )
        await self._session.flush()
        return len(chunks)

    async def delete_for_paper(self, past_paper_id: str) -> int:
        result = await self._session.execute(
            delete(PastPaperChunk).where(PastPaperChunk.past_paper_id == past_paper_id)
        )
        return result.rowcount or 0

    async def count_for_paper(self, past_paper_id: str) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(PastPaperChunk).where(PastPaperChunk.past_paper_id == past_paper_id)
        )
        return int(result.scalar_one())

    async def total_count(self) -> int:
        result = await self._session.execute(select(func.count()).select_from(PastPaperChunk))
        return int(result.scalar_one())

    async def distinct_paper_ids(self) -> list[str]:
        result = await self._session.execute(select(PastPaperChunk.past_paper_id).distinct())
        return [row[0] for row in result.all()]

    async def similarity_search(self, embedding: list[float], limit: int, min_score: float) -> list[ChunkMatch]:
        dialect = self._session.bind.dialect.name if self._session.bind is not None else ""
        if dialect != "postgresql":
            raise VectorSearchUnavailable(
                f"Vector similarity search requires PostgreSQL with pgvector; this session is bound to {dialect!r}."
            )

        # <=> is pgvector's cosine-distance operator, so the ordering and
        # the HNSW index in the migration are both used. Converting to a
        # similarity keeps the caller's threshold in the intuitive 0..1
        # range instead of exposing a distance.
        distance = PastPaperChunk.embedding.cosine_distance(embedding)
        similarity = 1 - distance
        stmt = (
            select(
                PastPaperChunk.id,
                PastPaperChunk.past_paper_id,
                PastPaperChunk.chunk_index,
                PastPaperChunk.content,
                similarity.label("score"),
                PastPaperChunk.page_start,
                PastPaperChunk.page_end,
            )
            .where(similarity >= min_score)
            .order_by(similarity.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            ChunkMatch(
                chunk_id=r.id,
                past_paper_id=r.past_paper_id,
                chunk_index=r.chunk_index,
                content=r.content,
                score=float(r.score),
                page_start=r.page_start,
                page_end=r.page_end,
            )
            for r in rows
        ]
