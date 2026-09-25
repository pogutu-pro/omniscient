from __future__ import annotations

from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/auth/register",
        json={
            "registration_number": f"C026-01-{email[:4]}/2023",
            "full_name": "Complainant",
            "email": email,
            "password": "Passw0rd!",
            "programme": "BSc Computer Science",
            "year_of_study": 2,
        },
    )
    return response.json()["access_token"]


async def test_file_complaint_requires_auth(app_client: AsyncClient):
    response = await app_client.post("/api/complaints", json={"category": "maintenance", "details": "Broken tap in room B14"})
    assert response.status_code == 401


async def test_file_and_fetch_complaint(app_client: AsyncClient):
    token = await _register_and_login(app_client, "owner@dekut.ac.ke")
    headers = {"Authorization": f"Bearer {token}"}

    created = await app_client.post(
        "/api/complaints", json={"category": "maintenance", "details": "Broken tap in room B14"}, headers=headers
    )
    assert created.status_code == 201
    reference_code = created.json()["reference_code"]

    fetched = await app_client.get(f"/api/complaints/{reference_code}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "submitted"

    listed = await app_client.get("/api/complaints", headers=headers)
    assert len(listed.json()) == 1


async def test_complaint_forbidden_for_other_student(app_client: AsyncClient):
    owner_token = await _register_and_login(app_client, "owner2@dekut.ac.ke")
    intruder_token = await _register_and_login(app_client, "intruder2@dekut.ac.ke")

    created = await app_client.post(
        "/api/complaints",
        json={"category": "security", "details": "Suspicious activity near the gate"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    reference_code = created.json()["reference_code"]

    response = await app_client.get(
        f"/api/complaints/{reference_code}", headers={"Authorization": f"Bearer {intruder_token}"}
    )
    assert response.status_code == 403


async def test_file_complaint_rejects_invalid_category(app_client: AsyncClient):
    token = await _register_and_login(app_client, "cat@dekut.ac.ke")
    response = await app_client.post(
        "/api/complaints",
        json={"category": "not_real", "details": "Something is wrong here"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
