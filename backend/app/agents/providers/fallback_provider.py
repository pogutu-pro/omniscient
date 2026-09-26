"""Failover across a primary and an optional fallback LLM provider.

A campus assistant that stops answering because one vendor returned a 429
is not a campus assistant. `FallbackProvider` presents the same
`LLMProvider` interface as a single provider, and on any `ProviderUnavailable`
from the current one it advances to the next and replays the same call.

Two properties matter for correctness:

- `display_name` is not fixed at construction. It is read from whichever
  provider is currently active, so the execution trace always names the
  model that actually produced the answer rather than the one that was
  configured first.
- Only `ProviderUnavailable` triggers a failover. Any other exception is a
  bug in this code or in the caller's, and retrying it on a second
  provider would hide that instead of surfacing it.

Once a provider fails it stays marked failed for the lifetime of the
process, so one turn does not pay the full timeout against a dead primary
and then again on every subsequent turn.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from app.agents.providers.base import AttachmentContent, ChatTurn, LLMProvider, ProviderUnavailable, ToolCallProposal
from app.core.logging import get_logger

logger = get_logger(component="fallback_provider")


class FallbackProvider(LLMProvider):
    def __init__(self, providers: list[LLMProvider]):
        usable = [p for p in providers if p is not None]
        if not usable:
            raise ProviderUnavailable("No usable LLM provider configured")
        self._providers = usable
        self._active = 0
        self._failed: set[int] = set()

    @property
    def display_name(self) -> str:  # type: ignore[override]
        return self._providers[self._active].display_name

    def _next_available(self) -> int | None:
        for i in range(len(self._providers)):
            if i not in self._failed:
                return i
        return None

    async def classify_intent(self, message: str, history: list[ChatTurn], domains: list[str]) -> dict:
        while True:
            provider = self._providers[self._active]
            try:
                return await provider.classify_intent(message, history, domains)
            except ProviderUnavailable as exc:
                if not await self._advance(exc, "classify_intent"):
                    raise

    async def propose_tool_calls(
        self, *, message: str, intent: str, parameters: dict, available_tools: list[dict], history: list[ChatTurn]
    ) -> list[ToolCallProposal]:
        while True:
            provider = self._providers[self._active]
            try:
                return await provider.propose_tool_calls(
                    message=message,
                    intent=intent,
                    parameters=parameters,
                    available_tools=available_tools,
                    history=history,
                )
            except ProviderUnavailable as exc:
                if not await self._advance(exc, "propose_tool_calls"):
                    raise

    async def stream_final_answer(
        self,
        *,
        message: str,
        intent: str,
        tool_results: list[dict],
        history: list[ChatTurn],
        attachments: list[AttachmentContent] | None = None,
    ) -> AsyncIterator[str]:
        while True:
            provider = self._providers[self._active]
            emitted = False
            try:
                async for delta in provider.stream_final_answer(
                    message=message,
                    intent=intent,
                    tool_results=tool_results,
                    history=history,
                    attachments=attachments,
                ):
                    emitted = True
                    yield delta
                return
            except ProviderUnavailable as exc:
                # Once tokens have reached the student, a retry would
                # splice two answers together into one incoherent reply.
                # Surface the failure and let the caller close the stream.
                if emitted:
                    logger.error(
                        "primary_provider_failed_mid_stream",
                        provider=provider.display_name,
                        stage="stream_final_answer",
                    )
                    raise
                if not await self._advance(exc, "stream_final_answer"):
                    raise

    async def _advance(self, exc: ProviderUnavailable, stage: str) -> bool:
        """Retire the active provider and move to the next usable one.

        Returns True when a fallback took over, False when the caller
        should re-raise the original failure.
        """
        failed_provider = self._providers[self._active]
        self._failed.add(self._active)
        nxt = self._next_available()
        if nxt is None:
            logger.error("all_llm_providers_failed", stage=stage, providers=len(self._providers))
            return False
        self._active = nxt
        replacement = self._providers[nxt]
        logger.warning(
            "llm_provider_fallback",
            stage=stage,
            failed=failed_provider.display_name,
            failed_reason=str(exc)[:200],
            using=replacement.display_name,
        )
        return True
