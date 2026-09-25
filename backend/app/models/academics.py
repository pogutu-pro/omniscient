from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class Programme(Base, TimestampMixin):
    __tablename__ = "programmes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    school: Mapped[str] = mapped_column(String(160), nullable=False, default="")


class Course(Base, TimestampMixin):
    """A unit/course within a programme (e.g. "Database Systems")."""

    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    programme_id: Mapped[str] = mapped_column(String(36), ForeignKey("programmes.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    year_of_study: Mapped[int] = mapped_column(Integer, nullable=False)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)


class TimetableEntry(Base, TimestampMixin):
    __tablename__ = "timetable_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id"), nullable=False, index=True)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Monday .. 6=Sunday
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)  # "HH:MM"
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)
    venue: Mapped[str] = mapped_column(String(120), nullable=False)
    session_type: Mapped[str] = mapped_column(String(20), nullable=False, default="lecture")


class AcademicDeadline(Base, TimestampMixin):
    __tablename__ = "academic_deadlines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    programme_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("programmes.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="general")
    due_date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
