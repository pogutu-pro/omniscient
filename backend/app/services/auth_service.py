from __future__ import annotations

from app.core.security import create_access_token, verify_password
from app.models.student import Student
from app.repositories.student_repository import StudentRepository
from app.schemas.student import StudentCreate


class InvalidCredentials(Exception):
    pass


class EmailAlreadyRegistered(Exception):
    pass


async def register_student(repo: StudentRepository, data: StudentCreate) -> Student:
    existing = await repo.get_by_email(data.email)
    if existing:
        raise EmailAlreadyRegistered(data.email)
    return await repo.create(data)


async def authenticate_student(repo: StudentRepository, email: str, password: str) -> Student:
    student = await repo.get_by_email(email)
    if not student or not verify_password(password, student.hashed_password):
        raise InvalidCredentials()
    return student


def issue_token(student: Student) -> str:
    return create_access_token(subject=student.id)
