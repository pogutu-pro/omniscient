from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import orchestrator, router
from app.agents.providers.base import ChatTurn
from app.agents.providers.mock_provider import MockProvider
from app.repositories.academic_repository import SqlAcademicRepository
from app.repositories.complaint_repository import SqlComplaintRepository
from app.repositories.hostel_repository import MockHostelRepository
from app.repositories.past_paper_repository import SqlPastPaperRepository
from app.tools.build import build_default_registry
from app.tools.registry import ToolContext
from tests.factories import make_course, make_hostel, make_past_paper, make_student


class _FakeSettings:
    api_url = "http://testserver"


def _ctx(db_session: AsyncSession, student_id: str | None = None) -> ToolContext:
    return ToolContext(
        hostel_repo=MockHostelRepository(db_session),
        academic_repo=SqlAcademicRepository(db_session),
        past_paper_repo=SqlPastPaperRepository(db_session, _FakeSettings()),
        complaint_repo=SqlComplaintRepository(db_session),
        student_id=student_id,
    )


async def _run_and_collect(**kwargs) -> list:
    events = []
    async for event in orchestrator.run(**kwargs):
        events.append(event)
    return events


@pytest.mark.parametrize(
    "message,expected_intent",
    [
        ("Find me a hostel under KSh 8,000 near Boma.", "housing"),
        ("What classes do I have tomorrow?", "academics"),
        ("Find Database Systems past papers.", "past_papers"),
        ("I want to report a broken water tap.", "complaints"),
    ],
)
async def test_router_classifies_the_four_canonical_messages(message: str, expected_intent: str):
    provider = MockProvider()
    result = await router.classify(provider, message, [])
    assert result.intent == expected_intent


async def test_orchestrator_housing_flow_selects_search_hostels_tool(db_session: AsyncSession):
    await make_hostel(db_session, name="Boma View Hostel", area="Boma", price_ksh=6500)
    provider = MockProvider()
    registry = build_default_registry()

    events = await _run_and_collect(
        message="Find me a hostel under KSh 8,000 near Boma.",
        history=[],
        ctx=_ctx(db_session),
        registry=registry,
        provider=provider,
    )

    tool_calls = [e for e in events if e.type == "tool_call"]
    assert tool_calls and tool_calls[0].tool == "search_hostels"
    tool_results = [e for e in events if e.type == "tool_result"]
    assert tool_results[0].status == "completed"
    answer = "".join(e.message for e in events if e.type == "answer_chunk")
    assert "Boma View Hostel" in answer
    done = [e for e in events if e.type == "done"][0]
    assert done.data["intent"] == "housing"
    assert done.data["preference_updates"]["housing_max_budget_ksh"] == 8000


async def test_orchestrator_academics_flow_selects_get_timetable_tool(db_session: AsyncSession):
    course = await make_course(db_session)
    provider = MockProvider()
    registry = build_default_registry()

    events = await _run_and_collect(
        message="What classes do I have tomorrow?",
        history=[],
        ctx=_ctx(db_session),
        registry=registry,
        provider=provider,
    )

    tool_calls = [e for e in events if e.type == "tool_call"]
    assert tool_calls and tool_calls[0].tool == "get_timetable"


async def test_orchestrator_past_papers_flow_selects_search_past_papers_tool(db_session: AsyncSession):
    course = await make_course(db_session, name="Database Systems", code="SCS 2101")
    await make_past_paper(db_session, course)
    provider = MockProvider()
    registry = build_default_registry()

    events = await _run_and_collect(
        message="Find Database Systems past papers.",
        history=[],
        ctx=_ctx(db_session),
        registry=registry,
        provider=provider,
    )

    tool_calls = [e for e in events if e.type == "tool_call"]
    assert tool_calls and tool_calls[0].tool == "search_past_papers"
    tool_results = [e for e in events if e.type == "tool_result"]
    assert "1" in tool_results[0].summary or "paper" in tool_results[0].summary.lower()


async def test_orchestrator_complaints_flow_files_when_authenticated(db_session: AsyncSession):
    student = await make_student(db_session)
    provider = MockProvider()
    registry = build_default_registry()

    events = await _run_and_collect(
        message="I want to report a broken water tap.",
        history=[],
        ctx=_ctx(db_session, student_id=student.id),
        registry=registry,
        provider=provider,
    )

    tool_calls = [e for e in events if e.type == "tool_call"]
    assert tool_calls and tool_calls[0].tool == "file_complaint"
    tool_results = [e for e in events if e.type == "tool_result"]
    assert tool_results[0].status == "completed"
    answer = "".join(e.message for e in events if e.type == "answer_chunk")
    assert "OMN-" in answer


async def test_orchestrator_complaints_flow_fails_gracefully_when_anonymous(db_session: AsyncSession):
    provider = MockProvider()
    registry = build_default_registry()

    events = await _run_and_collect(
        message="I want to report a broken water tap.",
        history=[],
        ctx=_ctx(db_session, student_id=None),
        registry=registry,
        provider=provider,
    )

    tool_results = [e for e in events if e.type == "tool_result"]
    assert tool_results[0].status == "failed"
    answer = "".join(e.message for e in events if e.type == "answer_chunk")
    assert "signed in" in answer.lower()


async def test_orchestrator_general_intent_never_calls_tools(db_session: AsyncSession):
    provider = MockProvider()
    registry = build_default_registry()

    events = await _run_and_collect(
        message="Hello, what can you help me with?",
        history=[],
        ctx=_ctx(db_session),
        registry=registry,
        provider=provider,
    )

    assert not [e for e in events if e.type == "tool_call"]
    assert any(e.type == "done" for e in events)
