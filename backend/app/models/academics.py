from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class Programme(Base, TimestampMixin):
    __tablename__ = "programmes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    school: Mapped[str] = mapped_column(String(160), nullable=False, default="")


class Course(Base, TimestampMixin):
    """A unit/course within a programme (e.g. "Database Systems").

    The teaching detail below (who teaches it, how many hours a week, how big
    the class is) is optional because it is not always published. DeKUT's
    departmental teaching timetables carry it in a course-catalogue block at
    the bottom of the sheet, so the spreadsheet importer fills it in, but a
    course created by hand through the admin API may not have it.
    """

    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    programme_id: Mapped[str] = mapped_column(String(36), ForeignKey("programmes.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    year_of_study: Mapped[int] = mapped_column(Integer, nullable=False)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    lecturer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lecture_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lab_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_size: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TimetableEntry(Base, TimestampMixin):
    """One session of one course, for one year group, in one term.

    A session is scheduled *for a cohort*, not just for a course: the same
    course can be timetabled separately for different year groups, and a year
    group can split into streams (DeKUT's year 1 runs a Computer Science and
    a Food Science stream side by side). So the cohort is spelled out here
    rather than being inferred from the course, which is a catalogue entry
    that outlives any single term.

    `day_of_week` is 0=Monday .. 6=Sunday, matching the convention used by
    the frontend and the agent's timetable table.
    """

    __tablename__ = "timetable_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id"), nullable=False, index=True)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Monday .. 6=Sunday
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)  # "HH:MM"
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)
    venue: Mapped[str] = mapped_column(String(120), nullable=False)
    session_type: Mapped[str] = mapped_column(String(20), nullable=False, default="lecture")
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)  # "2026/2027"
    semester: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2 or 3 within the academic year
    year_group: Mapped[str] = mapped_column(String(8), nullable=False, index=True)  # "4.2"
    stream: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "CS" / "FS", when the group splits


class AcademicTerm(Base, TimestampMixin):
    """One trimester of one DeKUT academic year.

    DeKUT runs a trimester system, not the two-semester year used by many
    universities: the academic year opens in September and is split into
    three roughly four-month trimesters (Semester 1 January-April, Semester 2
    May-August, Semester 3 September-December).

    The *usual* periods are a rule, so they are seeded here as data the agent
    can quote. The *actual* start, end and reporting dates are not a rule:
    they move by programme, school, intake and year, and are pushed back by
    industrial action or other disruptions. That is why they live in an
    editable row with a `provisional` flag and a `notes` field rather than
    being computed, and why the seeded rows say plainly that the dates are the
    published plan and not a promise.
    """

    __tablename__ = "academic_terms"
    __table_args__ = (UniqueConstraint("academic_year", "trimester", name="uq_academic_terms_year_trimester"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)  # "2026/2027"
    trimester: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2 or 3
    label: Mapped[str] = mapped_column(String(60), nullable=False, default="")  # "Semester 1"
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    reporting_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    provisional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str] = mapped_column(String(500), nullable=False, default="")


class AcademicDeadline(Base, TimestampMixin):
    __tablename__ = "academic_deadlines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    programme_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("programmes.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="general")
    due_date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
