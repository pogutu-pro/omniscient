from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.academics import TimetableQuery
from app.tools.registry import Tool, ToolContext, ToolResult


class ListDeadlinesParams(BaseModel):
    programme_code: str | None = Field(default=None, max_length=20)
    limit: int = Field(default=5, ge=1, le=20)


async def _get_timetable(ctx: ToolContext, params: TimetableQuery) -> ToolResult:
    entries = await ctx.academic_repo.get_timetable(params)
    if not entries:
        return ToolResult(ok=True, data=[], summary="No timetable entries matched that query.")
    return ToolResult(
        ok=True,
        data=[e.model_dump() for e in entries],
        summary=f"Found {len(entries)} timetable entr{'y' if len(entries) == 1 else 'ies'}.",
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


get_timetable_tool = Tool(
    name="get_timetable",
    description="Look up a student's class timetable, optionally filtered by programme, year, or day of week.",
    params_model=TimetableQuery,
    handler=_get_timetable,
)

list_deadlines_tool = Tool(
    name="list_academic_deadlines",
    description="List upcoming academic deadlines (registration, fees, exams) for a programme.",
    params_model=ListDeadlinesParams,
    handler=_list_deadlines,
)
