"""The agent execution loop.

Student message -> intent classification -> parameter extraction ->
validation -> tool selection -> tool execution -> results -> optional
additional tool calls -> final answer generation.

This function is the single place that emits the execution-trace events
the frontend renders live. Every event is a short, safe, user-facing
summary (see schemas/chat.py:TraceEventOut) — never chain-of-thought,
prompts, or secrets. The model never touches the database: it only ever
sees tool results that have already gone through a repository and a
typed, validated response.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from app.agents import router
from app.agents.content_blocks import build_blocks_for_tool
from app.agents.providers.base import AttachmentContent, ChatTurn, LLMProvider, ProviderUnavailable, ToolCallProposal
from app.schemas.chat import IntentResult, TraceEventOut
from app.services import personalization_service
from app.tools.registry import ToolContext, ToolRegistry

_DOMAIN_STATUS = {
    "housing": "Checking hostel listings near campus...",
    "academics": "Looking up your academic records...",
    "past_papers": "Searching the past papers archive...",
    "complaints": "Processing your complaint request...",
    "general": "Thinking about how I can help...",
}

_TOOL_RUNNING_MESSAGE = {
    "search_hostels": "Filtering hostels by your budget and area...",
    "get_hostel": "Fetching hostel details...",
    "get_timetable": "Pulling your class timetable...",
    "list_academic_deadlines": "Checking upcoming academic deadlines...",
    "search_past_papers": "Searching past examination papers...",
    "get_past_paper": "Fetching past paper details...",
    "file_complaint": "Filing your complaint...",
    "get_complaint_status": "Looking up your complaint status...",
}


class OrchestratorResult:
    def __init__(self):
        self.final_text: str = ""
        self.intent: str = "general"
        self.preference_updates: dict = {}


async def run(
    *,
    message: str,
    history: list[ChatTurn],
    ctx: ToolContext,
    registry: ToolRegistry,
    provider: LLMProvider,
    remembered_preferences: dict | None = None,
    attachments: list[AttachmentContent] | None = None,
) -> AsyncIterator[TraceEventOut]:
    result = OrchestratorResult()
    remembered_preferences = remembered_preferences or {}

    yield TraceEventOut(
        type="status", message="Reading your message...", data={"provider": provider.display_name}
    )

    if attachments:
        async for event in _run_with_attachments(provider, message, history, attachments):
            yield event
        return

    try:
        intent_result: IntentResult = await router.classify(provider, message, history)
    except ProviderUnavailable as exc:
        yield TraceEventOut(type="error", message="Omniscient is temporarily unable to process that request.")
        yield TraceEventOut(type="done", data={"error": str(exc)})
        return

    result.intent = intent_result.intent
    yield TraceEventOut(
        type="status",
        message=_DOMAIN_STATUS.get(intent_result.intent, "Thinking about how I can help..."),
        data={"intent": intent_result.intent, "confidence": intent_result.confidence},
    )

    parameters = dict(intent_result.parameters)
    if intent_result.intent == "housing":
        budget_resolved, area_resolved = personalization_service.resolve_housing_preferences(
            current_max_budget=parameters.get("max_budget_ksh"),
            current_area=parameters.get("area"),
            remembered=remembered_preferences,
        )
        if budget_resolved.value is not None:
            parameters["max_budget_ksh"] = budget_resolved.value
        if area_resolved.value is not None:
            parameters["area"] = area_resolved.value
        if budget_resolved.source == "remembered_preference" or area_resolved.source == "remembered_preference":
            note = budget_resolved.explanation if budget_resolved.source == "remembered_preference" else area_resolved.explanation
            yield TraceEventOut(type="status", message=note)
        result.preference_updates = personalization_service.preferences_from_housing_search(
            max_budget_ksh=parameters.get("max_budget_ksh"), area=parameters.get("area")
        )

    if intent_result.intent == "general":
        async for chunk in _stream_answer(provider, message, intent_result.intent, [], history):
            yield chunk
        yield TraceEventOut(type="done", data={"intent": "general", "preference_updates": {}})
        return

    tools_for_llm = registry.describe_for_llm()
    try:
        proposals: list[ToolCallProposal] = await provider.propose_tool_calls(
            message=message,
            intent=intent_result.intent,
            parameters=parameters,
            available_tools=tools_for_llm,
            history=history,
        )
    except ProviderUnavailable:
        proposals = []

    if not proposals:
        yield TraceEventOut(type="error", message="I couldn't determine how to help with that. Could you rephrase?")
        yield TraceEventOut(type="done", data={"intent": intent_result.intent, "preference_updates": {}})
        return

    tool_results: list[dict] = []
    for proposal in proposals:
        friendly = _TOOL_RUNNING_MESSAGE.get(proposal.tool, f"Running {proposal.tool}...")
        yield TraceEventOut(type="tool_call", tool=proposal.tool, status="running", message=friendly)

        # Router-validated parameters take precedence over the model's own guesses for overlapping keys.
        merged_arguments = {**proposal.arguments, **{k: v for k, v in parameters.items() if not k.startswith("_")}}
        tool_result = await registry.call(proposal.tool, merged_arguments, ctx)

        tool_results.append({"tool": proposal.tool, "ok": tool_result.ok, "data": tool_result.data, "summary": tool_result.summary})
        yield TraceEventOut(
            type="tool_result",
            tool=proposal.tool,
            status="completed" if tool_result.ok else "failed",
            summary=tool_result.summary,
        )

        for block in build_blocks_for_tool(proposal.tool, tool_result.ok, tool_result.data):
            yield TraceEventOut(type="content_block", tool=proposal.tool, data=block.model_dump(mode="json"))

    async for chunk in _stream_answer(provider, message, intent_result.intent, tool_results, history):
        yield chunk

    yield TraceEventOut(
        type="done",
        data={"intent": intent_result.intent, "preference_updates": result.preference_updates},
    )


async def _run_with_attachments(
    provider: LLMProvider,
    message: str,
    history: list[ChatTurn],
    attachments: list[AttachmentContent],
) -> AsyncIterator[TraceEventOut]:
    """Attachment turns skip domain-tool routing entirely: an uploaded
    image or document isn't a hostel/timetable/paper/complaint query, so
    there is nothing for the router or tool registry to do. The attachment
    itself is already shown on the student's own message bubble (the
    frontend renders `ChatMessage.attachments` there), so it is not echoed
    again here - only the provider's comment on it, with the real image
    bytes for a vision-capable provider, or an honest "I can't see images
    in this mode" for the mock provider (see MockProvider.stream_final_answer).
    """
    has_image = any(a.content_type.startswith("image/") for a in attachments)
    yield TraceEventOut(
        type="status",
        message="Looking at what you attached..." if has_image else "Looking at your attachment...",
    )

    async for chunk in _stream_answer(provider, message, "general", [], history, attachments=attachments):
        yield chunk

    yield TraceEventOut(type="done", data={"intent": "general", "preference_updates": {}})


async def _stream_answer(
    provider: LLMProvider,
    message: str,
    intent: str,
    tool_results: list[dict],
    history: list[ChatTurn],
    attachments: list[AttachmentContent] | None = None,
) -> AsyncIterator[TraceEventOut]:
    try:
        async for piece in provider.stream_final_answer(
            message=message, intent=intent, tool_results=tool_results, history=history, attachments=attachments
        ):
            yield TraceEventOut(type="answer_chunk", message=piece)
    except ProviderUnavailable:
        yield TraceEventOut(type="error", message="Omniscient is temporarily unable to process that request.")
