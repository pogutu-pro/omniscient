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

# Localities a DeKUT student might name. This is the offline provider's
# stand-in for what a real model would infer, and it previously listed only
# the seeded demo areas, so naming a real area ("Kahawa Ridge", "Nyeri View")
# extracted nothing and was silently replaced by a remembered area - asking
# about one part of Nyeri and getting another back. Kept as an explicit list
# because the real provider does this from the message itself.
KNOWN_AREAS = [
    # Real DeKUT localities, as they appear in housing listings.
    "Boma",
    "Kahawa Ridge",
    "Nyeri View",
    "Nyaribo",
    "Near Gate A",
    "Near Gate B",
    "Embassy Area",
    "King'ong'o",
    "Hill court",
    "Town",
    # Seeded demo areas, so mock-mode data still resolves.
    "Ruring'u",
    "Kamakwa",
    "Mawingo",
    "Outspan",
    "Karatina Road",
    "Majengo",
]

_HOUSING_KEYWORDS = [
    "hostel",
    "hostels",
    "rent",
    "accommodation",
    "room",
    "rooms",
    "house",
    "lodging",
    "bedsitter",
    "where to live",
    "somewhere to stay",
    "vacancy",
    "vacancies",
    "space",
]
# A follow-up that only names a place ("what about Kahawa Ridge?") carries no
# domain keyword at all. These are the shapes such a message takes, so the
# housing domain can still be recognised from the message rather than only
# from the conversation so far.
_FOLLOW_UP_HOUSING_PATTERNS = [
    r"^what about\b",
    r"^how about\b",
    r"^and\b",
    r"^any (?:in|at|around|near)\b",
    r"^in [a-z']",
    r"^around [a-z']",
    r"^near [a-z']",
]
_ACADEMIC_KEYWORDS = [
    "class",
    "classes",
    "timetable",
    "lecture",
    "lectures",
    "schedule",
    "unit",
    "deadline",
    "exam date",
    "year group",
    "semester",
    "trimester",
    "reporting",
    "resumption",
    "term dates",
]

# A question about the shape of the year rather than about a timetable. The
# offline provider has no model to reason with, so it recognises the phrasing
# directly instead of inferring it from an intent.
_CALENDAR_PATTERN = re.compile(
    r"\b(semester|trimester|term)\b[^?]*\b(dates?|start|ends?|running|current|when|calendar|reporting|resumption|long|length)\b"
    r"|\bwhich\s+(semester|trimester|term)\b"
    r"|\bwhat\s+(semester|trimester)\b"
    r"|\breporting\s+date\b"
    r"|\bresumption\b",
)
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
    # Longest first, so "Near Gate A" wins over any shorter overlapping
    # name, and so "Hill court" is not cut short by "hill".
    for area in sorted(KNOWN_AREAS, key=len, reverse=True):
        if area.lower() in lower:
            return area
    return None


def _names_a_known_area(message: str) -> bool:
    return _extract_area(message) is not None


def _looks_like_a_follow_up(message: str) -> bool:
    """True for the shapes a contextual follow-up takes: "what about X?",
    "any in Y?", "and Z". These carry no domain keyword of their own."""
    lowered = message.strip().lower()
    if not lowered:
        return False
    return any(re.search(pattern, lowered) for pattern in _FOLLOW_UP_HOUSING_PATTERNS)


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

# The department calls a cohort a "year group" and writes it "2.1" or
# "Year 2.2", and calls the two first-year classes CS/FS. Both spellings are
# matched here so a student asking either way gets their own grid.
_YEAR_GROUP_PATTERN = re.compile(r"\b(?:year\s*)?([1-9])[\.\s]?([1-3])\b", re.IGNORECASE)
_STREAM_PATTERN = re.compile(r"\b(CS|FS|BIT|BEE|BCE)\b")


def _extract_cohort(message: str) -> tuple[str | None, str | None]:
    """The year group and class a student asked about, if they named one.

    Returns `(year_group, stream)`. Deliberately returns `None` rather than a
    default: the timetable is the whole programme until the student says
    otherwise, and guessing a cohort would quietly answer the wrong one.
    """
    lower = message.lower()
    year_group = None
    match = _YEAR_GROUP_PATTERN.search(lower)
    if match and int(match.group(1)) <= 4:
        year_group = f"{match.group(1)}.{match.group(2)}"
    stream_match = _STREAM_PATTERN.search(lower)
    stream = stream_match.group(1).upper() if stream_match else None
    return year_group, stream


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

    @staticmethod
    def _last_assistant_turn_was_about(history: list[ChatTurn], subject: str) -> bool:
        """Whether the assistant's most recent reply was about `subject`.

        Used only to rescue a follow-up that names no domain keyword. A real
        provider gets this from the conversation itself; the offline one has
        to look for it.
        """
        for turn in reversed(history):
            if turn.role == "assistant":
                return subject in turn.content.lower()
        return False

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
            # A follow-up that names a place but no domain ("what about Kahawa
            # Ridge?") is still a housing question - a student asking that is
            # continuing the conversation, not starting an unrelated one.
            # Inferring it from the message plus the recent turn is what keeps
            # a follow-up from being answered with "what would you like to
            # do?", which is the opposite of continuing.
            if _looks_like_a_follow_up(message) and _names_a_known_area(message):
                scores["housing"] = 0.6
                best_domain, best_score = "housing", 0.6
            elif _looks_like_a_follow_up(message) and self._last_assistant_turn_was_about(history, "hostel"):
                scores["housing"] = 0.5
                best_domain, best_score = "housing", 0.5

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
            year_group, stream = _extract_cohort(message)
            if year_group is not None:
                parameters["year_group"] = year_group
            if stream is not None:
                parameters["stream"] = stream
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
            if _CALENDAR_PATTERN.search(message.lower()):
                return [ToolCallProposal(tool="get_academic_calendar", arguments={})]
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

    if tool_name == "get_academic_calendar":
        if not isinstance(data, dict):
            return "I couldn't read the academic calendar just now."
        terms = data.get("terms") or []
        running = data.get("current_trimester")
        period = ""
        for term in terms:
            if term.get("trimester") == running:
                period = (
                    f" {term.get('start_date','')} to {term.get('end_date','')}".strip()
                )
                break
        caveat = (
            " Those dates are the published plan — confirm with your registrar, since reporting and "
            "resumption dates are set per programme and can move."
            if not data.get("dates_confirmed", True)
            else ""
        )
        return (
            f"DeKUT runs three trimesters a year, and right now it is Semester {running} of "
            f"{data.get('current_academic_year', 'this year')}, running{period or ' now'}.{caveat} "
            "Semester 1 is January-April, Semester 2 May-August and Semester 3 September-December."
        )

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
