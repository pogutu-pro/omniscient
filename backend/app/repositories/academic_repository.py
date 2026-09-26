from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academics import AcademicDeadline, AcademicTerm, Course, Programme, TimetableEntry
from app.schemas.academics import (
    AcademicDeadlineCreate,
    AcademicDeadlineOut,
    AcademicDeadlineQuery,
    AcademicTermCreate,
    AcademicTermOut,
    AcademicsMeta,
    CourseCreate,
    CourseOut,
    ProgrammeCreate,
    ProgrammeOut,
    TimetableEntryCreate,
    TimetableEntryOut,
    TimetableQuery,
)
from app.services.term_calendar import TRIMESTER_PERIODS, current_trimester, opening_year_of, term_period

_TERM_NOTES = (
    "Usual trimester period. Exact reporting and resumption dates are set per programme, school and "
    "intake, and can change - confirm with your registrar or faculty notice."
)


def default_terms(academic_year: str | None = None, today: dt.date | None = None) -> list[AcademicTermOut]:
    """The trimester calendar derived from the rule, for a year or three.

    Used when no admin has entered dates yet. These rows are marked
    provisional and carry no reporting date, so nothing downstream can present
    a generated term as confirmed.
    """
    if academic_year:
        years = [academic_year]
    else:
        opening = opening_year_of(current_trimester(today)[0])
        years = [f"{year}/{year + 1}" for year in range(opening - 1, opening + 2)]
    terms: list[AcademicTermOut] = []
    for year in years:
        for trimester, _first, _last in TRIMESTER_PERIODS:
            start, end = term_period(year, trimester)
            terms.append(
                AcademicTermOut(
                    id=f"{year}:{trimester}",
                    academic_year=year,
                    trimester=trimester,
                    label=f"Semester {trimester}",
                    start_date=start,
                    end_date=end,
                    reporting_date=None,
                    provisional=True,
                    notes=_TERM_NOTES,
                )
            )
    return terms


def _entry_out(entry: TimetableEntry, course: Course | None) -> TimetableEntryOut:
    """Project a joined (entry, course) pair onto the flat read model.

    The course's code, name and lecturer are denormalised onto the response
    so the timetable screen and the agent's table can render a session
    without a second round trip or a second join.
    """
    return TimetableEntryOut(
        id=entry.id,
        course_id=entry.course_id,
        course_code=course.code if course else "",
        course_name=course.name if course else "",
        day_of_week=entry.day_of_week,
        start_time=entry.start_time,
        end_time=entry.end_time,
        venue=entry.venue,
        session_type=entry.session_type,
        academic_year=entry.academic_year,
        semester=entry.semester,
        year_group=entry.year_group,
        stream=entry.stream,
        lecturer=course.lecturer if course else None,
    )


