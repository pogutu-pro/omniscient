"""S3-compatible object storage, which is how Cloudflare R2 is reached.

R2 speaks the S3 API, so boto3 drives it directly, with three R2-specific
details that are easy to get wrong and produce confusing failures:

- `region` is the literal string `auto`. R2 ignores it and rejects
  anything else in some configurations, so it must be set explicitly
  rather than left to boto3's default resolution.
- **Path-style addressing is required.** boto3 defaults to
  virtual-host style (`bucket.endpoint`), which R2 does not answer, and
  the resulting error mentions DNS rather than anything about the
  bucket. `S3_ADDRESSING_STYLE=path` avoids it.
- Reads and writes are blocking boto3 calls, so they run in a worker
  thread. Calling them inline from a coroutine would block the event loop
  for the length of a network round trip.

The public base URL is separate from the API endpoint on purpose: the
endpoint is a credentialed internal address, while `S3_PUBLIC_URL` is
what a student's browser is sent to. Conflating the two is how a public
bucket ends up advertised behind a private endpoint.
"""
from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.services.storage.base import StorageBackend, StoredFile

logger = get_logger(component="s3_storage")

# R2 rejects the AWS chunked-transfer encoding that botocore uses by
# default for larger PUTs.
_R2_FIXED_CONTENT_LENGTH = True


class S3StorageBackend(StorageBackend):
    def __init__(
        self,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str | None,
        addressing_style: str = "auto",
        public_url: str | None = None,
    ):
        if not (endpoint and bucket and access_key and secret_key):
            raise ValueError("S3 storage requires S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY and S3_SECRET_KEY")
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("boto3 is required for S3 storage; add it to requirements.txt to enable it") from exc

        self._bucket = bucket
        self._endpoint = endpoint
        self._public_url = (public_url or "").rstrip("/")
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            # R2's own region identifier; boto3's default resolution tries
            # to contact a real AWS endpoint and stalls.
            region_name=region or "auto",
            config=Config(
                s3={
                    "addressing_style": addressing_style,
                    "signature_version": "s3v4",
                },
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    async def save(self, *, key: str, content: bytes, content_type: str) -> StoredFile:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        logger.info("object_stored", bucket=self._bucket, key=key, size=len(content))
        return StoredFile(key=key, content_type=content_type, size=len(content))

    async def read(self, key: str) -> bytes:
        def _read() -> bytes:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()

        return await asyncio.to_thread(_read)

    def url_for(self, key: str) -> str:
        # Prefer the public/custom domain. Falling back to the raw
        # endpoint only produces a working link for a genuinely public
        # bucket, which is exactly the configuration S3_PUBLIC_URL exists
        # to make explicit.
        if self._public_url:
            return f"{self._public_url}/{key}"
        return f"{self._endpoint.rstrip('/')}/{self._bucket}/{key}"

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)
