"""Admin-only content management.

Every route here depends on `get_current_admin`, which checks the
authenticated student's `is_admin` flag against the database — never
anything a client claims about itself. Admin-authored data flows through
the exact same repositories (and therefore the exact same tools) the chat
agent already reads from, so there is no separate "admin data path" that
could drift from what the agent actually grounds its answers in: feeding
a hostel here is what makes `search_hostels` find it.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_academic_repo,
    get_complaint_repo,
    get_current_admin,
    get_db_session,
    get_hostel_repo,
    get_past_paper_repo,
)
from app.repositories.academic_repository import AcademicRepository
from app.repositories.complaint_repository import ComplaintRepository
from app.repositories.hostel_repository import HostelRepository, HostelWriteNotSupported
from app.repositories.past_paper_repository import PastPaperRepository
from app.schemas.academics import (
    AcademicDeadlineCreate,
    AcademicDeadlineOut,
    CourseCreate,
    CourseOut,
    ProgrammeCreate,
    ProgrammeOut,
    TimetableEntryCreate,
    TimetableEntryOut,
)
from app.schemas.complaint import ALLOWED_STATUSES, ComplaintOut
from app.schemas.housing import HostelCreate, HostelOut, HostelUpdate
from app.schemas.insights import InsightsOut
from app.schemas.past_paper import PastPaperCreate, PastPaperOut
from app.services.insights_service import build_insights

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(get_current_admin)])


# --- Insights ---
@router.get("/insights", response_model=InsightsOut)
async def get_insights(
    session_db: AsyncSession = Depends(get_db_session),
    complaint_repo: ComplaintRepository = Depends(get_complaint_repo),
) -> InsightsOut:
    return await build_insights(session_db, complaint_repo)


# --- Housing ---
@router.post("/hostels", response_model=HostelOut, status_code=status.HTTP_201_CREATED)
async def create_hostel(data: HostelCreate, repo: HostelRepository = Depends(get_hostel_repo)) -> HostelOut:
    try:
        return await repo.create(data)
    except HostelWriteNotSupported as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.put("/hostels/{hostel_id}", response_model=HostelOut)
async def update_hostel(
    hostel_id: str, data: HostelUpdate, repo: HostelRepository = Depends(get_hostel_repo)
) -> HostelOut:
    try:
        hostel = await repo.update(hostel_id, data)
    except HostelWriteNotSupported as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not hostel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hostel not found")
    return hostel


@router.delete("/hostels/{hostel_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_hostel(hostel_id: str, repo: HostelRepository = Depends(get_hostel_repo)) -> None:
    try:
        deleted = await repo.delete(hostel_id)
    except HostelWriteNotSupported as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hostel not found")


# --- Academics ---
@router.get("/programmes", response_model=list[ProgrammeOut])
async def list_programmes(repo: AcademicRepository = Depends(get_academic_repo)) -> list[ProgrammeOut]:
    return await repo.list_programmes()


@router.post("/programmes", response_model=ProgrammeOut, status_code=status.HTTP_201_CREATED)
async def create_programme(
    data: ProgrammeCreate, repo: AcademicRepository = Depends(get_academic_repo)
) -> ProgrammeOut:
    return await repo.create_programme(data)


@router.get("/courses", response_model=list[CourseOut])
async def list_courses(
    programme_code: str | None = Query(default=None),
    repo: AcademicRepository = Depends(get_academic_repo),
) -> list[CourseOut]:
    return await repo.list_courses(programme_code, None)


@router.post("/courses", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
async def create_course(data: CourseCreate, repo: AcademicRepository = Depends(get_academic_repo)) -> CourseOut:
    return await repo.create_course(data)


@router.delete("/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_course(course_id: str, repo: AcademicRepository = Depends(get_academic_repo)) -> None:
    if not await repo.delete_course(course_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")


@router.post("/timetable", response_model=TimetableEntryOut, status_code=status.HTTP_201_CREATED)
async def create_timetable_entry(
    data: TimetableEntryCreate, repo: AcademicRepository = Depends(get_academic_repo)
) -> TimetableEntryOut:
    return await repo.create_timetable_entry(data)


@router.delete("/timetable/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_timetable_entry(entry_id: str, repo: AcademicRepository = Depends(get_academic_repo)) -> None:
    if not await repo.delete_timetable_entry(entry_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Timetable entry not found")


@router.post("/deadlines", response_model=AcademicDeadlineOut, status_code=status.HTTP_201_CREATED)
async def create_deadline(
    data: AcademicDeadlineCreate, repo: AcademicRepository = Depends(get_academic_repo)
) -> AcademicDeadlineOut:
    return await repo.create_deadline(data)


@router.delete("/deadlines/{deadline_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_deadline(deadline_id: str, repo: AcademicRepository = Depends(get_academic_repo)) -> None:
    if not await repo.delete_deadline(deadline_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deadline not found")


# --- Past papers ---
@router.post("/past-papers", response_model=PastPaperOut, status_code=status.HTTP_201_CREATED)
async def create_past_paper(
    data: PastPaperCreate, repo: PastPaperRepository = Depends(get_past_paper_repo)
) -> PastPaperOut:
    return await repo.create(data)


@router.delete("/past-papers/{paper_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_past_paper(paper_id: str, repo: PastPaperRepository = Depends(get_past_paper_repo)) -> None:
    if not await repo.delete(paper_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Past paper not found")


# --- Complaints ---
@router.get("/complaints", response_model=list[ComplaintOut])
async def list_all_complaints(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    repo: ComplaintRepository = Depends(get_complaint_repo),
) -> list[ComplaintOut]:
    return await repo.list_all(status_filter, limit)


@router.patch("/complaints/{complaint_id}/status", response_model=ComplaintOut)
async def update_complaint_status(
    complaint_id: str,
    new_status: str = Query(alias="status"),
    repo: ComplaintRepository = Depends(get_complaint_repo),
) -> ComplaintOut:
    if new_status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status")
    complaint = await repo.update_status(complaint_id, new_status)
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")
    return complaint
