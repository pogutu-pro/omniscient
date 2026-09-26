from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_academic_repo
from app.repositories.academic_repository import AcademicRepository
from app.schemas.academics import (
    AcademicDeadlineOut,
    AcademicDeadlineQuery,
    AcademicTermOut,
    AcademicsMeta,
    CourseOut,
    TimetableEntryOut,
    TimetableQuery,
)

router = APIRouter(prefix="/api/academics", tags=["academics"])


@router.get("/meta", response_model=AcademicsMeta)
async def get_meta(repo: AcademicRepository = Depends(get_academic_repo)) -> AcademicsMeta:
    """The terms, year groups, streams, venues and categories in use.

    The timetable screen needs all of these to render its controls, and
    deriving them from the data means a control can never offer a filter that
    returns nothing.
    """
    return await repo.get_meta()


@router.get("/timetable", response_model=list[TimetableEntryOut])
async def get_timetable(
    programme_code: str | None = Query(default=None),
    year_of_study: int | None = Query(default=None, ge=1, le=6),
    day_of_week: int | None = Query(default=None, ge=0, le=6),
    academic_year: str | None = Query(default=None, pattern=r"^\d{4}/\d{4}$"),
    year_group: str | None = Query(default=None, pattern=r"^[1-6]\.[1-3]$"),
    stream: str | None = Query(default=None),
    course_code: str | None = Query(default=None),
    repo: AcademicRepository = Depends(get_academic_repo),
) -> list[TimetableEntryOut]:
    query = TimetableQuery(
        programme_code=programme_code,
        year_of_study=year_of_study,
        day_of_week=day_of_week,
        academic_year=academic_year,
        year_group=year_group,
        stream=stream,
        course_code=course_code,
    )
    return await repo.get_timetable(query)


@router.get("/terms", response_model=list[AcademicTermOut])
async def list_terms(
    academic_year: str | None = Query(default=None, pattern=r"^\d{4}/\d{4}$"),
    repo: AcademicRepository = Depends(get_academic_repo),
) -> list[AcademicTermOut]:
    """DeKUT's trimester calendar for the academic year.

    Three terms per year: Semester 1 January-April, Semester 2 May-August and
    Semester 3 September-December. The periods are the published pattern; the
    real dates are announced per programme and can move, so each row carries
    a `provisional` flag and a note saying so.
    """
    return await repo.list_terms(academic_year)


@router.get("/terms/current", response_model=AcademicTermOut)
async def get_current_term(repo: AcademicRepository = Depends(get_academic_repo)) -> AcademicTermOut:
    """The trimester today falls in - what the Academics screen opens on and
    what the assistant quotes when asked which semester it is."""
    return await repo.get_current_term()


@router.get("/courses", response_model=list[CourseOut])
async def list_courses(
    programme_code: str | None = Query(default=None),
    year_of_study: int | None = Query(default=None, ge=1, le=6),
    repo: AcademicRepository = Depends(get_academic_repo),
) -> list[CourseOut]:
    """The course catalogue, including which lecturer takes each unit.

    Read-only and unauthenticated like the rest of this router: a published
    timetable is not private, and the student-facing Academics screen needs
    the catalogue to label a session with more than a course code.
    """
    return await repo.list_courses(programme_code, year_of_study)


@router.get("/deadlines", response_model=list[AcademicDeadlineOut])
async def list_deadlines(
    programme_code: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    include_past: bool = Query(default=False),
    repo: AcademicRepository = Depends(get_academic_repo),
) -> list[AcademicDeadlineOut]:
    return await repo.list_deadlines(
        AcademicDeadlineQuery(
            programme_code=programme_code,
            category=category,
            limit=limit,
            include_past=include_past,
        )
    )
