from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.student import Student
from app.schemas.student import StudentCreate


class StudentRepository(ABC):
    @abstractmethod
    async def get_by_email(self, email: str) -> Student | None: ...

    @abstractmethod
    async def get_by_id(self, student_id: str) -> Student | None: ...

    @abstractmethod
    async def create(self, data: StudentCreate) -> Student: ...

    @abstractmethod
    async def update_preferences(self, student_id: str, preferences: dict) -> Student | None: ...


class SqlStudentRepository(StudentRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_email(self, email: str) -> Student | None:
        stmt = select(Student).where(Student.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, student_id: str) -> Student | None:
        return await self._session.get(Student, student_id)

    async def create(self, data: StudentCreate) -> Student:
        student = Student(
            registration_number=data.registration_number,
            full_name=data.full_name,
            email=data.email,
            hashed_password=hash_password(data.password),
            programme=data.programme,
            year_of_study=data.year_of_study,
            preferences={},
        )
        self._session.add(student)
        await self._session.commit()
        await self._session.refresh(student)
        return student

    async def update_preferences(self, student_id: str, preferences: dict) -> Student | None:
        student = await self.get_by_id(student_id)
        if not student:
            return None
        student.preferences = {**student.preferences, **preferences}
        await self._session.commit()
        await self._session.refresh(student)
        return student
