from __future__ import annotations

import json

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_hostel


def _parse_sse(raw_lines: list[str]) -> list[dict]:
    events = []
    for line in raw_lines:
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


async def test_chat_stream_emits_session_status_and_done(app_client: AsyncClient, db_session: AsyncSession):
    await make_hostel(db_session, name="Boma View Hostel", area="Boma", price_ksh=6500)

    lines: list[str] = []
    async with app_client.stream(
        "POST", "/api/chat", json={"message": "Find me a hostel under KSh 8,000 near Boma."}
    ) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            lines.append(line)

    events = _parse_sse(lines)
    types = [e["type"] for e in events]

    assert types[0] == "session"
    assert "tool_call" in types
    assert "tool_result" in types
    assert "answer_chunk" in types
    assert types[-2] == "done"
    assert types[-1] == "stream_end"

    done_event = next(e for e in events if e["type"] == "done")
    assert done_event["data"]["intent"] == "housing"


async def test_chat_stream_persists_session_history(app_client: AsyncClient):
    lines: list[str] = []
    session_id = None
    async with app_client.stream("POST", "/api/chat", json={"message": "Hello there"}) as response:
        async for line in response.aiter_lines():
            lines.append(line)
    events = _parse_sse(lines)
    session_id = events[0]["session_id"]

    history_response = await app_client.get(f"/api/chat/sessions/{session_id}/messages")
    assert history_response.status_code == 200
    roles = [m["role"] for m in history_response.json()]
    assert roles[0] == "user"
    assert "assistant" in roles


async def test_chat_stream_unknown_session_returns_404(app_client: AsyncClient):
    response = await app_client.post("/api/chat", json={"session_id": "does-not-exist", "message": "Hi"})
    assert response.status_code == 404
