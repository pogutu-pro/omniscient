"""A single provider implementation for every OpenAI-compatible Chat
Completions API: OpenAI itself, xAI's Grok, DeepSeek, and any other
provider ("custom") that speaks the same wire format. Only `base_url`,
`api_key`, `model`, and a `display_name` differ between them — see
`factory.py` for how each named provider is constructed from config.

This is what makes "connect five providers, Grok primary, add more later"
a configuration change rather than five separate integrations: adding a
sixth OpenAI-compatible provider (Groq, Together, Mistral, ...) needs no
new code, just another entry in `PROVIDER_BASE_URLS` or `LLM_PROVIDER=custom`
with `LLM_API_BASE` pointed at it.
"""
from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator

from app.agents.providers.base import AttachmentContent, ChatTurn, LLMProvider, ProviderUnavailable, ToolCallProposal

_INTENT_FUNCTION = {
    "name": "classify_intent",
    "description": "Classify a DeKUT student's message into a support domain and extract structured parameters.",
    "parameters": {
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


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, *, api_key: str, model: str, base_url: str, display_name: str, temperature: float = 0.2):
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover
            raise ProviderUnavailable("The 'openai' package is not installed") from exc
        if not api_key:
            raise ProviderUnavailable(f"No API key configured for the {display_name} provider")
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._temperature = temperature
        self.display_name = display_name

    def _history_messages(self, history: list[ChatTurn]) -> list[dict]:
        return [{"role": t.role, "content": t.content} for t in history[-10:]]

    async def classify_intent(self, message: str, history: list[ChatTurn], domains: list[str]) -> dict:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                messages=[
                    {"role": "system", "content": _SAFE_SYSTEM_PROMPT},
                    *self._history_messages(history),
                    {"role": "user", "content": message},
                ],
                tools=[{"type": "function", "function": _INTENT_FUNCTION}],
                tool_choice={"type": "function", "function": {"name": "classify_intent"}},
            )
        except Exception as exc:
            raise ProviderUnavailable(f"{self.display_name} classify_intent call failed: {exc}") from exc

        tool_calls = response.choices[0].message.tool_calls
        if not tool_calls:
            raise ProviderUnavailable(f"{self.display_name} did not return a classify_intent tool call")
        try:
            return json.loads(tool_calls[0].function.arguments)
        except (json.JSONDecodeError, IndexError) as exc:
            raise ProviderUnavailable(f"{self.display_name} returned malformed classify_intent arguments") from exc

    async def propose_tool_calls(
        self, *, message: str, intent: str, parameters: dict, available_tools: list[dict], history: list[ChatTurn]
    ) -> list[ToolCallProposal]:
        if not available_tools:
            return []
        functions = [
            {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
            for t in available_tools
        ]
        prompt = (
            f"The message was classified as intent='{intent}' with extracted parameters "
            f"{json.dumps(parameters)}. Call the single most appropriate tool with well-formed "
            f"arguments to satisfy the student's request: {message!r}"
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                messages=[
                    {"role": "system", "content": _SAFE_SYSTEM_PROMPT},
                    *self._history_messages(history),
                    {"role": "user", "content": prompt},
                ],
                tools=functions,
            )
        except Exception as exc:
            raise ProviderUnavailable(f"{self.display_name} propose_tool_calls call failed: {exc}") from exc

        tool_calls = response.choices[0].message.tool_calls or []
        proposals = []
        for call in tool_calls:
            try:
                arguments = json.loads(call.function.arguments)
            except json.JSONDecodeError:
                continue
            proposals.append(ToolCallProposal(tool=call.function.name, arguments=arguments))
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
                    b64 = base64.b64encode(attachment.data).decode("ascii")
                    content.append(
                        {"type": "image_url", "image_url": {"url": f"data:{attachment.content_type};base64,{b64}"}}
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
            stream = await self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                messages=[
                    {"role": "system", "content": _SAFE_SYSTEM_PROMPT},
                    *self._history_messages(history),
                    user_message,
                ],
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
        except Exception as exc:
            raise ProviderUnavailable(f"{self.display_name} stream_final_answer call failed: {exc}") from exc
