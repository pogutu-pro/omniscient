from __future__ import annotations

import tempfile

import pytest

from app.services.storage.base import UploadRejected, validate_upload
from app.services.storage.local_storage import LocalStorageBackend


def test_validate_upload_rejects_bad_content_type():
    with pytest.raises(UploadRejected):
        validate_upload(filename="script.exe", content_type="application/x-msdownload", size=100)


def test_validate_upload_rejects_oversized_file():
    with pytest.raises(UploadRejected):
        validate_upload(filename="paper.pdf", content_type="application/pdf", size=11 * 1024 * 1024)


def test_validate_upload_rejects_path_traversal_filename():
    with pytest.raises(UploadRejected):
        validate_upload(filename="../../etc/passwd", content_type="application/pdf", size=10)


def test_validate_upload_accepts_valid_file():
    validate_upload(filename="paper.pdf", content_type="application/pdf", size=1024)


async def test_local_storage_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        backend = LocalStorageBackend(tmp, "http://testserver")
        stored = await backend.save(key="demo.pdf", content=b"hello world", content_type="application/pdf")
        assert stored.size == 11

        content = await backend.read("demo.pdf")
        assert content == b"hello world"
        assert backend.url_for("demo.pdf") == "http://testserver/api/files/demo.pdf"
