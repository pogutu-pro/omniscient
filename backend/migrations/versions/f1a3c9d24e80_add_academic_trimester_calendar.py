"""add academic trimester calendar

Revision ID: f1a3c9d24e80
Revises: d2b7f40a9c15
Create Date: 2026-09-26 16:40:00.000000

DeKUT runs a trimester system: the academic year opens in September and
divides into three roughly four-month trimesters - Semester 1 (January-April),
Semester 2 (May-August) and Semester 3 (September-December). Nothing in the
database said so, so the assistant had no way to answer "which semester are we
in?" or to explain why the September-December teaching timetable is filed
under a cohort the sheet itself calls "Semester 1" or "Semester 2".

This adds the calendar as data rather than as prompt text, because the usual
periods are a rule but the real dates are not: reporting and resumption dates
move by programme, school, intake and year, and slip when there is industrial
action. An admin can therefore correct a term in place, and every consumer -
the Academics screen, the API and the assistant's tool - reads the same row.
"""
import datetime as dt
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a3c9d24e80"
down_revision: str = "d2b7f40a9c15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _trimester_rows() -> list[dict]:
    """The three trimesters of an academic year, as DeKUT defines them.

    An academic year is labelled by the September it opens in, so its
    Semester 3 (September-December) falls in the *earlier* calendar year than
    its Semesters 1 and 2. That is the whole reason a September-December
    teaching timetable is officially Semester 3 even though a department's
    own sheet may label the cohort "Semester 1".
    """
    today = dt.date.today()
    # Seed this academic year plus one either side, so the app is useful
    # before an admin has entered anything and still after the year rolls.
    opening_year = today.year if today.month >= 9 else today.year - 1
    notes = (
        "Usual trimester period. Exact reporting and resumption dates are set per programme, "
        "school and intake, and can change - confirm with your registrar or faculty notice."
    )
    rows: list[dict] = []
    for opening in range(opening_year - 1, opening_year + 2):
        academic_year = f"{opening}/{opening + 1}"
        periods = [
            (1, dt.date(opening + 1, 1, 1), dt.date(opening + 1, 4, 30)),
            (2, dt.date(opening + 1, 5, 1), dt.date(opening + 1, 8, 31)),
            (3, dt.date(opening, 9, 1), dt.date(opening, 12, 31)),
        ]
        for trimester, start, end in periods:
            rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "academic_year": academic_year,
                    "trimester": trimester,
                    "label": f"Semester {trimester}",
                    "start_date": start,
                    "end_date": end,
                    # Left empty on purpose: the reporting date is not a
                    # rule, it is announced per programme, and inventing one
                    # here would be a fact the assistant would then repeat.
                    "reporting_date": None,
                    "provisional": True,
                    "notes": notes,
                    "created_at": dt.datetime.now(dt.timezone.utc),
                    "updated_at": dt.datetime.now(dt.timezone.utc),
                }
            )
    return rows


_TRIMESTER_ROWS = _trimester_rows()


def upgrade() -> None:
    op.create_table(
        "academic_terms",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("academic_year", sa.String(length=9), nullable=False),
        sa.Column("trimester", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("reporting_date", sa.Date(), nullable=True),
        sa.Column("provisional", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("academic_year", "trimester", name="uq_academic_terms_year_trimester"),
    )
    op.create_index("ix_academic_terms_academic_year", "academic_terms", ["academic_year"])

    # The trimester calendar is a rule, not a per-tenant choice, so it is
    # seeded for the current academic year and the two around it. Dates are
    # the published pattern (the 1st of the month) and are marked provisional,
    # because the real reporting and resumption dates are set per programme
    # and shift; `seed.py` keeps the same rows up to date on every run.
    op.bulk_insert(
        sa.table(
            "academic_terms",
            sa.column("id", sa.String(36)),
            sa.column("academic_year", sa.String(9)),
            sa.column("trimester", sa.Integer()),
            sa.column("label", sa.String(60)),
            sa.column("start_date", sa.Date()),
            sa.column("end_date", sa.Date()),
            sa.column("reporting_date", sa.Date()),
            sa.column("provisional", sa.Boolean()),
            sa.column("notes", sa.String(500)),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        _TRIMESTER_ROWS,
    )


def downgrade() -> None:
    op.drop_index("ix_academic_terms_academic_year", table_name="academic_terms")
    op.drop_table("academic_terms")
