from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.api.deps import get_current_student, get_settings_dep
from app.core.config import Settings
from app.models.student import Student
from app.services.storage.base import UploadRejected, validate_upload
from app.services.storage.factory import get_storage_backend

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    file: UploadFile,
    student: Student = Depends(get_current_student),
    settings: Settings = Depends(get_settings_dep),
) -> dict:
    """Upload a complaint attachment. Requires authentication; validates
    type/size/filename before anything is written, and the returned key
    is what a subsequent POST /api/complaints references — never a raw
    filesystem path.
    """
    content = await file.read()
    try:
        validate_upload(filename=file.filename or "", content_type=file.content_type or "", size=len(content))
    except UploadRejected as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    storage = get_storage_backend(settings)
    extension = (file.filename or "").rsplit(".", 1)[-1] if "." in (file.filename or "") else "bin"
    key = f"complaints/{student.id}/{uuid.uuid4().hex}.{extension}"
    stored = await storage.save(key=key, content=content, content_type=file.content_type or "application/octet-stream")
    return {"key": stored.key, "url": storage.url_for(stored.key)}
