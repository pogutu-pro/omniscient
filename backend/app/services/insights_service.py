"""Aggregates real, already-captured usage signal for the admin dashboard.

Deliberately a plain query module rather than a "repository" — insights
cut across students, chat messages, and complaints, and exist purely for
reporting. Nothing here writes anything or feeds a model; it reads what
the app already persisted.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatMessage, ChatSession
from app.models.student import Student
from app.repositories.complaint_repository import ComplaintRepository
from app.repositories.message_rating_repository import SqlMessageRatingRepository
from app.schemas.insights import InsightsOut


async def build_insights(session: AsyncSession, complaint_repo: ComplaintRepository) -> InsightsOut:
    total_students = (await session.execute(select(func.count(Student.id)))).scalar_one()
    total_chat_sessions = (await session.execute(select(func.count(ChatSession.id)))).scalar_one()
    total_messages = (await session.execute(select(func.count(ChatMessage.id)))).scalar_one()

    intent_stmt = (
        select(ChatMessage.intent, func.count(ChatMessage.id))
        .where(ChatMessage.role == "user", ChatMessage.intent.is_not(None))
        .group_by(ChatMessage.intent)
    )
    intent_rows = (await session.execute(intent_stmt)).all()
    intent_counts = {intent: count for intent, count in intent_rows if intent}

    rating_counts = await SqlMessageRatingRepository(session).counts()
    total_shares = (
        await session.execute(select(func.coalesce(func.sum(ChatMessage.share_count), 0)))
    ).scalar_one()

    return InsightsOut(
        total_students=total_students,
        total_chat_sessions=total_chat_sessions,
        total_messages=total_messages,
        intent_counts=intent_counts,
        answer_rating_up=rating_counts["up"],
        answer_rating_down=rating_counts["down"],
        total_shares=int(total_shares),
        complaint_category_counts=await complaint_repo.count_by_category(),
        complaint_status_counts=await complaint_repo.count_by_status(),
    )
