from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid
from app.db.vector import VECTOR


class PastPaperChunk(Base, TimestampMixin):
    """One embeddable slice of a past paper's text.

    A paper is stored as many rows rather than one vector per paper
    because a single embedding over a whole 40-page PDF is dominated by
    boilerplate (cover page, instructions) and answers badly for
    "question 3 on integration". Per-chunk vectors keep retrieval sharp
    and let the model cite the specific page range it drew from.

    `ON DELETE CASCADE` is deliberate: deleting a past paper must not
    leave orphaned chunks that a future search would happily quote.
    """

    __tablename__ = "past_paper_chunks"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    past_paper_id: Mapped[str] = mapped_column(
        sa.String(36), sa.ForeignKey("past_papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Position of this chunk within the paper, 0-based. Stable across
    # reindexing so a citation can name "chunk 4" and mean the same thing
    # tomorrow.
    chunk_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # Page range the text came from, when the source format reports it.
    # Best-effort: plain-text sources leave these null rather than
    # inventing a range.
    page_start: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR, nullable=False)
    # Approximate token count, stored only to make index size and prompt
    # budget visible without re-reading the text.
    char_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    __table_args__ = (
        sa.UniqueConstraint("past_paper_id", "chunk_index", name="uq_past_paper_chunk_position"),
        # Supports "which chunks belong to this paper" lookups and the
        # bulk delete that a reindex relies on. The vector index itself is
        # created in the migration, not here: HNSW is PostgreSQL-only and
        # cannot be expressed portably on the model.
        sa.Index("ix_past_paper_chunks_paper_id", "past_paper_id"),
    )
