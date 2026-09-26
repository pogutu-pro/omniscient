from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import orchestrator, router
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
        hostel_repo=MockHostelRepository(db_session, _FakeSettings()),
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
    # The trace says what was searched for, not just that a search ran.
    assert tool_calls[0].arguments == {"area": "Boma", "max_budget_ksh": 8000}
    tool_results = [e for e in events if e.type == "tool_result"]
    assert tool_results[0].status == "completed"
    assert tool_results[0].duration_ms is not None and tool_results[0].duration_ms >= 0
    answer = "".join(e.message for e in events if e.type == "answer_chunk")
    assert "hostel option" in answer
    content_blocks = [e for e in events if e.type == "content_block"]
    table_block = next(b for b in content_blocks if b.data["type"] == "table")
    assert table_block.data["rows"][0]["name"] == "Boma View Hostel"
    done = [e for e in events if e.type == "done"][0]
    assert done.data["intent"] == "housing"
    assert done.data["preference_updates"]["housing_max_budget_ksh"] == 8000


async def test_orchestrator_academics_flow_selects_get_timetable_tool(db_session: AsyncSession):
    await make_course(db_session)
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


def test_public_arguments_drops_internal_keys_and_truncates():
    """Arguments are echoed to the browser, so internal routing hints must
    not leak and a pasted question must not be reflected back in full."""
    from app.agents.orchestrator import _public_arguments

    assert _public_arguments({"max_budget_ksh": 8000, "area": "Boma"}) == {"max_budget_ksh": 8000, "area": "Boma"}
    assert "_is_status_check" not in _public_arguments({"_is_status_check": True, "area": "Boma"})
    assert _public_arguments({"query": "x" * 500})["query"].endswith("…")
    assert len(_public_arguments({"query": "x" * 500})["query"]) < 100
    # Bounded, so a tool with many parameters cannot bloat every SSE frame.
    assert len(_public_arguments({f"k{i}": i for i in range(50)})) == 8
    # Lists stay JSON-serialisable for the wire.
    assert _public_arguments({"amenities": ["wifi", "water"]}) == {"amenities": ["wifi", "water"]}


@pytest.mark.parametrize(
    "message",
    [
        "what about Kahawa Ridge?",
        "Kahawa Ridge hostels",
        "show me hostels in Nyeri View",
        "and Near Gate A?",
        "any in Embassy Area?",
    ],
)
async def test_mock_provider_understands_a_follow_up_that_only_names_a_place(db_session: AsyncSession, message: str):
    """A follow-up like "what about Kahawa Ridge?" carries no domain keyword.
    Treating it as a general question answered the student with "what would
    you like to do?" - the opposite of continuing the conversation."""
    await make_hostel(db_session, name="Ridge Hostel", area="Kahawa Ridge", price_ksh=6000)
    provider = MockProvider()

    events = await _run_and_collect(
        message=message,
        history=[],
        ctx=_ctx(db_session),
        registry=build_default_registry(),
        provider=provider,
    )

    tool_calls = [e for e in events if e.type == "tool_call"]
    assert tool_calls, f"{message!r} was not routed to a tool"
    assert tool_calls[0].tool == "search_hostels"
    # The place the student actually named must reach the search, rather than
    # being replaced by a remembered area.
    assert "area" in (tool_calls[0].arguments or {})


async def test_mock_provider_knows_the_real_dekut_localities(db_session: AsyncSession):
    """The offline provider's area list previously held only the seeded demo
    areas, so every real DeKUT locality resolved to nothing."""
    from app.agents.providers.mock_provider import _extract_area

    for area in ("Kahawa Ridge", "Nyeri View", "Near Gate A", "Nyaribo", "Boma"):
        assert _extract_area(f"hostels in {area}") == area


async def test_mock_provider_prefers_the_longest_matching_area(db_session: AsyncSession):
    from app.agents.providers.mock_provider import _extract_area

    assert _extract_area("hostels near Near Gate A") == "Near Gate A"


async def test_a_general_question_is_still_general(db_session: AsyncSession):
    """Rescuing follow-ups must not turn every short message into housing."""
    provider = MockProvider()
    result = await provider.classify_intent("thanks!", [], ["housing", "academics"])
    assert result["intent"] == "general"

    result = await provider.classify_intent("who is the vice chancellor?", [], ["housing", "academics"])
    assert result["intent"] == "general"
