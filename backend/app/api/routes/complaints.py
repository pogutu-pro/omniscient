from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_complaint_repo, get_current_student
from app.models.student import Student
from app.repositories.complaint_repository import ComplaintRepository
from app.schemas.complaint import ALLOWED_CATEGORIES, ComplaintCreate, ComplaintOut

router = APIRouter(prefix="/api/complaints", tags=["complaints"])


@router.post("", response_model=ComplaintOut, status_code=status.HTTP_201_CREATED)
async def file_complaint(
    data: ComplaintCreate,
    student: Student = Depends(get_current_student),
    repo: ComplaintRepository = Depends(get_complaint_repo),
) -> ComplaintOut:
    if data.category not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid complaint category")
    return await repo.create(student.id, data)


@router.get("", response_model=list[ComplaintOut])
async def list_my_complaints(
    student: Student = Depends(get_current_student),
    repo: ComplaintRepository = Depends(get_complaint_repo),
) -> list[ComplaintOut]:
    return await repo.list_for_student(student.id)


@router.get("/{reference_code}", response_model=ComplaintOut)
async def get_complaint(
    reference_code: str,
    student: Student = Depends(get_current_student),
    repo: ComplaintRepository = Depends(get_complaint_repo),
) -> ComplaintOut:
    complaint = await repo.get_by_reference(reference_code)
    if not complaint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found")
    if complaint.student_id != student.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your complaint")
    return complaint
