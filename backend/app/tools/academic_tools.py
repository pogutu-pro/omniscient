from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.academics import TimetableQuery
from app.tools.registry import Tool, ToolContext, ToolResult


class ListDeadlinesParams(BaseModel):
    programme_code: str | None = Field(default=None, max_length=20)
    limit: int = Field(default=5, ge=1, le=20)


class AcademicCalendarParams(BaseModel):
    academic_year: str | None = Field(
        default=None,
        max_length=9,
        description="Academic year such as '2026/2027'. Defaults to the current year.",
    )


async def _get_academic_calendar(ctx: ToolContext, params: AcademicCalendarParams) -> ToolResult:
    """Which trimester it is, and when the terms run.

    DeKUT's year has three trimesters, not two, and the assistant cannot be
    expected to know which one is running. This is also the only honest way to
    answer a date question, because the real reporting and resumption dates
    are announced per programme and move: the rows say whether they are
    confirmed or still the published plan, and the tool result repeats that
    so the answer does not present a provisional date as fact.
    """
    current = await ctx.academic_repo.get_current_term()
    academic_year = params.academic_year or current.academic_year
    terms = await ctx.academic_repo.list_terms(academic_year)
    if not terms:
        terms = [current]
    unconfirmed = [t for t in terms if t.provisional]
    caveat = (
        " Dates are the published plan and may still move - confirm with the registrar."
        if unconfirmed
        else ""
    )
    return ToolResult(
        ok=True,
        data={
            "current_academic_year": current.academic_year,
            "current_trimester": current.trimester,
            "current_term": current.model_dump(mode="json"),
            "terms": [term.model_dump(mode="json") for term in terms],
            "structure": (
                "DeKUT runs a trimester system: the academic year opens in September and is divided into "
                "three trimesters of about four months each - Semester 1 (January-April), "
                "Semester 2 (May-August) and Semester 3 (September-December)."
            ),
            "dates_confirmed": not unconfirmed,
        },
        summary=(
            f"Academic year {academic_year} runs as three trimesters; today falls in Semester "
            f"{current.trimester}.{caveat}"
        ),
    )


async def _get_timetable(ctx: ToolContext, params: TimetableQuery) -> ToolResult:
    entries = await ctx.academic_repo.get_timetable(params)
    if not entries:
        return ToolResult(ok=True, data=[], summary="No timetable entries matched that query.")
    # Naming the scope in the summary means the model can say "your year 2
    # classes" without inventing it, and a student who asked about the wrong
    # term sees immediately that the answer covered a different one.
    scope = ", ".join(
        f"{label}={value}"
        for label, value in (
            ("term", params.academic_year),
            ("year group", params.year_group),
            ("class", params.stream),
            ("day", params.day_of_week),
        )
        if value is not None
    )
    suffix = f" for {scope}." if scope else "."
    return ToolResult(
        ok=True,
        data=[e.model_dump(mode="json") for e in entries],
        summary=f"Found {len(entries)} timetable entr{'y' if len(entries) == 1 else 'ies'}{suffix}",
    )


async def _list_deadlines(ctx: ToolContext, params: ListDeadlinesParams) -> ToolResult:
    deadlines = await ctx.academic_repo.list_deadlines(params.programme_code, params.limit)
    if not deadlines:
        return ToolResult(ok=True, data=[], summary="No upcoming deadlines found.")
    return ToolResult(
        ok=True,
        data=[d.model_dump(mode="json") for d in deadlines],
        summary=f"Found {len(deadlines)} upcoming deadline{'s' if len(deadlines) != 1 else ''}.",
    )


get_academic_calendar_tool = Tool(
    name="get_academic_calendar",
    description=(
        "Get DeKUT's trimester calendar: which semester is running now, and the start/end/reporting dates "
        "of each trimester in an academic year. Use this for any question about semesters, trimesters, term "
        "dates, reporting or resumption, or when a student refers to 'semester 3' or the September-December "
        "term. The dates are per programme and can change, so quote the tool's confirmation flag rather than "
        "asserting a date as final."
    ),
    params_model=AcademicCalendarParams,
    handler=_get_academic_calendar,
)

get_timetable_tool = Tool(
    name="get_timetable",
    description=(
        "Look up the class timetable, optionally filtered by academic year/term, year group "
        "(e.g. '2.1' or '1.1'), class or stream (e.g. 'CS' or 'FS'), programme, course or day of week. "
        "Always pass year_group when the student names their year or course of study, so the answer "
        "is not the whole programme's grid."
    ),
    params_model=TimetableQuery,
    handler=_get_timetable,
)

list_deadlines_tool = Tool(
    name="list_academic_deadlines",
    description="List upcoming academic deadlines (registration, fees, exams) for a programme.",
    params_model=ListDeadlinesParams,
    handler=_list_deadlines,
)
