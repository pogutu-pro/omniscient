"""LLM-unavailable is a real, expected failure mode: the router/orchestrator
must degrade gracefully instead of crashing or fabricating a result.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import orchestrator
from app.agents.providers.base import ChatTurn, LLMProvider, ProviderUnavailable, ToolCallProposal
from app.repositories.academic_repository import SqlAcademicRepository
from app.repositories.complaint_repository import SqlComplaintRepository
from app.repositories.hostel_repository import MockHostelRepository
from app.repositories.past_paper_repository import SqlPastPaperRepository
from app.tools.build import build_default_registry
from app.tools.registry import ToolContext


class _FakeSettings:
    api_url = "http://testserver"


class _AlwaysDownProvider(LLMProvider):
    async def classify_intent(self, message: str, history: list[ChatTurn], domains: list[str]) -> dict:
        raise ProviderUnavailable("simulated outage")

    async def propose_tool_calls(self, **kwargs) -> list[ToolCallProposal]:
        raise ProviderUnavailable("simulated outage")

    async def stream_final_answer(self, **kwargs) -> AsyncIterator[str]:
        raise ProviderUnavailable("simulated outage")
        yield ""  # pragma: no cover -- unreachable, keeps this an async generator


def _ctx(db_session: AsyncSession) -> ToolContext:
    return ToolContext(
        hostel_repo=MockHostelRepository(db_session),
        academic_repo=SqlAcademicRepository(db_session),
        past_paper_repo=SqlPastPaperRepository(db_session, _FakeSettings()),
        complaint_repo=SqlComplaintRepository(db_session),
    )


async def test_orchestrator_degrades_gracefully_when_provider_is_down(db_session: AsyncSession):
    registry = build_default_registry()
    events = []
    async for event in orchestrator.run(
        message="Find me a hostel",
        history=[],
        ctx=_ctx(db_session),
        registry=registry,
        provider=_AlwaysDownProvider(),
    ):
        events.append(event)

    assert any(e.type == "error" for e in events)
    assert any(e.type == "done" for e in events)
    # Never fabricates a tool result when the provider is unreachable.
    assert not [e for e in events if e.type == "tool_result"]
