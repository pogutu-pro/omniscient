from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.academic_repository import SqlAcademicRepository
from app.repositories.complaint_repository import SqlComplaintRepository
from app.repositories.hostel_repository import (
    HostelWriteNotSupported,
    MockHostelRepository,
    RumiaPostgresHostelRepository,
)
from app.repositories.past_paper_repository import SqlPastPaperRepository
from app.repositories.student_repository import SqlStudentRepository
from app.schemas.academics import CourseCreate, ProgrammeCreate, TimetableQuery
from app.schemas.complaint import ComplaintCreate
from app.schemas.housing import HostelCreate, HostelSearchParams, HostelUpdate
from app.schemas.past_paper import PastPaperSearchParams
from app.schemas.student import StudentCreate
from tests.factories import make_course, make_hostel, make_past_paper, make_student, make_timetable_entry


class _FakeSettings:
    api_url = "http://testserver"


async def test_hostel_search_filters_by_budget_and_area(db_session: AsyncSession):
    await make_hostel(db_session, name="Cheap Boma Room", area="Boma", price_ksh=4000)
    await make_hostel(db_session, name="Pricey Boma Room", area="Boma", price_ksh=15000)
    await make_hostel(db_session, name="Cheap Kamakwa Room", area="Kamakwa", price_ksh=4000)

    repo = MockHostelRepository(db_session, _FakeSettings())
    results = await repo.search(HostelSearchParams(max_budget_ksh=8000, area="Boma"))

    assert len(results) == 1
    assert results[0].name == "Cheap Boma Room"


async def test_hostel_search_verified_only(db_session: AsyncSession):
    await make_hostel(db_session, name="Verified", verified=True)
    await make_hostel(db_session, name="Unverified", verified=False)

    repo = MockHostelRepository(db_session, _FakeSettings())
    results = await repo.search(HostelSearchParams(verified_only=True))

    assert [h.name for h in results] == ["Verified"]


async def test_mock_hostel_repository_create_update_delete(db_session: AsyncSession):
    repo = MockHostelRepository(db_session, _FakeSettings())

    created = await repo.create(
        HostelCreate(name="Repo Test Hostel", area="Boma", distance_from_campus_km=0.4, price_ksh=5000)
    )
    assert created.source == "mock"

    updated = await repo.update(
        created.id,
        HostelUpdate(name="Renamed", area="Boma", distance_from_campus_km=0.4, price_ksh=5200, verified=True),
    )
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.verified is True

    assert await repo.delete(created.id) is True
    assert await repo.get_by_id(created.id) is None
    assert await repo.delete(created.id) is False


async def test_rumia_hostel_repository_writes_raise_not_supported():
    repo = RumiaPostgresHostelRepository("postgresql+asyncpg://user:pass@localhost/rumia", _FakeSettings())

    with pytest.raises(HostelWriteNotSupported):
        await repo.create(HostelCreate(name="XX", area="Boma", distance_from_campus_km=0.4, price_ksh=5000))
    with pytest.raises(HostelWriteNotSupported):
        await repo.update("some-id", HostelUpdate(name="XX", area="Boma", distance_from_campus_km=0.4, price_ksh=5000))
    with pytest.raises(HostelWriteNotSupported):
        await repo.delete("some-id")


async def test_academic_repository_programme_and_course_writes(db_session: AsyncSession):
    repo = SqlAcademicRepository(db_session)

    programme = await repo.create_programme(ProgrammeCreate(code="BSE", name="BSc Software Engineering"))
    assert programme.code == "BSE"

    course = await repo.create_course(
        CourseCreate(programme_id=programme.id, code="SSE 2101", name="Software Design", year_of_study=2, semester=1)
    )
    assert course.programme_id == programme.id

    assert await repo.delete_course(course.id) is True
    assert await repo.delete_course(course.id) is False


async def test_academic_repository_timetable_and_deadlines(db_session: AsyncSession):
    course = await make_course(db_session)
    await make_timetable_entry(db_session, course, day_of_week=0)
    await make_timetable_entry(db_session, course, day_of_week=2)

    repo = SqlAcademicRepository(db_session)
    monday_only = await repo.get_timetable(TimetableQuery(day_of_week=0))
    assert len(monday_only) == 1
    assert monday_only[0].course_code == course.code

    all_entries = await repo.get_timetable(TimetableQuery())
    assert len(all_entries) == 2


async def test_past_paper_repository_search_by_course_code(db_session: AsyncSession):
    course = await make_course(db_session)
    await make_past_paper(db_session, course, academic_year="2023/2024")
    await make_past_paper(db_session, course, academic_year="2022/2023")

    repo = SqlPastPaperRepository(db_session, _FakeSettings())
    results = await repo.search(PastPaperSearchParams(course_code="SCS 2101"))

    assert len(results) == 2
    assert all(r.course_code == "SCS 2101" for r in results)
    assert results[0].download_url.startswith("http://testserver/api/past-papers/")


async def test_complaint_repository_create_and_lookup(db_session: AsyncSession):
    student = await make_student(db_session)
    repo = SqlComplaintRepository(db_session)

    complaint = await repo.create(student.id, ComplaintCreate(category="maintenance", details="Broken tap in room B14"))
    assert complaint.reference_code.startswith("OMN-")
    assert complaint.status == "submitted"

    fetched = await repo.get_by_reference(complaint.reference_code)
    assert fetched is not None
    assert fetched.id == complaint.id

    mine = await repo.list_for_student(student.id)
    assert len(mine) == 1


async def test_student_repository_create_and_preferences(db_session: AsyncSession):
    repo = SqlStudentRepository(db_session)
    student = await repo.create(
        StudentCreate(
            registration_number="C026-01-0005/2023",
            full_name="New Student",
            email="new.student@dekut.ac.ke",
            password="Passw0rd!",
            programme="BSc IT",
            year_of_study=1,
        )
    )
    assert student.id

    updated = await repo.update_preferences(student.id, {"housing_max_budget_ksh": 9000})
    assert updated is not None
    assert updated.preferences["housing_max_budget_ksh"] == 9000
