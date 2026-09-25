from __future__ import annotations

from pathlib import Path

from app.services.storage.base import StorageBackend, StoredFile


class LocalStorageBackend(StorageBackend):
    """Filesystem-backed storage for local development and small deployments.

    Files are written under a dedicated directory, never executed, and
    served back only through the API's own download endpoints (never
    directly exposed as static files with execute permissions).
    """

    def __init__(self, base_path: str, public_base_url: str):
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._public_base_url = public_base_url.rstrip("/")

    async def save(self, *, key: str, content: bytes, content_type: str) -> StoredFile:
        target = self._base_path / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return StoredFile(key=key, content_type=content_type, size=len(content))

    async def read(self, key: str) -> bytes:
        target = self._base_path / key
        return target.read_bytes()

    def url_for(self, key: str) -> str:
        return f"{self._public_base_url}/api/files/{key}"
