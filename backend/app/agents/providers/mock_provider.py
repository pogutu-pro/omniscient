"""Deterministic, offline provider.

Implements the same interface a real model would, using keyword rules and
regexes tuned for the kinds of messages DeKUT students actually send. It
exists so the full product — router, tools, streaming trace, personalization
— is demonstrable and testable without any external API key, per the
brief's requirement that Omniscient work completely without Rumia *or* a
live LLM credential.
"""
from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator

from app.agents.providers.base import AttachmentContent, ChatTurn, LLMProvider, ToolCallProposal

KNOWN_AREAS = ["Boma", "Ruring'u", "Kamakwa", "Mawingo", "Outspan", "Karatina Road", "Majengo"]

_HOUSING_KEYWORDS = ["hostel", "hostels", "rent", "accommodation", "room", "house", "lodging", "bedsitter"]
_ACADEMIC_KEYWORDS = ["class", "classes", "timetable", "lecture", "schedule", "unit", "deadline", "exam date"]
_PAST_PAPER_KEYWORDS = ["past paper", "past papers", "cat", "revision", "exam paper", "question paper"]
_COMPLAINT_KEYWORDS = ["complaint", "broken", "report", "issue", "leak", "tap", "wifi", "power", "fault", "not working"]

_DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_COMPLAINT_CATEGORY_KEYWORDS = {
    "maintenance": ["tap", "leak", "plumbing", "water", "door", "window", "broken"],
    "security": ["security", "theft", "stolen", "break-in", "unsafe"],
    "utilities": ["wifi", "internet", "power", "electricity", "lights"],
    "academic": ["lecturer", "grade", "marks", "unit registration"],
    "hostel": ["hostel", "room", "roommate"],
}


def _score(message: str, keywords: list[str]) -> float:
    lower = message.lower()
    hits = sum(1 for k in keywords if k in lower)
    return min(1.0, 0.35 + 0.25 * hits) if hits else 0.0


