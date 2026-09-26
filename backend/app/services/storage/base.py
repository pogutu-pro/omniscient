"""File storage abstraction.

Business logic never touches the filesystem or an S3 SDK directly — it
goes through this interface, so swapping `local` for an S3-compatible
provider (the Oracle Cloud target) later is a config change, not a
rewrite. Validation (type/size/filename) happens before any bytes are
written, in `validate_upload` below.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    DOCX_CONTENT_TYPE,
    "image/png",
    "image/jpeg",
    "image/webp",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


class UploadRejected(Exception):
    pass


@dataclass
class StoredFile:
    key: str
    content_type: str
    size: int


class StorageBackend(ABC):
    @abstractmethod
    async def save(self, *, key: str, content: bytes, content_type: str) -> StoredFile: ...

    @abstractmethod
    async def read(self, key: str) -> bytes: ...

    @abstractmethod
    def url_for(self, key: str) -> str: ...


def validate_upload(*, filename: str, content_type: str, size: int) -> None:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise UploadRejected(f"Unsupported file type: {content_type}")
    if size > MAX_UPLOAD_BYTES:
        raise UploadRejected("File exceeds the 10 MB upload limit")
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        raise UploadRejected("Invalid filename")
