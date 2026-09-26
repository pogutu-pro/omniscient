"""Reading and recording a student's rating on an assistant reply.

A rating is per (message, student): setting one replaces any previous
verdict, and clearing removes it. That is the behaviour a thumbs control is
expected to have - tapping the other thumb should change your mind, not add
a second opinion - and it also keeps the aggregate counts honest, which a
naive append-only table would not.
"""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import MessageRating


class MessageNotFound(Exception):
    """The message id does not exist, or is not an assistant reply."""


class SqlMessageRatingRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def rate(self, *, message_id: str, student_id: str, rating: int) -> int:
        """Record (or replace) a verdict. Returns the stored rating.

        The assistant-role check is here rather than in the route so there is
        one place that decides what is ratable.
        """
        from app.models.chat import ChatMessage

        message = await self._session.get(ChatMessage, message_id)
        if message is None or message.role != "assistant":
            raise MessageNotFound(message_id)

        # upsert: one row per (message, student). The on_conflict_do_update
        # form is used rather than a read-then-write so two rapid taps
        # cannot race into two rows.
        stmt = (
            pg_insert(MessageRating)
            .values(id=_new_id(), message_id=message_id, student_id=student_id, rating=rating)
            .on_conflict_do_update(
                index_elements=["message_id", "student_id"],
                set_={"rating": rating, "updated_at": func.now()},
            )
        )
        # SQLite (used by the test suite) has no ON CONFLICT DO UPDATE with
        # the same ergonomics via the postgres dialect, so fall back to a
        # portable update-then-insert.
        if self._session.bind is not None and self._session.bind.dialect.name == "sqlite":
            existing = await self._session.execute(
                select(MessageRating).where(
                    MessageRating.message_id == message_id,
                    MessageRating.student_id == student_id,
                )
            )
            row = existing.scalar_one_or_none()
            if row is None:
                self._session.add(
                    MessageRating(message_id=message_id, student_id=student_id, rating=rating)
                )
            else:
                row.rating = rating
            await self._session.commit()
            return rating

        await self._session.execute(stmt)
        await self._session.commit()
        return rating

    async def clear(self, *, message_id: str, student_id: str) -> bool:
        result = await self._session.execute(
            delete(MessageRating).where(
                MessageRating.message_id == message_id,
                MessageRating.student_id == student_id,
            )
        )
        await self._session.commit()
        return bool(result.rowcount)

    async def ratings_for_messages(self, message_ids: list[str], student_id: str) -> dict[str, int]:
        """This student's own verdict per message, so a reloaded conversation
        shows the thumbs they already pressed."""
        if not message_ids:
            return {}
        rows = await self._session.execute(
            select(MessageRating.message_id, MessageRating.rating).where(
                MessageRating.message_id.in_(message_ids),
                MessageRating.student_id == student_id,
            )
        )
        return {message_id: rating for message_id, rating in rows.all()}

    async def counts(self) -> dict[str, int]:
        """Aggregate up/down totals across every student, for admin insights."""
        rows = await self._session.execute(
            select(MessageRating.rating, func.count(MessageRating.id)).group_by(MessageRating.rating)
        )
        tally = {1: 0, -1: 0}
        for rating, count in rows.all():
            tally[rating] = count
        return {"up": tally.get(1, 0), "down": tally.get(-1, 0)}


def _new_id() -> str:
    from app.db.base import new_uuid

    return new_uuid()
