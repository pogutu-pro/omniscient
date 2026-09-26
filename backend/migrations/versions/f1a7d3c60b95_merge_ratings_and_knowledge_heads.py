"""merge message-rating/share heads with the knowledge-base head

Revision ID: f1a7d3c60b95
Revises: b8e2d4f7a913, e6b2c4a91f38
Create Date: 2026-09-26 13:20:00.000000

Two branches were developed against the same parent - the knowledge-base
work and the message rating/share counters - which leaves Alembic with two
heads and makes `alembic upgrade head` fail with "Multiple head revisions are
present". This merge revision joins them.

It changes no schema: every table and column is created by the migrations on
each branch, so upgrade() and downgrade() are intentionally empty.
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "f1a7d3c60b95"
down_revision: Union[str, tuple[str, str], None] = ("b8e2d4f7a913", "e6b2c4a91f38")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
