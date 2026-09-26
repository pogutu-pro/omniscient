"""merge the trimester calendar and knowledge base branches

Revision ID: b8e2d4f7a913
Revises: f1a3c9d24e80, a7c31e9b4d28
Create Date: 2026-09-26 16:58:00.000000

Two migrations were written in parallel against the same parent, so the
repository briefly had two heads and `alembic upgrade head` refused to run:

    59edf8f9d423 -> ... -> d2b7f40a9c15 -> f1a3c9d24e80  (trimester calendar)
                                       -> a7c31e9b4d28  (knowledge base)

A merge revision is the right fix rather than re-basing either branch: it
leaves both files exactly as their authors wrote them, works no matter which
order they are applied in, and is what alembic expects when two heads meet.
It creates no schema of its own.
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "b8e2d4f7a913"
down_revision: Union[str, Sequence[str], None] = ("f1a3c9d24e80", "a7c31e9b4d28")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Nothing to do: both branches are applied by their own migrations."""


def downgrade() -> None:
    """Nothing to undo: this revision only unified the history."""
