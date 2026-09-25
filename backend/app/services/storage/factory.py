from __future__ import annotations

from app.core.config import Settings
from app.services.storage.base import StorageBackend
from app.services.storage.local_storage import LocalStorageBackend


def get_storage_backend(settings: Settings) -> StorageBackend:
    if settings.storage_provider == "s3":
        from app.services.storage.s3_storage import S3StorageBackend

        return S3StorageBackend(
            endpoint=settings.s3_endpoint or "",
            bucket=settings.s3_bucket or "",
            access_key=settings.s3_access_key or "",
            secret_key=settings.s3_secret_key or "",
            region=settings.s3_region,
        )
    return LocalStorageBackend(settings.storage_local_path, settings.api_url)
