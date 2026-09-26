from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.academic_repository import SqlAcademicRepository
from app.repositories.complaint_repository import SqlComplaintRepository
from app.repositories.hostel_repository import MockHostelRepository
from app.repositories.past_paper_repository import SqlPastPaperRepository
from app.tools.build import build_default_registry
from app.tools.registry import ToolContext
from tests.factories import make_course, make_hostel, make_student


class _FakeSettings:
    api_url = "http://testserver"


def _ctx(db_session: AsyncSession, student_id: str | None = None) -> ToolContext:
    return ToolContext(
        hostel_repo=MockHostelRepository(db_session, _FakeSettings()),
        academic_repo=SqlAcademicRepository(db_session),
        past_paper_repo=SqlPastPaperRepository(db_session, _FakeSettings()),
        complaint_repo=SqlComplaintRepository(db_session),
        student_id=student_id,
    )


async def test_search_hostels_tool_returns_typed_results(db_session: AsyncSession):
    await make_hostel(db_session, name="Boma View Hostel", price_ksh=6500)
    registry = build_default_registry()

    result = await registry.call("search_hostels", {"max_budget_ksh": 8000}, _ctx(db_session))

    assert result.ok
    assert result.data[0]["name"] == "Boma View Hostel"


async def test_search_hostels_tool_rejects_invalid_input(db_session: AsyncSession):
    registry = build_default_registry()
    result = await registry.call("search_hostels", {"max_budget_ksh": -5}, _ctx(db_session))
    assert not result.ok
    assert result.error is not None


async def test_get_timetable_tool(db_session: AsyncSession):
    await make_course(db_session)
    registry = build_default_registry()
    result = await registry.call("get_timetable", {"programme_code": "BCS"}, _ctx(db_session))
    assert result.ok


async def test_file_complaint_requires_authentication(db_session: AsyncSession):
    registry = build_default_registry()
    result = await registry.call(
        "file_complaint", {"category": "maintenance", "details": "Broken tap in the shared bathroom"}, _ctx(db_session)
    )
    assert not result.ok
    assert result.error == "unauthorized"


async def test_file_complaint_succeeds_when_authenticated(db_session: AsyncSession):
    student = await make_student(db_session)
    registry = build_default_registry()
    result = await registry.call(
        "file_complaint",
        {"category": "maintenance", "details": "Broken tap in the shared bathroom"},
        _ctx(db_session, student_id=student.id),
    )
    assert result.ok
    assert result.data["reference_code"].startswith("OMN-")


async def test_get_complaint_status_forbids_other_students(db_session: AsyncSession):
    owner = await make_student(db_session, email="owner@dekut.ac.ke", registration_number="C026-01-0010/2023")
    intruder = await make_student(db_session, email="intruder@dekut.ac.ke", registration_number="C026-01-0011/2023")
    registry = build_default_registry()

    filed = await registry.call(
        "file_complaint", {"category": "security", "details": "Suspicious person near the gate"}, _ctx(db_session, student_id=owner.id)
    )
    reference_code = filed.data["reference_code"]

    result = await registry.call(
        "get_complaint_status", {"reference_code": reference_code}, _ctx(db_session, student_id=intruder.id)
    )
    assert not result.ok
    assert result.error == "forbidden"


async def test_file_complaint_rejects_unknown_category(db_session: AsyncSession):
    student = await make_student(db_session)
    registry = build_default_registry()
    result = await registry.call(
        "file_complaint",
        {"category": "not_a_real_category", "details": "This should be rejected by the tool"},
        _ctx(db_session, student_id=student.id),
    )
    assert not result.ok
    assert result.error == "invalid_category"


async def test_unknown_tool_name_returns_error(db_session: AsyncSession):
    registry = build_default_registry()
    result = await registry.call("delete_all_students", {}, _ctx(db_session))
    assert not result.ok
    assert "Unknown tool" in result.error
