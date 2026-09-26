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

import os
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_academic_repo,
    get_complaint_repo,
    get_current_admin,
    get_db_session,
    get_db,
    get_embedding_service,
    get_hostel_repo,
    get_past_paper_repo,
    get_settings_dep,
    get_storage_dep,
)
from app.core.config import Settings
from app.models.past_paper import PastPaper
from app.repositories.academic_repository import AcademicRepository
from app.repositories.chunk_repository import SqlChunkRepository
from app.repositories.complaint_repository import ComplaintRepository
from app.repositories.hostel_repository import HostelRepository, HostelWriteNotSupported
from app.repositories.past_paper_repository import PastPaperRepository
from app.schemas.academics import (
    AcademicDeadlineCreate,
    AcademicDeadlineOut,
    AcademicTermCreate,
    AcademicTermOut,
    CourseCreate,
    CourseOut,
    ProgrammeCreate,
    ProgrammeOut,
    TimetableEntryCreate,
    TimetableEntryOut,
    TimetableImportReportOut,
)
from app.schemas.complaint import ALLOWED_STATUSES, ComplaintOut
from app.schemas.housing import HostelCreate, HostelOut, HostelUpdate
from app.schemas.insights import InsightsOut
from app.schemas.past_paper import PastPaperCreate, PastPaperOut
from app.schemas.rag_admin import ReindexAccepted, ReindexRequest, ReindexStatus
from app.services.embedding_service import EmbeddingService
from app.services.insights_service import build_insights
from app.services.paper_index_service import PaperIndexService
from app.services.reindex_job import start_reindex, state
from app.services.storage.base import StorageBackend
from app.services.timetable_import import (
    TimetableImportError,
    import_timetable,
    parse_timetable_workbook,
)

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


@router.put("/terms", response_model=AcademicTermOut)
async def upsert_term(
    data: AcademicTermCreate, repo: AcademicRepository = Depends(get_academic_repo)
) -> AcademicTermOut:
    """Enter or correct a trimester's dates.

    Keyed on (academic year, trimester), so this is how a slipped reporting
    date is corrected in place rather than added as a second, conflicting
    term. Admin-only like the rest of this router: the assistant and the
    student-facing calendar read these rows, so an unauthenticated writer
    here would be able to rewrite the dates the whole faculty is told.
    """
    return await repo.upsert_term(data)


@router.post("/timetable/import", response_model=TimetableImportReportOut)
async def import_timetable_file(
    file: UploadFile = File(...),
    programme_code: str = Form("BCS"),
    academic_year: str | None = Form(None),
    overwrite: bool = Form(False),
    prune: bool = Form(False),
    session: AsyncSession = Depends(get_db_session),
) -> TimetableImportReportOut:
    """Upload and ingest a teaching timetable spreadsheet (.xlsx)."""
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Excel workbooks (.xlsx) are supported.",
        )
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name
        content = await file.read()
        tmp.write(content)
    try:
        parsed = parse_timetable_workbook(tmp_path, academic_year=academic_year or None)
        report = await import_timetable(
            session,
            parsed,
            programme_code=programme_code,
            overwrite_course_detail=overwrite,
            prune=prune,
        )
        return TimetableImportReportOut(
            academic_year=report.academic_year,
            term_label=report.term_label,
            programme_code=report.programme_code,
            courses_created=report.courses_created,
            courses_updated=report.courses_updated,
            sessions_created=report.sessions_created,
            sessions_updated=report.sessions_updated,
            sessions_removed=report.sessions_removed,
            sessions_without_a_catalogue_entry=report.sessions_without_a_catalogue_entry,
            warnings=report.warnings,
            official_trimester=report.official_trimester,
            summary=report.summary(),
        )
    except TimetableImportError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


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


# --- Past-paper RAG index ---
# Routes are declared before "/past-papers/{paper_id}" would ever match
# them only by luck of ordering, so both live under a distinct prefix to
# keep "/past-papers/reindex" from being read as a paper id.
@router.post("/rag/reindex", response_model=ReindexAccepted, status_code=status.HTTP_202_ACCEPTED)
async def reindex_past_papers(
    body: ReindexRequest | None = None,
    storage: StorageBackend = Depends(get_storage_dep),
    embeddings: EmbeddingService = Depends(get_embedding_service),
    settings: Settings = Depends(get_settings_dep),
) -> ReindexAccepted:
    """Queue a rebuild of the past-paper vector index.

    Returns immediately: the work runs in the background because a full
    library takes minutes and an admin dashboard should not sit on a
    pending request that long. Poll `/rag/index-status` for progress.
    """
    if not settings.embedding_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Embeddings are disabled on this deployment. Set EMBEDDING_ENABLED=true to build an index.",
        )
    request = body or ReindexRequest()

    async def job():
        # A session of its own: this work outlives the request, so it must
        # not sit on a request-scoped session for its whole lifetime.
        async for session in get_db():
            service = PaperIndexService(session, storage, embeddings, settings)
            return await service.reindex_all(
                force=request.force,
                paper_ids=request.past_paper_ids,
                concurrency=request.concurrency,
            )

    if not start_reindex(job):
        return ReindexAccepted(
            started=False,
            already_running=True,
            detail="A reindex is already running. Wait for it to finish before starting another.",
        )
    return ReindexAccepted(
        started=True, detail="Reindex started in the background. Poll /api/admin/rag/index-status for progress."
    )


@router.get("/rag/index-status", response_model=ReindexStatus)
async def reindex_status(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
) -> ReindexStatus:
    chunks = SqlChunkRepository(session)
    total_chunks = await chunks.total_count()
    indexed = len(await chunks.distinct_paper_ids())
    total_papers = int((await session.execute(select(func.count()).select_from(PastPaper))).scalar_one())
    return ReindexStatus(
        running=state.running,
        total_chunks=total_chunks,
        indexed_papers=indexed,
        total_papers=total_papers,
        last_report=state.last_report,
        last_error=state.last_error,
        embedding_backend=settings.embedding_backend,
        embedding_model=settings.embedding_model,
        rag_enabled=settings.rag_enabled,
    )


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
