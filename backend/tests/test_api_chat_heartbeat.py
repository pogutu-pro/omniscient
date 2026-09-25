"""A slow provider must not make the connection look dead: the stream
should interleave SSE keep-alive comment frames while waiting, so
intermediate proxies don't time it out and the frontend can tell "slow"
apart from "disconnected".
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient

from app.agents.providers.base import ChatTurn, LLMProvider, ToolCallProposal
from app.api.routes import chat as chat_route


class _SlowProvider(LLMProvider):
    display_name = "Slow Test Provider"

    async def classify_intent(self, message: str, history: list[ChatTurn], domains: list[str]) -> dict:
        await asyncio.sleep(0.08)
        return {"intent": "general", "confidence": 0.9, "parameters": {}}

    async def propose_tool_calls(self, **kwargs) -> list[ToolCallProposal]:
        return []

    async def stream_final_answer(self, **kwargs) -> AsyncIterator[str]:
        yield "Hello"


@pytest.fixture(autouse=True)
def _fast_heartbeat(monkeypatch):
    monkeypatch.setattr(chat_route, "HEARTBEAT_SECONDS", 0.02)


async def test_slow_provider_gets_keep_alive_frames(app_client: AsyncClient):
    from app.api.deps import get_llm_provider_dep
    from app.main import app

    app.dependency_overrides[get_llm_provider_dep] = lambda: _SlowProvider()
    try:
        raw_lines: list[str] = []
        async with app_client.stream("POST", "/api/chat", json={"message": "hello"}) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                raw_lines.append(line)
    finally:
        del app.dependency_overrides[get_llm_provider_dep]

    assert any(line.startswith(": keep-alive") for line in raw_lines), raw_lines
    data_lines = [line for line in raw_lines if line.startswith("data: ")]
    assert any('"type": "session"' in line for line in data_lines)
    assert any('"type": "stream_end"' in line for line in data_lines)