class AcademicRepository(ABC):
    @abstractmethod
    async def get_programme_by_code(self, code: str) -> ProgrammeOut | None: ...

    @abstractmethod
    async def list_programmes(self) -> list[ProgrammeOut]: ...

    @abstractmethod
    async def list_courses(self, programme_code: str | None, year_of_study: int | None) -> list[CourseOut]: ...

    @abstractmethod
    async def get_timetable(self, query: TimetableQuery) -> list[TimetableEntryOut]: ...

    @abstractmethod
    async def list_deadlines(self, query: AcademicDeadlineQuery) -> list[AcademicDeadlineOut]: ...

    @abstractmethod
    async def get_meta(self) -> AcademicsMeta: ...

    @abstractmethod
    async def list_terms(self, academic_year: str | None = None) -> list[AcademicTermOut]: ...

    @abstractmethod
    async def get_current_term(self, today: dt.date | None = None) -> AcademicTermOut: ...

    # --- Admin writes ---
    @abstractmethod
    async def create_programme(self, data: ProgrammeCreate) -> ProgrammeOut: ...

    @abstractmethod
    async def create_course(self, data: CourseCreate) -> CourseOut: ...

    @abstractmethod
    async def delete_course(self, course_id: str) -> bool: ...

    @abstractmethod
    async def create_timetable_entry(self, data: TimetableEntryCreate) -> TimetableEntryOut: ...

    @abstractmethod
    async def delete_timetable_entry(self, entry_id: str) -> bool: ...

    @abstractmethod
    async def create_deadline(self, data: AcademicDeadlineCreate) -> AcademicDeadlineOut: ...

    @abstractmethod
    async def upsert_term(self, data: AcademicTermCreate) -> AcademicTermOut: ...

    @abstractmethod
    async def delete_deadline(self, deadline_id: str) -> bool: ...


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
        stmt = stmt.order_by(Course.year_of_study, Course.semester, Course.code)
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
        if query.academic_year:
            stmt = stmt.where(TimetableEntry.academic_year == query.academic_year)
        if query.year_group:
            stmt = stmt.where(TimetableEntry.year_group == query.year_group)
        if query.stream:
            stmt = stmt.where(TimetableEntry.stream == query.stream)
        if query.course_code:
            stmt = stmt.where(Course.code == query.course_code)
        stmt = stmt.order_by(
            TimetableEntry.day_of_week,
            TimetableEntry.start_time,
            Course.code,
        )
        result = await self._session.execute(stmt)
        return [_entry_out(entry, course) for entry, course in result.all()]

    async def list_deadlines(self, query: AcademicDeadlineQuery) -> list[AcademicDeadlineOut]:
        stmt = select(AcademicDeadline)
        if query.programme_code:
            # A NULL programme_id means the deadline applies to every
            # programme, so filtering on the code has to keep those rows
            # rather than drop them the way a plain equality would.
            stmt = stmt.outerjoin(Programme, AcademicDeadline.programme_id == Programme.id).where(
                (Programme.code == query.programme_code) | (AcademicDeadline.programme_id.is_(None))
            )
        if query.category:
            stmt = stmt.where(AcademicDeadline.category == query.category)
        if not query.include_past:
            stmt = stmt.where(AcademicDeadline.due_date >= dt.date.today())
        stmt = stmt.order_by(AcademicDeadline.due_date.asc()).limit(query.limit)
        result = await self._session.execute(stmt)
        return [AcademicDeadlineOut.model_validate(d) for d in result.scalars().all()]

    async def list_terms(self, academic_year: str | None = None) -> list[AcademicTermOut]:
        """The trimester calendar, in academic year then trimester order.

        The usual periods are a rule, so an empty table still yields the
        right answer: stored rows are returned when they exist and generated
        ones otherwise, so a database that has never been seeded can still
        answer "which semester are we in?".
        """
        stmt = select(AcademicTerm)
        if academic_year:
            stmt = stmt.where(AcademicTerm.academic_year == academic_year)
        result = await self._session.execute(stmt.order_by(AcademicTerm.academic_year, AcademicTerm.trimester))
        stored = [AcademicTermOut.model_validate(term) for term in result.scalars().all()]
        # Fall back to the rule, but only for the year that was asked for. A
        # bare default_terms() here would answer a query for a year with no
        # stored rows with every year it knows, which the caller then has to
        # filter - and which reports the wrong calendar as if it were the
        # requested one.
        return stored or default_terms(academic_year)

    async def get_current_term(self, today: dt.date | None = None) -> AcademicTermOut:
        """The trimester today falls in, preferring an admin's entered dates.

        Falls back to the usual periods so the assistant can always answer,
        but a generated term stays provisional and carries no reporting date,
        because that is genuinely unknown until it is announced.
        """
        day = today or dt.date.today()
        academic_year, trimester = current_trimester(day)
        for term in await self.list_terms(academic_year):
            if term.trimester == trimester:
                return term
        return default_terms(academic_year, today=day)[trimester - 1]

    async def upsert_term(self, data: AcademicTermCreate) -> AcademicTermOut:
        """Enter or correct a term's dates.

        Keyed on (academic year, trimester) so correcting a reporting date
        updates the existing row instead of stacking a second, contradictory
        one - which is what would otherwise happen on the day a date slips.
        """
        existing = (
            await self._session.execute(
                select(AcademicTerm).where(
                    AcademicTerm.academic_year == data.academic_year,
                    AcademicTerm.trimester == data.trimester,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            term = AcademicTerm(**data.model_dump())
            self._session.add(term)
        else:
            term = existing
            for field, value in data.model_dump().items():
                setattr(term, field, value)
        await self._session.commit()
        await self._session.refresh(term)
        return AcademicTermOut.model_validate(term)

    async def get_meta(self) -> AcademicsMeta:
        """Collect the distinct values in use, so the screen's controls can
        only ever offer a filter that returns rows.

        Year groups sort by year then semester rather than as text, because
        "1.10" sorting before "1.2" is not an ordering anyone wants to read.
        """

        async def distinct(column) -> list[str]:
            result = await self._session.execute(select(column).distinct())
            return [value for value in result.scalars().all() if value]

        year_groups = await distinct(TimetableEntry.year_group)
        year_groups.sort(key=lambda group: (int(group.split(".")[0]), int(group.split(".")[1])))
        academic_years = sorted(await distinct(TimetableEntry.academic_year), reverse=True)
        streams = sorted(await distinct(TimetableEntry.stream))
        session_types = sorted(await distinct(TimetableEntry.session_type))
        venues = sorted(await distinct(TimetableEntry.venue))
        deadline_categories = sorted(await distinct(AcademicDeadline.category))
        current_term = await self.get_current_term()
        return AcademicsMeta(
            academic_years=academic_years,
            year_groups=year_groups,
            streams=streams,
            session_types=session_types,
            deadline_categories=deadline_categories,
            venues=venues,
            current_academic_year=current_term.academic_year,
            current_trimester=current_term.trimester,
            terms=await self.list_terms(),
        )


    async def list_programmes(self) -> list[ProgrammeOut]:
        result = await self._session.execute(select(Programme).order_by(Programme.name))
        return [ProgrammeOut.model_validate(p) for p in result.scalars().all()]

    async def create_programme(self, data: ProgrammeCreate) -> ProgrammeOut:
        programme = Programme(**data.model_dump())
        self._session.add(programme)
        await self._session.commit()
        await self._session.refresh(programme)
        return ProgrammeOut.model_validate(programme)

    async def create_course(self, data: CourseCreate) -> CourseOut:
        course = Course(**data.model_dump())
        self._session.add(course)
        await self._session.commit()
        await self._session.refresh(course)
        return CourseOut.model_validate(course)

    async def delete_course(self, course_id: str) -> bool:
        course = await self._session.get(Course, course_id)
        if not course:
            return False
        await self._session.delete(course)
        await self._session.commit()
        return True

    async def create_timetable_entry(self, data: TimetableEntryCreate) -> TimetableEntryOut:
        entry = TimetableEntry(**data.model_dump())
        self._session.add(entry)
        await self._session.commit()
        await self._session.refresh(entry)
        return _entry_out(entry, await self._session.get(Course, entry.course_id))

    async def delete_timetable_entry(self, entry_id: str) -> bool:
        entry = await self._session.get(TimetableEntry, entry_id)
        if not entry:
            return False
        await self._session.delete(entry)
        await self._session.commit()
        return True

    async def create_deadline(self, data: AcademicDeadlineCreate) -> AcademicDeadlineOut:
        deadline = AcademicDeadline(**data.model_dump())
        self._session.add(deadline)
        await self._session.commit()
        await self._session.refresh(deadline)
        return AcademicDeadlineOut.model_validate(deadline)

    async def delete_deadline(self, deadline_id: str) -> bool:
        deadline = await self._session.get(AcademicDeadline, deadline_id)
        if not deadline:
            return False
        await self._session.delete(deadline)
        await self._session.commit()
        return True