def _extract_budget(message: str) -> int | None:
    match = re.search(r"(?:under|below|less than|ksh\.?\s*)\s*([\d,]{3,7})", message.lower())
    if not match:
        match = re.search(r"([\d,]{3,7})\s*(?:ksh|kes|shillings|bob)", message.lower())
    if match:
        try:
            return int(match.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def _extract_area(message: str) -> str | None:
    lower = message.lower()
    for area in KNOWN_AREAS:
        if area.lower() in lower:
            return area
    return None


def _extract_distance(message: str) -> float | None:
    match = re.search(r"([\d.]+)\s*km", message.lower())
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _extract_day(message: str) -> int | None:
    lower = message.lower()
    if "tomorrow" in lower:
        return None  # resolved by the caller against the current date if needed
    for idx, name in enumerate(_DAY_NAMES):
        if name in lower:
            return idx
    return None


def _extract_complaint_category(message: str) -> str:
    lower = message.lower()
    for category, keywords in _COMPLAINT_CATEGORY_KEYWORDS.items():
        if any(k in lower for k in keywords):
            return category
    return "other"


# Domain keywords plus generic request filler - stripped out so a natural
# request like "Find Database Systems past papers" searches on "database
# systems" (which actually matches a course name/code) rather than the
# whole sentence (which matches nothing).
_PAST_PAPER_FILLER = [*_PAST_PAPER_KEYWORDS, "find", "search for", "search", "show me", "get me", "for", "please"]


def _extract_past_paper_query(message: str) -> str:
    lower = message.lower()
    for phrase in sorted(_PAST_PAPER_FILLER, key=len, reverse=True):
        lower = lower.replace(phrase, " ")
    cleaned = re.sub(r"\s+", " ", lower).strip()
    return cleaned or message


class MockProvider(LLMProvider):
    display_name = "Mock Assistant"

    async def classify_intent(self, message: str, history: list[ChatTurn], domains: list[str]) -> dict:
        scores = {
            "housing": _score(message, _HOUSING_KEYWORDS),
            "academics": _score(message, _ACADEMIC_KEYWORDS),
            "past_papers": _score(message, _PAST_PAPER_KEYWORDS),
            "complaints": _score(message, _COMPLAINT_KEYWORDS),
        }
        best_domain = max(scores, key=lambda k: scores[k])
        best_score = scores[best_domain]
        if best_score == 0.0:
            return {"intent": "general", "confidence": 0.9, "parameters": {}}

        parameters: dict = {}
        if best_domain == "housing":
            budget = _extract_budget(message)
            area = _extract_area(message)
            distance = _extract_distance(message)
            if budget is not None:
                parameters["max_budget_ksh"] = budget
            if area is not None:
                parameters["area"] = area
            if distance is not None:
                parameters["max_distance_km"] = distance
        elif best_domain == "academics":
            day = _extract_day(message)
            if day is not None:
                parameters["day_of_week"] = day
        elif best_domain == "past_papers":
            parameters["query"] = _extract_past_paper_query(message)
        elif best_domain == "complaints":
            ref_match = re.search(r"OMN-[A-F0-9]{6}", message.upper())
            if ref_match:
                parameters["reference_code"] = ref_match.group(0)
                parameters["_is_status_check"] = True
            else:
                parameters["category"] = _extract_complaint_category(message)
                parameters["details"] = message

        return {"intent": best_domain, "confidence": round(best_score, 2), "parameters": parameters}

    async def propose_tool_calls(
        self, *, message: str, intent: str, parameters: dict, available_tools: list[dict], history: list[ChatTurn]
    ) -> list[ToolCallProposal]:
        if intent == "housing":
            args = {k: v for k, v in parameters.items() if not k.startswith("_")}
            return [ToolCallProposal(tool="search_hostels", arguments=args)]
        if intent == "academics":
            args = {k: v for k, v in parameters.items() if not k.startswith("_")}
            return [ToolCallProposal(tool="get_timetable", arguments=args)]
        if intent == "past_papers":
            args = {k: v for k, v in parameters.items() if not k.startswith("_")}
            return [ToolCallProposal(tool="search_past_papers", arguments=args)]
        if intent == "complaints":
            if parameters.get("_is_status_check"):
                return [ToolCallProposal(tool="get_complaint_status", arguments={"reference_code": parameters["reference_code"]})]
            return [
                ToolCallProposal(
                    tool="file_complaint",
                    arguments={
                        "category": parameters.get("category", "other"),
                        "details": parameters.get("details", message),
                        "location": parameters.get("location", ""),
                    },
                )
            ]
        return []

    async def stream_final_answer(
        self,
        *,
        message: str,
        intent: str,
        tool_results: list[dict],
        history: list[ChatTurn],
        attachments: list[AttachmentContent] | None = None,
    ) -> AsyncIterator[str]:
        text = _compose_attachment_reply(attachments) if attachments else _compose_answer(intent, tool_results)
        for chunk in _chunk_words(text):
            await asyncio.sleep(0)
            yield chunk


def _compose_attachment_reply(attachments: list[AttachmentContent]) -> str:
    # Deliberately honest rather than fabricating a plausible-sounding
    # description: the mock provider has no model behind it, so it cannot
    # actually see pixels. A real vision-capable provider (see
    # AnthropicProvider/OpenAICompatibleProvider) receives the same
    # attachment as real image bytes and can describe it for real.
    images = [a for a in attachments if a.content_type.startswith("image/")]
    others = [a for a in attachments if not a.content_type.startswith("image/")]
    parts = []
    if images:
        names = ", ".join(a.filename for a in images)
        parts.append(
            f"I can see you've attached {'an image' if len(images) == 1 else f'{len(images)} images'} ({names}). "
            "Omniscient is running in offline demo mode right now, so I can't actually analyze image content — "
            "connect a real AI provider (Anthropic, OpenAI, Grok, or DeepSeek) via LLM_PROVIDER to enable that."
        )
    if others:
        names = ", ".join(a.filename for a in others)
        parts.append(f"I've also received {names} as an attachment for reference.")
    return " ".join(parts)


def _chunk_words(text: str, words_per_chunk: int = 4) -> list[str]:
    words = text.split(" ")
    chunks = []
    for i in range(0, len(words), words_per_chunk):
        piece = " ".join(words[i : i + words_per_chunk])
        chunks.append(piece + (" " if i + words_per_chunk < len(words) else ""))
    return chunks


def _compose_answer(intent: str, tool_results: list[dict]) -> str:
    if not tool_results:
        return (
            "I can help with housing near DeKUT, your class timetable, past examination "
            "papers, or filing a complaint. What would you like to do?"
        )

    result = tool_results[0]
    tool_name = result.get("tool")
    data = result.get("data")
    ok = result.get("ok", False)

    if not ok:
        return result.get("summary") or "I couldn't complete that request."

    if tool_name == "search_hostels":
        hostels = data or []
        if not hostels:
            return "I couldn't find any hostels matching that budget and area. Try widening your search."
        return f"I found {len(hostels)} hostel option{'s' if len(hostels) != 1 else ''} for you — see the details below."

    if tool_name == "get_timetable":
        entries = data or []
        if not entries:
            return "You have no scheduled classes matching that filter."
        return "Here is your schedule:"

    if tool_name == "search_past_papers":
        papers = data or []
        if not papers:
            return "I couldn't find past papers matching that search. Try the unit code or name."
        return f"I found {len(papers)} past paper{'s' if len(papers) != 1 else ''} — you can download them below."

    if tool_name == "file_complaint":
        return f"Your complaint has been filed. Reference code: {data.get('reference_code')}. You can check its status any time with this code."

    if tool_name == "get_complaint_status":
        return f"Complaint {data.get('reference_code')} is currently: {data.get('status')}."

    return result.get("summary") or "Done."
