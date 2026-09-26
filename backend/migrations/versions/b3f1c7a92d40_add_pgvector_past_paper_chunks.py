"""add pgvector extension and past paper chunk table

Revision ID: b3f1c7a92d40
Revises: 07fb0d35a995
Create Date: 2026-09-26 10:14:33.902117

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "b3f1c7a92d40"
down_revision: Union[str, None] = "07fb0d35a995"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Must match app.db.vector.VECTOR_DIMENSIONS and EMBEDDING_DIMENSIONS.
VECTOR_DIMENSIONS = 384


def upgrade() -> None:
    # IF NOT EXISTS so re-running a partially applied deploy is a no-op
    # rather than an error. Requires superuser, which the compose
    # POSTGRES_USER is; on a managed instance grant it once out of band.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "past_paper_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("past_paper_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(VECTOR_DIMENSIONS), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # ON DELETE CASCADE: removing a past paper must take its chunks
        # with it, or search would keep quoting a paper that no longer
        # exists for download.
        sa.ForeignKeyConstraint(
            ["past_paper_id"], ["past_papers.id"], ondelete="CASCADE", name="fk_past_paper_chunks_paper"
        ),
        sa.PrimaryKeyConstraint("id"),
        # Guards against a reindex writing two chunks at the same position.
        sa.UniqueConstraint("past_paper_id", "chunk_index", name="uq_past_paper_chunk_position"),
    )
    op.create_index("ix_past_paper_chunks_paper_id", "past_paper_chunks", ["past_paper_id"])
    op.create_index("ix_past_paper_chunks_past_paper_id", "past_paper_chunks", ["past_paper_id"])

    # HNSW rather than IVFFlat: it builds incrementally, so it does not
    # need the whole table present before the first search, and it does not
    # need periodic re-centring. vector_cosine_ops matches the <=>
    # distance operator the repository orders by — an operator-class
    # mismatch here is the classic cause of "the index exists but the
    # planner ignores it".
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_past_paper_chunks_embedding_hnsw "
        "ON past_paper_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_past_paper_chunks_embedding_hnsw")
    op.drop_index("ix_past_paper_chunks_past_paper_id", table_name="past_paper_chunks")
    op.drop_index("ix_past_paper_chunks_paper_id", table_name="past_paper_chunks")
    op.drop_table("past_paper_chunks")
    # The extension is intentionally left in place. It is a shared
    # database-level object, so dropping it on a downgrade of one feature
    # would take any other pgvector usage with it. Harmless to leave.
