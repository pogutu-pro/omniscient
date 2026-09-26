from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.academics import Course, Programme
from app.models.past_paper import PastPaper
from app.schemas.past_paper import PastPaperCreate, PastPaperOut, PastPaperSearchParams, PastPaperUpdate


class PastPaperRepository(ABC):
    @abstractmethod
    async def search(self, params: PastPaperSearchParams) -> list[PastPaperOut]: ...

    @abstractmethod
    async def get_by_id(self, paper_id: str) -> PastPaperOut | None: ...

    @abstractmethod
    async def create(self, data: PastPaperCreate) -> PastPaperOut: ...

    @abstractmethod
    async def update(self, paper_id: str, data: PastPaperUpdate) -> PastPaperOut | None: ...

    @abstractmethod
    async def delete(self, paper_id: str) -> bool: ...


def _download_url(paper: PastPaper, settings: Settings) -> str:
    """Where a browser should fetch the PDF from.

    When the object lives in R2 and a public base URL is configured, link
    straight at Cloudflare. That is the whole point of R2 here: its egress
    is free, while the API download route would stream every paper out of
    the instance's limited block/egress budget. Local storage has no public
    address, so it keeps the API route, which reads the file through the
    storage backend.
    """
    public = (getattr(settings, "s3_public_url", None) or "").rstrip("/")
    if getattr(settings, "storage_provider", "local") == "s3" and public:
        return f"{public}/{paper.file_reference}"
    return f"{settings.api_url}/api/past-papers/{paper.id}/download"


def _to_out(paper: PastPaper, course: Course, settings: Settings) -> PastPaperOut:
    return PastPaperOut(
        id=paper.id,
        course_id=paper.course_id,
        course_code=course.code,
        course_name=course.name,
        programme_id=paper.programme_id,
        academic_year=paper.academic_year,
        semester=paper.semester,
        exam_type=paper.exam_type,
        file_name=paper.file_name,
        file_reference=paper.file_reference,
        download_url=_download_url(paper, settings),
    )


class SqlPastPaperRepository(PastPaperRepository):
    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings

    async def search(self, params: PastPaperSearchParams) -> list[PastPaperOut]:
        stmt = select(PastPaper, Course).join(Course, PastPaper.course_id == Course.id)
        if params.course_code:
            stmt = stmt.where(Course.code.ilike(f"%{params.course_code}%"))
        if params.query:
            like = f"%{params.query}%"
            stmt = stmt.where(or_(Course.name.ilike(like), Course.code.ilike(like)))
        if params.programme_code:
            stmt = stmt.join(Programme, PastPaper.programme_id == Programme.id).where(
                Programme.code == params.programme_code
            )
        if params.academic_year:
            stmt = stmt.where(PastPaper.academic_year == params.academic_year)
        stmt = stmt.order_by(PastPaper.academic_year.desc()).limit(params.limit)
        result = await self._session.execute(stmt)
        return [_to_out(paper, course, self._settings) for paper, course in result.all()]

    async def get_by_id(self, paper_id: str) -> PastPaperOut | None:
        stmt = select(PastPaper, Course).join(Course, PastPaper.course_id == Course.id).where(PastPaper.id == paper_id)
        result = await self._session.execute(stmt)
        row = result.first()
        if not row:
            return None
        paper, course = row
        return _to_out(paper, course, self._settings)

    async def create(self, data: PastPaperCreate) -> PastPaperOut:
        paper = PastPaper(**data.model_dump())
        self._session.add(paper)
        await self._session.commit()
        await self._session.refresh(paper)
        course = await self._session.get(Course, paper.course_id)
        return _to_out(paper, course, self._settings)

    async def update(self, paper_id: str, data: PastPaperUpdate) -> PastPaperOut | None:
        paper = await self._session.get(PastPaper, paper_id)
        if not paper:
            return None
        # exclude_unset: a partial body changes only the fields it names, so
        # an edit of the exam type cannot blank the academic year.
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(paper, field, value)
        await self._session.commit()
        await self._session.refresh(paper)
        course = await self._session.get(Course, paper.course_id)
        return _to_out(paper, course, self._settings)

    async def delete(self, paper_id: str) -> bool:
        paper = await self._session.get(PastPaper, paper_id)
        if not paper:
            return False
        await self._session.delete(paper)
        await self._session.commit()
        return True
