"""widen knowledge_sections.sort_key to bigint

Revision ID: b1f4e6a90c27
Revises: f1a7d3c60b95
Create Date: 2026-09-26 19:10:00.000000

A section's `sort_key` is `number * 10_000^2`, so any section numbered 22 or
higher is larger than the 32-bit signed maximum (2,147,483,647). The column
was declared INTEGER, which PostgreSQL enforces and SQLite does not — so the
knowledge ingest passed in tests and failed on the first real deployment with
"value out of int32 range". BIGINT holds the formula's full range and the
ordering is unchanged.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b1f4e6a90c27"
down_revision = "f1a7d3c60b95"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "knowledge_sections",
        "sort_key",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "knowledge_sections",
        "sort_key",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
