from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academics import AcademicDeadline, Course, Programme, TimetableEntry
from app.schemas.academics import AcademicDeadlineOut, CourseOut, ProgrammeOut, TimetableEntryOut, TimetableQuery


class AcademicRepository(ABC):
    @abstractmethod
    async def get_programme_by_code(self, code: str) -> ProgrammeOut | None: ...

    @abstractmethod
    async def list_courses(self, programme_code: str | None, year_of_study: int | None) -> list[CourseOut]: ...

    @abstractmethod
    async def get_timetable(self, query: TimetableQuery) -> list[TimetableEntryOut]: ...

    @abstractmethod
    async def list_deadlines(self, programme_code: str | None, limit: int) -> list[AcademicDeadlineOut]: ...


class SqlAcademicRepository(AcademicRepository):
    """Omniscient's own academics data — never sourced from Rumia."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_programme_by_code(self, code: str) -> ProgrammeOut | None:
        stmt = select(Programme).where(Programme.code == code)
        result = await self._session.execute(stmt)
        programme = result.scalar_one_or_none()
        return ProgrammeOut.model_validate(programme) if programme else None

    async def list_courses(self, programme_code: str | None, year_of_study: int | None) -> list[CourseOut]:
        stmt = select(Course)
        if programme_code:
            stmt = stmt.join(Programme, Course.programme_id == Programme.id).where(Programme.code == programme_code)
        if year_of_study:
            stmt = stmt.where(Course.year_of_study == year_of_study)
        result = await self._session.execute(stmt)
        return [CourseOut.model_validate(c) for c in result.scalars().all()]

    async def get_timetable(self, query: TimetableQuery) -> list[TimetableEntryOut]:
        stmt = select(TimetableEntry, Course).join(Course, TimetableEntry.course_id == Course.id)
        if query.programme_code:
            stmt = stmt.join(Programme, Course.programme_id == Programme.id).where(
                Programme.code == query.programme_code
            )
        if query.year_of_study:
            stmt = stmt.where(Course.year_of_study == query.year_of_study)
        if query.day_of_week is not None:
            stmt = stmt.where(TimetableEntry.day_of_week == query.day_of_week)
        stmt = stmt.order_by(TimetableEntry.day_of_week, TimetableEntry.start_time)
        result = await self._session.execute(stmt)
        entries = []
        for entry, course in result.all():
            entries.append(
                TimetableEntryOut(
                    id=entry.id,
                    course_id=entry.course_id,
                    course_code=course.code,
                    course_name=course.name,
                    day_of_week=entry.day_of_week,
                    start_time=entry.start_time,
                    end_time=entry.end_time,
                    venue=entry.venue,
                    session_type=entry.session_type,
                )
            )
        return entries

    async def list_deadlines(self, programme_code: str | None, limit: int) -> list[AcademicDeadlineOut]:
        stmt = select(AcademicDeadline)
        if programme_code:
            stmt = stmt.join(Programme, AcademicDeadline.programme_id == Programme.id).where(
                Programme.code == programme_code
            )
        stmt = stmt.order_by(AcademicDeadline.due_date.asc()).limit(limit)
        result = await self._session.execute(stmt)
        return [AcademicDeadlineOut.model_validate(d) for d in result.scalars().all()]
