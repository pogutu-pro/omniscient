"""add message_ratings table

Revision ID: c4e8a1d70b25
Revises: b3f1c7a92d40
Create Date: 2026-09-26 12:05:00.000000

Stores a student's thumbs-up / thumbs-down on an assistant reply. One row
per (message, student) so re-rating replaces the previous verdict rather
than adding a second one, which would make the admin insight counts wrong.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e8a1d70b25"
down_revision: Union[str, None] = "b3f1c7a92d40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "message_ratings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("student_id", sa.String(length=36), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # The database is the last line of defence for the "1 or -1 only"
        # rule the API enforces - a rating outside that range would corrupt
        # the up/down totals the admin dashboard reports.
        sa.CheckConstraint("rating IN (-1, 1)", name="ck_message_ratings_rating"),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "student_id", name="uq_message_ratings_message_student"),
    )
    op.create_index("ix_message_ratings_message_id", "message_ratings", ["message_id"])
    op.create_index("ix_message_ratings_student_id", "message_ratings", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_message_ratings_student_id", table_name="message_ratings")
    op.drop_index("ix_message_ratings_message_id", table_name="message_ratings")
    op.drop_table("message_ratings")
