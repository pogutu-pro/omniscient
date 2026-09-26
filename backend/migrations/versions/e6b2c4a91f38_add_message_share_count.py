"""add chat_messages.share_count

Revision ID: e6b2c4a91f38
Revises: c4e8a1d70b25
Create Date: 2026-09-26 13:10:00.000000

Counts how many times an answer has been shared. Copying is deliberately
not counted.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6b2c4a91f38"
down_revision: Union[str, None] = "c4e8a1d70b25"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default so the column is usable for rows that already exist,
    # without a separate backfill pass.
    op.add_column(
        "chat_messages",
        sa.Column("share_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "share_count")
