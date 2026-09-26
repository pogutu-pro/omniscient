from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.models.student import Student
from tests.factories import make_course, make_hostel


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/auth/register",
        json={
            "registration_number": f"C026-01-{abs(hash(email)) % 100000:05d}/2023",
            "full_name": "Test Student",
            "email": email,
            "password": "Passw0rd!",
            "programme": "BSc Computer Science",
            "year_of_study": 2,
        },
    )
    return response.json()["access_token"]


async def _make_admin_token(client: AsyncClient, db_session: AsyncSession, email: str) -> str:
    token = await _register(client, email)
    result = await db_session.execute(select(Student).where(Student.email == email))
    registered = result.scalar_one()
    registered.is_admin = True
    await db_session.commit()
    return token


async def test_admin_routes_require_auth(app_client: AsyncClient):
    response = await app_client.get("/api/admin/insights")
    assert response.status_code == 401


async def test_admin_routes_forbidden_for_non_admin(app_client: AsyncClient):
    token = await _register(app_client, "student@dekut.ac.ke")
    response = await app_client.get("/api/admin/insights", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


async def test_admin_insights_returns_aggregate_counts(app_client: AsyncClient, db_session: AsyncSession):
    token = await _make_admin_token(app_client, db_session, "insights-admin@dekut.ac.ke")
    headers = {"Authorization": f"Bearer {token}"}

    response = await app_client.get("/api/admin/insights", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_students"] >= 1
    assert body["total_chat_sessions"] == 0
    assert body["total_messages"] == 0
    assert body["complaint_category_counts"] == {}
    assert body["complaint_status_counts"] == {}


async def test_admin_can_create_update_delete_hostel(app_client: AsyncClient, db_session: AsyncSession):
    token = await _make_admin_token(app_client, db_session, "hostel-admin@dekut.ac.ke")
    headers = {"Authorization": f"Bearer {token}"}

    created = await app_client.post(
        "/api/admin/hostels",
        json={
            "name": "New Hostel",
            "area": "Boma",
            "distance_from_campus_km": 0.5,
            "price_ksh": 5000,
            "verified": False,
            "amenities": ["wifi"],
            "availability": "available",
            "description": "Fresh listing",
        },
        headers=headers,
    )
    assert created.status_code == 201
    hostel_id = created.json()["id"]
    assert created.json()["source"] == "mock"

    updated = await app_client.put(
        f"/api/admin/hostels/{hostel_id}",
        json={
            "name": "New Hostel Renamed",
            "area": "Boma",
            "distance_from_campus_km": 0.5,
            "price_ksh": 5500,
            "verified": True,
            "amenities": ["wifi", "water"],
            "availability": "limited",
            "description": "Updated listing",
        },
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "New Hostel Renamed"
    assert updated.json()["price_ksh"] == 5500

    deleted = await app_client.delete(f"/api/admin/hostels/{hostel_id}", headers=headers)
    assert deleted.status_code == 204

    missing = await app_client.get(f"/api/housing/hostels/{hostel_id}")
    assert missing.status_code == 404


async def test_admin_hostel_with_image_key_returns_computed_image_url(app_client: AsyncClient, db_session: AsyncSession):
    token = await _make_admin_token(app_client, db_session, "hostel-image-admin@dekut.ac.ke")
    headers = {"Authorization": f"Bearer {token}"}

    uploaded = await app_client.post(
        "/api/files/upload",
        files={"file": ("hostel.png", b"\x89PNG\r\n\x1a\n fake png bytes", "image/png")},
        headers=headers,
    )
    assert uploaded.status_code == 201
    image_key = uploaded.json()["key"]

    created = await app_client.post(
        "/api/admin/hostels",
        json={
            "name": "Photographed Hostel",
            "area": "Boma",
            "distance_from_campus_km": 0.5,
            "price_ksh": 5000,
            "image_key": image_key,
        },
        headers=headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["image_url"] == f"http://localhost:8000/api/files/{image_key}"

    public = await app_client.get(f"/api/housing/hostels/{body['id']}")
    assert public.json()["image_url"] == body["image_url"]


async def test_admin_hostel_without_image_key_has_no_image_url(app_client: AsyncClient, db_session: AsyncSession):
    token = await _make_admin_token(app_client, db_session, "hostel-no-image-admin@dekut.ac.ke")
    headers = {"Authorization": f"Bearer {token}"}

    created = await app_client.post(
        "/api/admin/hostels",
        json={"name": "Plain Hostel", "area": "Boma", "distance_from_campus_km": 0.5, "price_ksh": 5000},
        headers=headers,
    )
    assert created.json()["image_url"] is None


async def test_admin_update_delete_hostel_not_found(app_client: AsyncClient, db_session: AsyncSession):
    token = await _make_admin_token(app_client, db_session, "hostel-404-admin@dekut.ac.ke")
    headers = {"Authorization": f"Bearer {token}"}

    update = await app_client.put(
        "/api/admin/hostels/does-not-exist",
        json={
            "name": "Unknown Hostel",
            "area": "Boma",
            "distance_from_campus_km": 0.5,
            "price_ksh": 5000,
            "availability": "available",
        },
        headers=headers,
    )
    assert update.status_code == 404

    delete = await app_client.delete("/api/admin/hostels/does-not-exist", headers=headers)
    assert delete.status_code == 404


async def test_non_admin_cannot_write_hostel(app_client: AsyncClient, db_session: AsyncSession):
    hostel = await make_hostel(db_session)
    token = await _register(app_client, "non-admin-writer@dekut.ac.ke")
    headers = {"Authorization": f"Bearer {token}"}

    response = await app_client.delete(f"/api/admin/hostels/{hostel.id}", headers=headers)
    assert response.status_code == 403


async def test_admin_programme_and_course_crud(app_client: AsyncClient, db_session: AsyncSession):
    token = await _make_admin_token(app_client, db_session, "academics-admin@dekut.ac.ke")
    headers = {"Authorization": f"Bearer {token}"}

    programme = await app_client.post(
        "/api/admin/programmes",
        json={"code": "BSE", "name": "BSc Software Engineering", "school": "School of Computing"},
        headers=headers,
    )
    assert programme.status_code == 201
    programme_id = programme.json()["id"]

    listed = await app_client.get("/api/admin/programmes", headers=headers)
    assert any(p["code"] == "BSE" for p in listed.json())

    course = await app_client.post(
        "/api/admin/courses",
        json={"programme_id": programme_id, "code": "SSE 2101", "name": "Software Design", "year_of_study": 2, "semester": 1},
        headers=headers,
    )
    assert course.status_code == 201
    course_id = course.json()["id"]

    courses_listed = await app_client.get("/api/admin/courses", params={"programme_code": "BSE"}, headers=headers)
    assert any(c["id"] == course_id for c in courses_listed.json())

    deleted = await app_client.delete(f"/api/admin/courses/{course_id}", headers=headers)
    assert deleted.status_code == 204

    delete_missing = await app_client.delete(f"/api/admin/courses/{course_id}", headers=headers)
    assert delete_missing.status_code == 404


async def test_admin_timetable_and_deadline_crud(app_client: AsyncClient, db_session: AsyncSession):
    token = await _make_admin_token(app_client, db_session, "timetable-admin@dekut.ac.ke")
    headers = {"Authorization": f"Bearer {token}"}
    course = await make_course(db_session)

    entry = await app_client.post(
        "/api/admin/timetable",
        json={
            "course_id": course.id,
            "day_of_week": 1,
            "start_time": "09:00",
            "end_time": "11:00",
            "venue": "LT9",
            "session_type": "lecture",
            "academic_year": "2026/2027",
            "semester": 1,
            "year_group": "2.1",
        },
        headers=headers,
    )
    assert entry.status_code == 201
    assert entry.json()["course_code"] == course.code
    assert entry.json()["year_group"] == "2.1"
    assert entry.json()["lecturer"] == course.lecturer
    entry_id = entry.json()["id"]

    deleted_entry = await app_client.delete(f"/api/admin/timetable/{entry_id}", headers=headers)
    assert deleted_entry.status_code == 204
    assert (await app_client.delete(f"/api/admin/timetable/{entry_id}", headers=headers)).status_code == 404

    deadline = await app_client.post(
        "/api/admin/deadlines",
        json={"title": "Test deadline", "description": "desc", "category": "general", "due_date": "2027-01-01"},
        headers=headers,
    )
    assert deadline.status_code == 201
    deadline_id = deadline.json()["id"]

    deleted_deadline = await app_client.delete(f"/api/admin/deadlines/{deadline_id}", headers=headers)
    assert deleted_deadline.status_code == 204
    assert (await app_client.delete(f"/api/admin/deadlines/{deadline_id}", headers=headers)).status_code == 404


async def test_admin_past_paper_crud(app_client: AsyncClient, db_session: AsyncSession):
    token = await _make_admin_token(app_client, db_session, "papers-admin@dekut.ac.ke")
    headers = {"Authorization": f"Bearer {token}"}
    course = await make_course(db_session)

    paper = await app_client.post(
        "/api/admin/past-papers",
        json={
            "course_id": course.id,
            "programme_id": course.programme_id,
            "academic_year": "2024/2025",
            "semester": 1,
            "exam_type": "main",
            "file_reference": "some-key.pdf",
            "file_name": "some-key.pdf",
        },
        headers=headers,
    )
    assert paper.status_code == 201
    paper_id = paper.json()["id"]

    deleted = await app_client.delete(f"/api/admin/past-papers/{paper_id}", headers=headers)
    assert deleted.status_code == 204
    assert (await app_client.delete(f"/api/admin/past-papers/{paper_id}", headers=headers)).status_code == 404


async def test_admin_complaints_list_and_status_update(app_client: AsyncClient, db_session: AsyncSession):
    admin_token = await _make_admin_token(app_client, db_session, "complaints-admin@dekut.ac.ke")
    student_token = await _register(app_client, "complainant@dekut.ac.ke")

    filed = await app_client.post(
        "/api/complaints",
        json={"category": "maintenance", "details": "Broken tap in room B14"},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert filed.status_code == 201
    complaint_id = filed.json()["id"]

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    listed = await app_client.get("/api/admin/complaints", headers=admin_headers)
    assert listed.status_code == 200
    assert any(c["id"] == complaint_id for c in listed.json())

    filtered = await app_client.get("/api/admin/complaints", params={"status": "resolved"}, headers=admin_headers)
    assert filtered.json() == []

    updated = await app_client.patch(
        f"/api/admin/complaints/{complaint_id}/status", params={"status": "resolved"}, headers=admin_headers
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "resolved"

    invalid = await app_client.patch(
        f"/api/admin/complaints/{complaint_id}/status", params={"status": "not_a_status"}, headers=admin_headers
    )
    assert invalid.status_code == 422

    missing = await app_client.patch(
        "/api/admin/complaints/does-not-exist/status", params={"status": "resolved"}, headers=admin_headers
    )
    assert missing.status_code == 404

    insights = await app_client.get("/api/admin/insights", headers=admin_headers)
    assert insights.json()["complaint_status_counts"] == {"resolved": 1}
