from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_student, get_student_repository
from app.models.student import Student
from app.repositories.student_repository import StudentRepository
from app.schemas.student import StudentCreate, StudentLogin, StudentOut, TokenOut
from app.services.auth_service import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    authenticate_student,
    issue_token,
    register_student,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(data: StudentCreate, repo: StudentRepository = Depends(get_student_repository)) -> TokenOut:
    try:
        student = await register_student(repo, data)
    except EmailAlreadyRegistered as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered") from exc
    token = issue_token(student)
    return TokenOut(access_token=token, student=StudentOut.model_validate(student))


@router.post("/login", response_model=TokenOut)
async def login(data: StudentLogin, repo: StudentRepository = Depends(get_student_repository)) -> TokenOut:
    try:
        student = await authenticate_student(repo, data.email, data.password)
    except InvalidCredentials as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password") from exc
    token = issue_token(student)
    return TokenOut(access_token=token, student=StudentOut.model_validate(student))


@router.get("/me", response_model=StudentOut)
async def me(student: Student = Depends(get_current_student)) -> StudentOut:
    return StudentOut.model_validate(student)
