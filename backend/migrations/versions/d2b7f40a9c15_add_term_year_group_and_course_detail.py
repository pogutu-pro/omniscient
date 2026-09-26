"""add term, year group and course teaching detail

Revision ID: d2b7f40a9c15
Revises: c4e8a1d70b25
Create Date: 2026-09-26 14:20:00.000000

DeKUT's departmental teaching timetables are issued per term and scheduled
per year group (1.1, 2.2, 3.2, 4.2), with year 1 splitting into a Computer
Science and a Food Science stream. `timetable_entries` could express none of
that: it had no term and no cohort, so two different cohorts' sessions for
the same course were indistinguishable and a new term's timetable could not
be told apart from the current one.

The four new columns are therefore backfilled from the course a row already
points at - `courses.year_of_study` and `courses.semester` give the year
group, and the term is the one this deployment is running. Rows imported
from a real departmental sheet carry their own values instead.

The teaching detail added to `courses` comes from the course-catalogue block
at the bottom of those sheets (lecturer, weekly lecture/lab hours, class
size). It is all nullable: a course created by hand through the admin API
has none of it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2b7f40a9c15"
down_revision: Union[str, None] = "c4e8a1d70b25"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The term this deployment is serving. Existing demo rows have no term of
# their own, so they are attributed here rather than left NULL: a timetable
# entry that belongs to no term cannot be filtered, ordered or replaced when
# the next term's sheet arrives.
DEFAULT_ACADEMIC_YEAR = "2026/2027"


def upgrade() -> None:
    op.add_column("courses", sa.Column("lecturer", sa.String(length=120), nullable=True))
    op.add_column("courses", sa.Column("lecture_hours", sa.Integer(), nullable=True))
    op.add_column("courses", sa.Column("lab_hours", sa.Integer(), nullable=True))
    op.add_column("courses", sa.Column("class_size", sa.Integer(), nullable=True))

    # Added NOT NULL with a server default so the table never holds a
    # half-populated row, then given the correct per-row values below and
    # stripped of the default so new inserts must state their own term.
    op.add_column(
        "timetable_entries",
        sa.Column("academic_year", sa.String(length=9), nullable=False, server_default=DEFAULT_ACADEMIC_YEAR),
    )
    op.add_column(
        "timetable_entries", sa.Column("semester", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column(
        "timetable_entries", sa.Column("year_group", sa.String(length=8), nullable=False, server_default="1.1")
    )
    op.add_column("timetable_entries", sa.Column("stream", sa.String(length=20), nullable=True))

    # A row's cohort is its course's year of study and semester ("2" and "2"
    # -> "2.2"), which is how the sheets label the GROUP column.
    op.execute(
        """
        UPDATE timetable_entries AS te
        SET semester = c.semester,
            year_group = c.year_of_study::text || '.' || c.semester::text
        FROM courses AS c
        WHERE c.id = te.course_id
        """
    )

    op.alter_column("timetable_entries", "academic_year", server_default=None)
    op.alter_column("timetable_entries", "semester", server_default=None)
    op.alter_column("timetable_entries", "year_group", server_default=None)

    # The timetable screen filters on (term, year group) and orders by day
    # and start time; one composite index serves both.
    op.create_index(
        "ix_timetable_entries_term_year_group",
        "timetable_entries",
        ["academic_year", "year_group"],
    )


def downgrade() -> None:
    op.drop_index("ix_timetable_entries_term_year_group", table_name="timetable_entries")
    op.drop_column("timetable_entries", "stream")
    op.drop_column("timetable_entries", "year_group")
    op.drop_column("timetable_entries", "semester")
    op.drop_column("timetable_entries", "academic_year")
    op.drop_column("courses", "class_size")
    op.drop_column("courses", "lab_hours")
    op.drop_column("courses", "lecture_hours")
    op.drop_column("courses", "lecturer")
