from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatMessage, ChatSession, TraceEvent


class ChatRepository(ABC):
    @abstractmethod
    async def create_session(self, student_id: str | None) -> ChatSession: ...

    @abstractmethod
    async def get_session(self, session_id: str) -> ChatSession | None: ...

    @abstractmethod
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        intent: str | None,
        content_blocks: list[dict] | None = None,
        attachments: list[dict] | None = None,
    ) -> ChatMessage: ...

    @abstractmethod
    async def list_messages(self, session_id: str) -> list[ChatMessage]: ...

    @abstractmethod
    async def add_trace_event(
        self, session_id: str, message_id: str | None, event_type: str, payload: dict
    ) -> TraceEvent: ...

    @abstractmethod
    async def set_title(self, session_id: str, title: str) -> None: ...


class SqlChatRepository(ChatRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_session(self, student_id: str | None) -> ChatSession:
        chat_session = ChatSession(student_id=student_id)
        self._session.add(chat_session)
        await self._session.commit()
        await self._session.refresh(chat_session)
        return chat_session

    async def get_session(self, session_id: str) -> ChatSession | None:
        return await self._session.get(ChatSession, session_id)

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        intent: str | None = None,
        content_blocks: list[dict] | None = None,
        attachments: list[dict] | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            intent=intent,
            content_blocks=content_blocks,
            attachments=attachments,
        )
        self._session.add(message)
        await self._session.commit()
        await self._session.refresh(message)
        return message

    async def list_messages(self, session_id: str) -> list[ChatMessage]:
        stmt = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def add_trace_event(
        self, session_id: str, message_id: str | None, event_type: str, payload: dict
    ) -> TraceEvent:
        event = TraceEvent(session_id=session_id, message_id=message_id, event_type=event_type, payload=payload)
        self._session.add(event)
        await self._session.commit()
        return event

    async def set_title(self, session_id: str, title: str) -> None:
        chat_session = await self.get_session(session_id)
        if not chat_session:
            return
        chat_session.title = title[:157] + "..." if len(title) > 160 else title
        await self._session.commit()
