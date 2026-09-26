from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatMessage, ChatSession, MessageRating
from app.repositories.message_rating_repository import MessageNotFound, SqlMessageRatingRepository
from tests.factories import make_student


async def _assistant_message(db_session: AsyncSession, *, role: str = "assistant", owner_id: str | None = None) -> ChatMessage:
    session = ChatSession(student_id=owner_id, title="t")
    db_session.add(session)
    await db_session.flush()
    message = ChatMessage(session_id=session.id, role=role, content="Here are some hostels.")
    db_session.add(message)
    await db_session.commit()
    return message


async def test_rating_a_reply_is_recorded(db_session: AsyncSession):
    message = await _assistant_message(db_session)
    student = await make_student(db_session, email="rater@dekut.ac.ke", registration_number="C026-01-9001/2023")

    repo = SqlMessageRatingRepository(db_session)
    assert await repo.rate(message_id=message.id, student_id=student.id, rating=1) == 1

    assert await repo.ratings_for_messages([message.id], student.id) == {message.id: 1}


async def test_re_rating_replaces_rather_than_adds(db_session: AsyncSession):
    """A thumbs control is expected to let a student change their mind.
    Appending instead would double-count and make the admin totals wrong."""
    message = await _assistant_message(db_session)
    student = await make_student(db_session, email="rater@dekut.ac.ke", registration_number="C026-01-9001/2023")
    repo = SqlMessageRatingRepository(db_session)

    await repo.rate(message_id=message.id, student_id=student.id, rating=1)
    await repo.rate(message_id=message.id, student_id=student.id, rating=-1)

    rows = (await db_session.execute(MessageRating.__table__.select())).fetchall()
    assert len(rows) == 1
    assert await repo.ratings_for_messages([message.id], student.id) == {message.id: -1}


async def test_clearing_a_rating_removes_it(db_session: AsyncSession):
    message = await _assistant_message(db_session)
    student = await make_student(db_session, email="rater@dekut.ac.ke", registration_number="C026-01-9001/2023")
    repo = SqlMessageRatingRepository(db_session)

    await repo.rate(message_id=message.id, student_id=student.id, rating=1)
    assert await repo.clear(message_id=message.id, student_id=student.id) is True
    assert await repo.ratings_for_messages([message.id], student.id) == {}
    # Clearing again is a no-op rather than an error.
    assert await repo.clear(message_id=message.id, student_id=student.id) is False


async def test_one_students_rating_does_not_leak_to_another(db_session: AsyncSession):
    message = await _assistant_message(db_session)
    first = await make_student(db_session, email="one@dekut.ac.ke", registration_number="C026-01-9002/2023")
    second = await make_student(db_session, email="two@dekut.ac.ke", registration_number="C026-01-9003/2023")
    repo = SqlMessageRatingRepository(db_session)

    await repo.rate(message_id=message.id, student_id=first.id, rating=1)

    assert await repo.ratings_for_messages([message.id], second.id) == {}


async def test_only_assistant_replies_are_ratable(db_session: AsyncSession):
    user_message = await _assistant_message(db_session, role="user")
    student = await make_student(db_session, email="rater@dekut.ac.ke", registration_number="C026-01-9001/2023")

    with pytest.raises(MessageNotFound):
        await SqlMessageRatingRepository(db_session).rate(
            message_id=user_message.id, student_id=student.id, rating=1
        )


async def test_rating_an_unknown_message_is_rejected(db_session: AsyncSession):
    student = await make_student(db_session, email="rater@dekut.ac.ke", registration_number="C026-01-9001/2023")

    with pytest.raises(MessageNotFound):
        await SqlMessageRatingRepository(db_session).rate(message_id="nope", student_id=student.id, rating=1)


