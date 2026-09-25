from __future__ import annotations

import mimetypes
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status

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
    """Upload a file (complaint attachment, past-paper PDF, chat attachment,
    hostel photo). Requires authentication; validates type/size/filename
    before anything is written, and the returned key is what a subsequent
    request (a complaint, an admin past-paper, a chat message) references -
    never a raw filesystem path.
    """
    content = await file.read()
    try:
        validate_upload(filename=file.filename or "", content_type=file.content_type or "", size=len(content))
    except UploadRejected as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    storage = get_storage_backend(settings)
    extension = (file.filename or "").rsplit(".", 1)[-1] if "." in (file.filename or "") else "bin"
    key = f"uploads/{student.id}/{uuid.uuid4().hex}.{extension}"
    stored = await storage.save(key=key, content=content, content_type=file.content_type or "application/octet-stream")
    return {"key": stored.key, "url": storage.url_for(stored.key)}


@router.get("/{key:path}")
async def get_uploaded_file(key: str, settings: Settings = Depends(get_settings_dep)) -> Response:
    """Serve a previously uploaded file by its storage key.

    Deliberately unauthenticated, matching the existing past-paper download
    route: keys are unguessable (uuid4-based) and nothing served here is
    more sensitive than a past paper already is. `".."`/absolute paths are
    rejected so a key can never escape the storage root.
    """
    if ".." in key or key.startswith("/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file key")
    storage = get_storage_backend(settings)
    try:
        content = await storage.read(key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found") from exc
    content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    return Response(content=content, media_type=content_type)
