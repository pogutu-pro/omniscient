from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.providers.base import LLMProvider
from app.agents.providers.factory import get_llm_provider
from app.core.config import Settings, get_settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.student import Student
from app.repositories.academic_repository import AcademicRepository, SqlAcademicRepository
from app.repositories.complaint_repository import ComplaintRepository, SqlComplaintRepository
from app.repositories.hostel_repository import HostelRepository, get_hostel_repository
from app.repositories.past_paper_repository import PastPaperRepository, SqlPastPaperRepository
from app.repositories.student_repository import SqlStudentRepository, StudentRepository
from app.tools.build import build_default_registry
from app.tools.registry import ToolContext, ToolRegistry

_registry = build_default_registry()


def get_settings_dep() -> Settings:
    return get_settings()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db():
        yield session


def get_student_repository(session: AsyncSession = Depends(get_db_session)) -> StudentRepository:
    return SqlStudentRepository(session)


def get_hostel_repo(
    session: AsyncSession = Depends(get_db_session), settings: Settings = Depends(get_settings_dep)
) -> HostelRepository:
    return get_hostel_repository(session, settings)


def get_academic_repo(session: AsyncSession = Depends(get_db_session)) -> AcademicRepository:
    return SqlAcademicRepository(session)


def get_past_paper_repo(
    session: AsyncSession = Depends(get_db_session), settings: Settings = Depends(get_settings_dep)
) -> PastPaperRepository:
    return SqlPastPaperRepository(session, settings)


def get_complaint_repo(session: AsyncSession = Depends(get_db_session)) -> ComplaintRepository:
    return SqlComplaintRepository(session)


def get_tool_registry() -> ToolRegistry:
    return _registry


def get_llm_provider_dep(settings: Settings = Depends(get_settings_dep)) -> LLMProvider:
    return get_llm_provider(settings)


async def get_optional_student(
    authorization: str | None = Header(default=None),
    repo: StudentRepository = Depends(get_student_repository),
) -> Student | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1]
    student_id = decode_access_token(token)
    if not student_id:
        return None
    return await repo.get_by_id(student_id)


async def get_current_student(
    student: Student | None = Depends(get_optional_student),
) -> Student:
    if not student:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return student


async def get_current_admin(
    student: Student = Depends(get_current_student),
) -> Student:
    """Gate for every /api/admin/* route. Checked against the student
    record loaded from the DB for this request, never against a claim
    made anywhere else (a token payload, a request body, or anything the
    LLM might say) - see core/security.py, whose JWTs only ever carry a
    student id, nothing else.
    """
    if not student.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return student


async def get_tool_context(
    hostel_repo: HostelRepository = Depends(get_hostel_repo),
    academic_repo: AcademicRepository = Depends(get_academic_repo),
    past_paper_repo: PastPaperRepository = Depends(get_past_paper_repo),
    complaint_repo: ComplaintRepository = Depends(get_complaint_repo),
    student: Student | None = Depends(get_optional_student),
) -> ToolContext:
    return ToolContext(
        hostel_repo=hostel_repo,
        academic_repo=academic_repo,
        past_paper_repo=past_paper_repo,
        complaint_repo=complaint_repo,
        student_id=student.id if student else None,
    )