async def test_counts_split_up_and_down(db_session: AsyncSession):
    message = await _assistant_message(db_session)
    a = await make_student(db_session, email="a@dekut.ac.ke", registration_number="C026-01-9004/2023")
    b = await make_student(db_session, email="b@dekut.ac.ke", registration_number="C026-01-9005/2023")
    repo = SqlMessageRatingRepository(db_session)

    await repo.rate(message_id=message.id, student_id=a.id, rating=1)
    await repo.rate(message_id=message.id, student_id=b.id, rating=-1)
    # A second up from a different student.
    other = await _assistant_message(db_session)
    c = await make_student(db_session, email="c@dekut.ac.ke", registration_number="C026-01-9006/2023")
    await repo.rate(message_id=other.id, student_id=c.id, rating=1)

    assert await repo.counts() == {"up": 2, "down": 1}


async def test_counts_are_zero_before_any_ratings(db_session: AsyncSession):
    assert await SqlMessageRatingRepository(db_session).counts() == {"up": 0, "down": 0}


# --- API surface ---

async def _auth_headers(client: AsyncClient, email: str = "rater@dekut.ac.ke") -> dict:
    res = await client.post(
        "/api/auth/register",
        json={
            "registration_number": f"C026-01-{email[:4].upper()}/2023",
            "full_name": "Rater",
            "email": email,
            "password": "Passw0rd!",
            "programme": "BSc Computer Science",
            "year_of_study": 2,
        },
    )
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def test_rating_endpoint_round_trip(app_client: AsyncClient):
    headers = await _auth_headers(app_client)

    # Ask something so there is a real assistant message to rate.
    async with app_client.stream("POST", "/api/chat", json={"message": "hostels near campus"}, headers=headers) as r:
        session_lines = [line async for line in r.aiter_lines()]
    session_id = next(
        __import__("json").loads(line[6:])["session_id"]
        for line in session_lines
        if line.startswith("data: ") and '"session"' in line
    )

    history = await app_client.get(f"/api/chat/sessions/{session_id}/messages", headers=headers)
    assistant = [m for m in history.json() if m["role"] == "assistant"][0]
    message_id = assistant["id"]
    # New history carries the rating field, unset to begin with.
    assert assistant["rating"] is None

    up = await app_client.put(f"/api/chat/messages/{message_id}/rating", json={"rating": 1}, headers=headers)
    assert up.status_code == 200
    assert up.json()["rating"] == 1

    reread = await app_client.get(f"/api/chat/sessions/{session_id}/messages", headers=headers)
    assert [m for m in reread.json() if m["id"] == message_id][0]["rating"] == 1

    cleared = await app_client.delete(f"/api/chat/messages/{message_id}/rating", headers=headers)
    assert cleared.status_code == 204

    after = await app_client.get(f"/api/chat/sessions/{session_id}/messages", headers=headers)
    assert [m for m in after.json() if m["id"] == message_id][0]["rating"] is None


async def test_rating_requires_authentication(app_client: AsyncClient):
    res = await app_client.put("/api/chat/messages/whatever/rating", json={"rating": 1})
    assert res.status_code == 401


async def test_rating_rejects_a_value_that_is_not_a_thumb(app_client: AsyncClient):
    headers = await _auth_headers(app_client)
    res = await app_client.put("/api/chat/messages/whatever/rating", json={"rating": 5}, headers=headers)
    assert res.status_code == 422


async def test_rating_an_unknown_message_is_404(app_client: AsyncClient):
    headers = await _auth_headers(app_client)
    res = await app_client.put("/api/chat/messages/does-not-exist/rating", json={"rating": 1}, headers=headers)
    assert res.status_code == 404


async def test_history_still_reads_without_a_token(app_client: AsyncClient):
    """Ratings are personalised, but history must not have become private
    as a side effect of adding them."""
    headers = await _auth_headers(app_client)
    async with app_client.stream("POST", "/api/chat", json={"message": "hello"}, headers=headers) as r:
        lines = [line async for line in r.aiter_lines()]
    session_id = next(
        __import__("json").loads(line[6:])["session_id"]
        for line in lines
        if line.startswith("data: ") and '"session"' in line
    )

    anonymous = await app_client.get(f"/api/chat/sessions/{session_id}/messages")
    assert anonymous.status_code == 200
    # No token, so no ratings are disclosed rather than someone else's.
    assert all(m["rating"] is None for m in anonymous.json())
