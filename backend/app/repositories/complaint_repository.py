from __future__ import annotations

import secrets
from abc import ABC, abstractmethod

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.complaint import Complaint
from app.schemas.complaint import ComplaintCreate, ComplaintOut


def generate_reference_code() -> str:
    return f"OMN-{secrets.token_hex(3).upper()}"


class ComplaintRepository(ABC):
    @abstractmethod
    async def create(self, student_id: str, data: ComplaintCreate) -> ComplaintOut: ...

    @abstractmethod
    async def get_by_reference(self, reference_code: str) -> ComplaintOut | None: ...

    @abstractmethod
    async def list_for_student(self, student_id: str) -> list[ComplaintOut]: ...

    @abstractmethod
    async def list_all(self, status_filter: str | None, limit: int) -> list[ComplaintOut]: ...

    @abstractmethod
    async def update_status(self, complaint_id: str, status: str) -> ComplaintOut | None: ...

    @abstractmethod
    async def count_by_category(self) -> dict[str, int]: ...

    @abstractmethod
    async def count_by_status(self) -> dict[str, int]: ...


class SqlComplaintRepository(ComplaintRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, student_id: str, data: ComplaintCreate) -> ComplaintOut:
        complaint = Complaint(
            reference_code=generate_reference_code(),
            student_id=student_id,
            category=data.category,
            details=data.details,
            location=data.location,
            attachment_reference=data.attachment_reference,
            status="submitted",
        )
        self._session.add(complaint)
        await self._session.commit()
        await self._session.refresh(complaint)
        return ComplaintOut.model_validate(complaint)

    async def get_by_reference(self, reference_code: str) -> ComplaintOut | None:
        stmt = select(Complaint).where(Complaint.reference_code == reference_code)
        result = await self._session.execute(stmt)
        complaint = result.scalar_one_or_none()
        return ComplaintOut.model_validate(complaint) if complaint else None

    async def list_for_student(self, student_id: str) -> list[ComplaintOut]:
        stmt = select(Complaint).where(Complaint.student_id == student_id).order_by(Complaint.created_at.desc())
        result = await self._session.execute(stmt)
        return [ComplaintOut.model_validate(c) for c in result.scalars().all()]

    async def list_all(self, status_filter: str | None, limit: int) -> list[ComplaintOut]:
        stmt = select(Complaint).order_by(Complaint.created_at.desc()).limit(limit)
        if status_filter:
            stmt = stmt.where(Complaint.status == status_filter)
        result = await self._session.execute(stmt)
        return [ComplaintOut.model_validate(c) for c in result.scalars().all()]

    async def update_status(self, complaint_id: str, status: str) -> ComplaintOut | None:
        complaint = await self._session.get(Complaint, complaint_id)
        if not complaint:
            return None
        complaint.status = status
        await self._session.commit()
        await self._session.refresh(complaint)
        return ComplaintOut.model_validate(complaint)

    async def count_by_category(self) -> dict[str, int]:
        stmt = select(Complaint.category, func.count(Complaint.id)).group_by(Complaint.category)
        result = await self._session.execute(stmt)
        return {category: count for category, count in result.all()}

    async def count_by_status(self) -> dict[str, int]:
        stmt = select(Complaint.status, func.count(Complaint.id)).group_by(Complaint.status)
        result = await self._session.execute(stmt)
        return {status: count for status, count in result.all()}
