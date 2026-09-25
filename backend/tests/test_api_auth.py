from __future__ import annotations

from httpx import AsyncClient


async def _register(client: AsyncClient, email: str = "new@dekut.ac.ke") -> dict:
    response = await client.post(
        "/api/auth/register",
        json={
            "registration_number": "C026-01-0077/2023",
            "full_name": "New Student",
            "email": email,
            "password": "Passw0rd!",
            "programme": "BSc Computer Science",
            "year_of_study": 1,
        },
    )
    return response


async def test_register_returns_token_and_student(app_client: AsyncClient):
    response = await _register(app_client)
    assert response.status_code == 201
    body = response.json()
    assert body["access_token"]
    assert body["student"]["email"] == "new@dekut.ac.ke"


async def test_register_duplicate_email_conflicts(app_client: AsyncClient):
    await _register(app_client)
    second = await _register(app_client)
    assert second.status_code == 409


async def test_login_with_correct_credentials(app_client: AsyncClient):
    await _register(app_client)
    response = await app_client.post("/api/auth/login", json={"email": "new@dekut.ac.ke", "password": "Passw0rd!"})
    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_login_with_wrong_password_rejected(app_client: AsyncClient):
    await _register(app_client)
    response = await app_client.post("/api/auth/login", json={"email": "new@dekut.ac.ke", "password": "wrong"})
    assert response.status_code == 401


async def test_me_requires_authentication(app_client: AsyncClient):
    response = await app_client.get("/api/auth/me")
    assert response.status_code == 401


async def test_me_returns_current_student(app_client: AsyncClient):
    registered = await _register(app_client)
    token = registered.json()["access_token"]
    response = await app_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "new@dekut.ac.ke"
