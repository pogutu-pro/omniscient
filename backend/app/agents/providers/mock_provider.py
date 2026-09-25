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

from app.agents.providers.base import ChatTurn, LLMProvider, ToolCallProposal

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


class MockProvider(LLMProvider):
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
            parameters["query"] = message
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
        self, *, message: str, intent: str, tool_results: list[dict], history: list[ChatTurn]
    ) -> AsyncIterator[str]:
        text = _compose_answer(intent, tool_results)
        for chunk in _chunk_words(text):
            await asyncio.sleep(0)
            yield chunk


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
            return "I couldn't find any hostels matching that budget and area — try widening your search."
        lines = [f"I found {len(hostels)} hostel option(s) for you:"]
        for h in hostels[:5]:
            verified = "verified" if h["verified"] else "unverified demo listing"
            lines.append(
                f"- {h['name']} in {h['area']}, KSh {h['price_ksh']:,}/month, "
                f"{h['distance_from_campus_km']} km from campus ({verified})."
            )
        return " ".join(lines)

    if tool_name == "get_timetable":
        entries = data or []
        if not entries:
            return "You have no scheduled classes matching that filter."
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        lines = ["Here is your schedule:"]
        for e in entries[:8]:
            lines.append(
                f"- {day_names[e['day_of_week']]} {e['start_time']}-{e['end_time']}: "
                f"{e['course_code']} {e['course_name']} ({e['session_type']}) in {e['venue']}."
            )
        return " ".join(lines)

    if tool_name == "search_past_papers":
        papers = data or []
        if not papers:
            return "I couldn't find past papers matching that search — try the unit code or name."
        lines = [f"I found {len(papers)} past paper(s):"]
        for p in papers[:5]:
            lines.append(f"- {p['course_code']} {p['course_name']}, {p['academic_year']} semester {p['semester']} ({p['exam_type']}).")
        return " ".join(lines)

    if tool_name == "file_complaint":
        return f"Your complaint has been filed. Reference code: {data.get('reference_code')}. You can check its status any time with this code."

    if tool_name == "get_complaint_status":
        return f"Complaint {data.get('reference_code')} is currently: {data.get('status')}."

    return result.get("summary") or "Done."
