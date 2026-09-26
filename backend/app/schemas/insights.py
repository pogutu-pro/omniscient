from __future__ import annotations

from pydantic import BaseModel


class InsightsOut(BaseModel):
    """Real, already-captured signal about how students use Omniscient -
    not a claim that any model is being retrained. Intent counts come from
    every chat message's classified intent (schemas/chat.py:IntentResult,
    persisted on ChatMessage.intent); complaint counts come straight from
    the complaints table. This is what "learns from users" honestly means
    here: admins see what students actually ask and report, so they know
    what data to keep current."""

    total_students: int
    total_chat_sessions: int
    total_messages: int
    intent_counts: dict[str, int]
    # Thumbs-up / thumbs-down totals across all students, and the net of
    # them. Real captured signal, read from message_ratings - not a claim
    # that anything is being retrained.
    answer_rating_up: int
    answer_rating_down: int
    # Total times an answer was shared. Copying is not counted - sharing is
    # the point at which an answer leaves the app.
    total_shares: int
    complaint_category_counts: dict[str, int]
    complaint_status_counts: dict[str, int]
