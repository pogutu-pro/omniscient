"""S3-compatible storage backend (for Oracle Cloud Object Storage or any
S3-compatible provider). Not wired to any real credentials in this build —
selected only when STORAGE_PROVIDER=s3 and the S3_* variables are set.
"""
from __future__ import annotations

from app.services.storage.base import StorageBackend, StoredFile


class S3StorageBackend(StorageBackend):
    def __init__(self, endpoint: str, bucket: str, access_key: str, secret_key: str, region: str | None):
        if not (endpoint and bucket and access_key and secret_key):
            raise ValueError("S3 storage requires S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY and S3_SECRET_KEY")
        try:
            import boto3  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("boto3 is required for S3 storage; add it to requirements.txt to enable it") from exc

        self._bucket = bucket
        self._endpoint = endpoint
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    async def save(self, *, key: str, content: bytes, content_type: str) -> StoredFile:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=content, ContentType=content_type)
        return StoredFile(key=key, content_type=content_type, size=len(content))

    async def read(self, key: str) -> bytes:
        obj = self._client.get_object(Bucket=self._bucket, Key=key)
        return obj["Body"].read()

    def url_for(self, key: str) -> str:
        return f"{self._endpoint.rstrip('/')}/{self._bucket}/{key}"
