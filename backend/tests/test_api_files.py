from __future__ import annotations

from httpx import AsyncClient


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/auth/register",
        json={
            "registration_number": f"C026-01-{abs(hash(email)) % 100000:05d}/2023",
            "full_name": "Upload Tester",
            "email": email,
            "password": "Passw0rd!",
            "programme": "BSc Computer Science",
            "year_of_study": 2,
        },
    )
    return response.json()["access_token"]


async def test_upload_requires_auth(app_client: AsyncClient):
    response = await app_client.post("/api/files/upload", files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")})
    assert response.status_code == 401


async def test_upload_and_download_roundtrip(app_client: AsyncClient):
    token = await _register(app_client, "uploader@dekut.ac.ke")
    headers = {"Authorization": f"Bearer {token}"}

    uploaded = await app_client.post(
        "/api/files/upload",
        files={"file": ("notes.pdf", b"%PDF-1.4 fake pdf content", "application/pdf")},
        headers=headers,
    )
    assert uploaded.status_code == 201
    body = uploaded.json()
    assert body["key"].startswith(f"uploads/")

    downloaded = await app_client.get(f"/api/files/{body['key']}")
    assert downloaded.status_code == 200
    assert downloaded.content == b"%PDF-1.4 fake pdf content"
    assert downloaded.headers["content-type"] == "application/pdf"


async def test_upload_rejects_disallowed_type(app_client: AsyncClient):
    token = await _register(app_client, "bad-upload@dekut.ac.ke")
    headers = {"Authorization": f"Bearer {token}"}

    response = await app_client.post(
        "/api/files/upload",
        files={"file": ("script.exe", b"MZ", "application/x-msdownload")},
        headers=headers,
    )
    assert response.status_code == 422


async def test_download_missing_key_returns_404(app_client: AsyncClient):
    response = await app_client.get("/api/files/uploads/does-not-exist.pdf")
    assert response.status_code == 404


async def test_download_rejects_path_traversal(app_client: AsyncClient):
    response = await app_client.get("/api/files/../../etc/passwd")
    assert response.status_code in (400, 404)
