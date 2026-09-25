"""LLM-driven intent router.

Calls the configured provider to classify a message, then validates the
result into `IntentResult` before anything downstream sees it. Raw model
output is never trusted directly: an out-of-domain intent, a
malformed/missing confidence, or garbage parameters all fall back to a
safe default instead of propagating.
"""
from __future__ import annotations

from app.agents.providers.base import ChatTurn, LLMProvider
from app.schemas.chat import Domain, IntentResult

VALID_DOMAINS: list[Domain] = ["housing", "academics", "past_papers", "complaints", "general"]


async def classify(provider: LLMProvider, message: str, history: list[ChatTurn]) -> IntentResult:
    raw = await provider.classify_intent(message, history, list(VALID_DOMAINS))
    return _validate(raw)


def _validate(raw: dict) -> IntentResult:
    intent = raw.get("intent")
    if intent not in VALID_DOMAINS:
        return IntentResult(intent="general", confidence=0.5, parameters={})

    confidence = raw.get("confidence", 0.5)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    parameters = raw.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {}

    try:
        return IntentResult(intent=intent, confidence=confidence, parameters=parameters)
    except Exception:
        return IntentResult(intent="general", confidence=0.5, parameters={})
