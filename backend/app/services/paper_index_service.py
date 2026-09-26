"""Building the past-paper vector index.

Reads each paper from object storage, extracts and chunks its text,
embeds the chunks, and writes them to pgvector. The unit of work is one
paper, and each paper is committed independently: a single corrupt or
scanned PDF fails one paper rather than aborting a 200-paper reindex.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.past_paper import PastPaper
from app.repositories.chunk_repository import ChunkRepository, SqlChunkRepository
from app.services.document_chunker import (
    Chunk,
    DocumentExtractionError,
    chunk_pages,
    extract_pages_async,
)
from app.services.embedding_service import EmbeddingService, EmbeddingUnavailable
from app.services.storage.base import StorageBackend

logger = get_logger(component="paper_index")


@dataclass
class PaperIndexResult:
    past_paper_id: str
    file_name: str
    chunks_written: int
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class ReindexReport:
    papers_processed: int = 0
    papers_skipped: int = 0
    chunks_written: int = 0
    failures: list[PaperIndexResult] = field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None

    def as_dict(self) -> dict:
        return {
            "papers_processed": self.papers_processed,
            "papers_skipped": self.papers_skipped,
            "chunks_written": self.chunks_written,
            "failed_papers": [
                {"past_paper_id": f.past_paper_id, "file_name": f.file_name, "error": f.error}
                for f in self.failures
            ],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class PaperIndexService:
    def __init__(
        self,
        session: AsyncSession,
        storage: StorageBackend,
        embeddings: EmbeddingService,
        settings: Settings,
        chunk_repo: ChunkRepository | None = None,
    ):
        self._session = session
        self._storage = storage
        self._embeddings = embeddings
        self._settings = settings
        self._chunks = chunk_repo or SqlChunkRepository(session)

    async def reindex_paper(self, paper: PastPaper) -> PaperIndexResult:
        result = PaperIndexResult(past_paper_id=paper.id, file_name=paper.file_name, chunks_written=0)
        try:
            data = await self._storage.read(paper.file_reference)
        except Exception as exc:
            result.error = f"Could not read file from storage: {exc}"
            return result

        try:
            pages = await extract_pages_async(data, paper.file_name)
        except DocumentExtractionError as exc:
            result.error = str(exc)
            # Leave no half-built index behind for a paper we cannot read.
            await self._chunks.delete_for_paper(paper.id)
            await self._session.commit()
            return result

        chunks = chunk_pages(
            pages,
            chunk_chars=self._settings.rag_chunk_chars,
            overlap_chars=self._settings.rag_chunk_overlap_chars,
        )
        if not chunks:
            result.error = "No usable text after chunking"
            await self._chunks.delete_for_paper(paper.id)
            await self._session.commit()
            return result

        try:
            vectors = await self._embeddings.embed([c.text for c in chunks])
        except EmbeddingUnavailable as exc:
            result.error = str(exc)
            return result

        if len(vectors) != len(chunks):
            result.error = f"Embedding backend returned {len(vectors)} vectors for {len(chunks)} chunks"
            return result

        result.chunks_written = await self._chunks.replace_chunks(paper.id, _rows(chunks, vectors))
        await self._session.commit()
        return result

    async def reindex_all(
        self,
        *,
        force: bool = False,
        paper_ids: list[str] | None = None,
        concurrency: int = 1,
    ) -> ReindexReport:
        """Rebuild the index for every paper, or just `paper_ids`.

        With `force=False` a paper that already has chunks is skipped,
        which is what makes an idempotent nightly job cheap: it only pays
        for papers that are new or were previously unreadable.

        `concurrency` is capped low on purpose. Embedding is CPU-bound, so
        fanning out wide on a 2-OCPU box does not finish sooner — it just
        makes every concurrent chat request slower while all of them
        compete for the same cores.
        """
        report = ReindexReport(started_at=_now())
        papers = await self._pending_papers(force=force, paper_ids=paper_ids)

        if concurrency <= 1:
            for paper in papers:
                self._record(report, await self.reindex_paper(paper))
        else:
            semaphore = asyncio.Semaphore(concurrency)

            async def run(paper: PastPaper) -> PaperIndexResult:
                async with semaphore:
                    return await self.reindex_paper(paper)

            for outcome in await asyncio.gather(*(run(p) for p in papers)):
                self._record(report, outcome)

        report.papers_skipped = len(papers) - report.papers_processed - len(report.failures)
        report.finished_at = _now()
        return report

    async def _pending_papers(self, *, force: bool, paper_ids: list[str] | None) -> list[PastPaper]:
        stmt = select(PastPaper).order_by(PastPaper.created_at)
        if paper_ids:
            stmt = stmt.where(PastPaper.id.in_(paper_ids))
        papers = list((await self._session.execute(stmt)).scalars().all())
        if not paper_ids and not force:
            indexed = set(await self._chunks.distinct_paper_ids())
            papers = [p for p in papers if p.id not in indexed]
        return papers

    @staticmethod
    def _record(report: ReindexReport, outcome: PaperIndexResult) -> None:
        if outcome.ok:
            report.papers_processed += 1
            report.chunks_written += outcome.chunks_written
            logger.info("paper_indexed", paper=outcome.file_name, chunks=outcome.chunks_written)
        else:
            report.failures.append(outcome)
            logger.warning("paper_index_failed", paper=outcome.file_name, error=outcome.error)


def _rows(chunks: list[Chunk], vectors: list[list[float]]) -> list[tuple[int, str, list[float], int | None, int | None]]:
    return [
        (c.index, c.text, v, c.page_start, c.page_end) for c, v in zip(chunks, vectors, strict=True)
    ]


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
