"""Real LLM provider backed by the Anthropic Messages API.

Selected when `LLM_PROVIDER=anthropic` and `LLM_API_KEY` is set. Uses
native tool-use so intent classification and tool selection come back as
structured, schema-shaped data rather than free text the router would have
to hope is valid JSON — but the router still validates everything this
class returns before it is trusted (see agents/router.py).
"""
from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator

from app.agents.providers.base import AttachmentContent, ChatTurn, LLMProvider, ProviderUnavailable, ToolCallProposal

_INTENT_TOOL = {
    "name": "classify_intent",
    "description": "Classify a DeKUT student's message into a support domain and extract structured parameters.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["housing", "academics", "past_papers", "complaints", "general"],
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "parameters": {"type": "object"},
        },
        "required": ["intent", "confidence", "parameters"],
    },
}

_SAFE_SYSTEM_PROMPT = (
    "You are Omniscient, a campus assistant for Dedan Kimathi University of Technology (DeKUT) "
    "students in Nyeri, Kenya. You only answer using the tool results you are given — never invent "
    "hostel listings, timetable entries, past papers, or complaint statuses. Be concise and practical. "
    "Structured results (tables, cards, lists, files) are already rendered separately in the UI below "
    "your reply — write a short, conversational sentence or two, and do not re-list every item yourself."
)


class AnthropicProvider(LLMProvider):
    display_name = "Claude (Anthropic)"

    def __init__(self, api_key: str, model: str, temperature: float = 0.2, base_url: str | None = None):
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover
            raise ProviderUnavailable("The 'anthropic' package is not installed") from exc
        if not api_key:
            raise ProviderUnavailable("LLM_API_KEY is not configured for the anthropic provider")
        self._client = AsyncAnthropic(api_key=api_key, base_url=base_url)
        self._model = model
        self._temperature = temperature

    def _history_messages(self, history: list[ChatTurn]) -> list[dict]:
        return [{"role": t.role, "content": t.content} for t in history[-10:]]

    async def classify_intent(self, message: str, history: list[ChatTurn], domains: list[str]) -> dict:
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=512,
                temperature=self._temperature,
                system=_SAFE_SYSTEM_PROMPT,
                messages=[*self._history_messages(history), {"role": "user", "content": message}],
                tools=[_INTENT_TOOL],
                tool_choice={"type": "tool", "name": "classify_intent"},
            )
        except Exception as exc:
            raise ProviderUnavailable(f"Anthropic classify_intent call failed: {exc}") from exc

        for block in response.content:
            if block.type == "tool_use" and block.name == "classify_intent":
                return dict(block.input)
        raise ProviderUnavailable("Anthropic did not return a classify_intent tool call")

    async def propose_tool_calls(
        self, *, message: str, intent: str, parameters: dict, available_tools: list[dict], history: list[ChatTurn]
    ) -> list[ToolCallProposal]:
        if not available_tools:
            return []
        anthropic_tools = [
            {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
            for t in available_tools
        ]
        prompt = (
            f"The message was classified as intent='{intent}' with extracted parameters "
            f"{json.dumps(parameters)}. Call the single most appropriate tool with well-formed "
            f"arguments to satisfy the student's request: {message!r}"
        )
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=512,
                temperature=self._temperature,
                system=_SAFE_SYSTEM_PROMPT,
                messages=[*self._history_messages(history), {"role": "user", "content": prompt}],
                tools=anthropic_tools,
            )
        except Exception as exc:
            raise ProviderUnavailable(f"Anthropic propose_tool_calls call failed: {exc}") from exc

        proposals = []
        for block in response.content:
            if block.type == "tool_use":
                proposals.append(ToolCallProposal(tool=block.name, arguments=dict(block.input)))
        return proposals

    async def stream_final_answer(
        self,
        *,
        message: str,
        intent: str,
        tool_results: list[dict],
        history: list[ChatTurn],
        attachments: list[AttachmentContent] | None = None,
    ) -> AsyncIterator[str]:
        if attachments:
            content: list[dict] = []
            for attachment in attachments:
                if attachment.content_type.startswith("image/"):
                    content.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": attachment.content_type,
                                "data": base64.b64encode(attachment.data).decode("ascii"),
                            },
                        }
                    )
            attachment_names = ", ".join(a.filename for a in attachments)
            content.append(
                {
                    "type": "text",
                    "text": (
                        f"Student message: {message!r}\nAttached file(s): {attachment_names}\n"
                        "Describe/answer based on what you can actually see in the attached image(s). "
                        "If a file isn't an image you can't read its contents — say so plainly rather "
                        "than guessing at what it contains."
                    ),
                }
            )
            user_message: dict = {"role": "user", "content": content}
        else:
            grounding = json.dumps(tool_results, default=str)
            prompt = (
                f"Student message: {message!r}\nIntent: {intent}\n"
                f"Tool results (the ONLY facts you may state): {grounding}\n"
                "Write a short, helpful, grounded reply. If tool results are empty or failed, say so plainly "
                "instead of guessing."
            )
            user_message = {"role": "user", "content": prompt}

        try:
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=1024,
                temperature=self._temperature,
                system=_SAFE_SYSTEM_PROMPT,
                messages=[*self._history_messages(history), user_message],
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as exc:
            raise ProviderUnavailable(f"Anthropic stream_final_answer call failed: {exc}") from exc
