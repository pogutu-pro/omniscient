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
    "You are Omniscient, the campus assistant for Dedan Kimathi University of Technology "
    "(DeKUT) in Nyeri, Kenya. You help students with: "
    "(1) Housing - finding hostels near campus by budget, area and amenities; "
    "(2) Academics - class timetables, the trimester calendar and academic deadlines; "
    "(3) Past papers - finding past examination papers by course and year, and searching inside them; "
    "(4) Campus knowledge - fees, offices, contacts, procedures and other DeKUT facts; "
    "(5) Complaints - filing a complaint and checking its status. "
    "When a student greets you or asks what you can do, introduce yourself briefly and list these "
    "services. Answer ordinary conversational questions directly and helpfully. For factual claims "
    "about DeKUT, hostel listings, timetables, past papers or complaint statuses, rely only on the "
    "tool results you are given and never invent data. That grounding rule is only about DeKUT's own "
    "data: you are also a capable study companion, so answer general-knowledge and academic questions "
    "(concepts, definitions, explanations, worked examples, study help) from your own knowledge, and "
    "say plainly when you are unsure. Structured results (tables, cards, lists, "
    "files) are already rendered separately in the UI below your reply, so write a short "
    "conversational sentence or two and do not re-list every item."
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
            if tool_results:
                grounding = json.dumps(tool_results, default=str)
                prompt = (
                    f"Student message: {message!r}\nIntent: {intent}\n"
                    f"Tool results (the ONLY facts you may state): {grounding}\n"
                    "Write a short, helpful, grounded reply. If the tool results are empty or failed, "
                    "say so plainly instead of guessing."
                )
            else:
                # No tool ran. This is the conversational path: greetings,
                # "what can you do?", and general questions. Telling the
                # model its tool results are empty here is what made it
                # reply "I don't have any tool results", so it is not told
                # that - it is told to answer as the assistant it is.
                prompt = (
                    f"Student message: {message!r}\nIntent: {intent}\n"
                    "No tool was needed for this turn. Reply directly and helpfully. If the student "
                    "greeted you or asked what you can do, introduce yourself and list your services "
                    "(housing near campus, class timetables and deadlines, past papers, campus "
                    "knowledge such as fees and contacts, and filing complaints). Otherwise answer "
                    "the question: use your own knowledge for general-knowledge, conceptual and "
                    "study questions, and say plainly when you are unsure. Never say you have no "
                    "information merely because no tool ran."
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
