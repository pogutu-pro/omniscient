"""AI provider abstraction.

Nothing in the router or orchestrator imports a specific LLM SDK — they
only depend on this interface, so `LLM_PROVIDER` in configuration decides
which implementation runs. `MockProvider` is deterministic and needs no
network access or API key, so the whole agent stack (router, tools,
streaming trace, final answers) works completely offline; `AnthropicProvider`
swaps in real model calls when `LLM_API_KEY` is configured.

Every method returns/streams data the caller must still validate — a
provider is never trusted to authorize an action or to have produced a
safe/well-formed result on its own (see tools/registry.py and
agents/router.py).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


class ProviderUnavailable(Exception):
    """Raised when the configured LLM provider cannot serve a request."""


@dataclass
class ChatTurn:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class ToolCallProposal:
    tool: str
    arguments: dict = field(default_factory=dict)


@dataclass
class AttachmentContent:
    """A file the student attached to their message, with its bytes
    already read from storage so a vision-capable provider can embed them
    directly (base64) — a remote LLM API can't fetch a local dev storage
    URL, so the raw bytes have to travel in the request itself."""

    filename: str
    content_type: str
    data: bytes
    url: str


class LLMProvider(ABC):
    #: Short, user-facing name shown in the execution trace (e.g. "Grok",
    #: "Claude", "DeepSeek"). Overridden by each concrete provider.
    display_name: str = "Assistant"

    @abstractmethod
    async def classify_intent(self, message: str, history: list[ChatTurn], domains: list[str]) -> dict:
        """Return a raw dict shaped like IntentResult. The router validates it."""

    @abstractmethod
    async def propose_tool_calls(
        self, *, message: str, intent: str, parameters: dict, available_tools: list[dict], history: list[ChatTurn]
    ) -> list[ToolCallProposal]:
        """Decide which registered tool(s) to call for this turn, with what arguments."""

    @abstractmethod
    def stream_final_answer(
        self,
        *,
        message: str,
        intent: str,
        tool_results: list[dict],
        history: list[ChatTurn],
        attachments: list[AttachmentContent] | None = None,
    ) -> AsyncIterator[str]:
        """Stream the natural-language answer, grounded only in tool_results
        (plus any attachments, for a provider that can actually see them)."""
