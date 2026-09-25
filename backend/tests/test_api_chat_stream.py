from __future__ import annotations

import base64
import json

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import make_hostel

# Smallest possible valid PNG (1x1 transparent pixel).
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/auth/register",
        json={
            "registration_number": f"C026-01-{abs(hash(email)) % 100000:05d}/2023",
            "full_name": "Attachment Tester",
            "email": email,
            "password": "Passw0rd!",
            "programme": "BSc Computer Science",
            "year_of_study": 2,
        },
    )
    return response.json()["access_token"]


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

    content_block_events = [e for e in events if e["type"] == "content_block"]
    assert content_block_events, "expected at least one content_block event for a structured hostel search"
    table_blocks = [e for e in content_block_events if e["data"]["type"] == "table"]
    assert table_blocks and table_blocks[0]["data"]["rows"][0]["name"] == "Boma View Hostel"


async def test_chat_stream_persists_content_blocks_on_assistant_message(app_client: AsyncClient, db_session: AsyncSession):
    await make_hostel(db_session, name="Boma View Hostel", area="Boma", price_ksh=6500)

    lines: list[str] = []
    async with app_client.stream(
        "POST", "/api/chat", json={"message": "Find me a hostel under KSh 8,000 near Boma."}
    ) as response:
        async for line in response.aiter_lines():
            lines.append(line)
    events = _parse_sse(lines)
    session_id = events[0]["session_id"]

    history = await app_client.get(f"/api/chat/sessions/{session_id}/messages")
    assistant_message = next(m for m in history.json() if m["role"] == "assistant")
    assert assistant_message["content_blocks"]
    assert assistant_message["content_blocks"][0]["type"] == "table"


async def test_chat_with_image_attachment_gives_honest_reply_and_persists_attachment(app_client: AsyncClient):
    token = await _register(app_client, "attach-image@dekut.ac.ke")
    headers = {"Authorization": f"Bearer {token}"}

    upload = await app_client.post(
        "/api/files/upload",
        files={"file": ("photo.png", _TINY_PNG, "image/png")},
        headers=headers,
    )
    assert upload.status_code == 201
    key = upload.json()["key"]

    lines: list[str] = []
    async with app_client.stream(
        "POST",
        "/api/chat",
        json={"message": "What's in this photo?", "attachments": [{"key": key, "content_type": "image/png", "file_name": "photo.png"}]},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            lines.append(line)

    events = _parse_sse(lines)
    # The attachment is shown once, on the student's own message bubble
    # (via the persisted attachment below) - the assistant's reply is not
    # expected to echo it back as a second, redundant content block.
    assert not [e for e in events if e["type"] == "content_block"]

    answer = "".join(e["message"] for e in events if e["type"] == "answer_chunk")
    assert "offline demo mode" in answer

    session_id = events[0]["session_id"]
    history = await app_client.get(f"/api/chat/sessions/{session_id}/messages", headers=headers)
    user_message = history.json()[0]
    assert user_message["attachments"][0]["file_name"] == "photo.png"


async def test_chat_with_unknown_attachment_key_returns_404(app_client: AsyncClient):
    token = await _register(app_client, "attach-missing@dekut.ac.ke")
    headers = {"Authorization": f"Bearer {token}"}

    response = await app_client.post(
        "/api/chat",
        json={
            "message": "Look at this",
            "attachments": [{"key": "uploads/does-not-exist.png", "content_type": "image/png", "file_name": "x.png"}],
        },
        headers=headers,
    )
    assert response.status_code == 404


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
