from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_academic_repo
from app.repositories.academic_repository import AcademicRepository
from app.schemas.academics import AcademicDeadlineOut, TimetableEntryOut, TimetableQuery

router = APIRouter(prefix="/api/academics", tags=["academics"])


@router.get("/timetable", response_model=list[TimetableEntryOut])
async def get_timetable(
    programme_code: str | None = Query(default=None),
    year_of_study: int | None = Query(default=None, ge=1, le=6),
    day_of_week: int | None = Query(default=None, ge=0, le=6),
    repo: AcademicRepository = Depends(get_academic_repo),
) -> list[TimetableEntryOut]:
    query = TimetableQuery(programme_code=programme_code, year_of_study=year_of_study, day_of_week=day_of_week)
    return await repo.get_timetable(query)


@router.get("/deadlines", response_model=list[AcademicDeadlineOut])
async def list_deadlines(
    programme_code: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    repo: AcademicRepository = Depends(get_academic_repo),
) -> list[AcademicDeadlineOut]:
    return await repo.list_deadlines(programme_code, limit)
