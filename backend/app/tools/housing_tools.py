from __future__ import annotations

from pydantic import BaseModel, Field

from app.repositories.hostel_repository import RumiaUnavailable
from app.schemas.housing import HostelSearchParams
from app.tools.registry import Tool, ToolContext, ToolResult


class GetHostelParams(BaseModel):
    hostel_id: str = Field(min_length=1)


# A listing source that is down must never be reported as "no hostels
# matched" - to a student that reads as "there is nowhere to live near
# campus", which is both alarming and false. It is surfaced as a failed
# step with the real reason instead.
_RUMIA_DOWN_SUMMARY = "I couldn't reach Rumia's housing listings right now, so I can't confirm what's available. Please try again in a moment."


async def _search_hostels(ctx: ToolContext, params: HostelSearchParams) -> ToolResult:
    try:
        hostels = await ctx.hostel_repo.search(params)
    except RumiaUnavailable:
        return ToolResult(ok=False, error="source_unavailable", summary=_RUMIA_DOWN_SUMMARY)
    if not hostels:
        return ToolResult(ok=True, data=[], summary="No hostels matched those filters.")
    return ToolResult(
        ok=True,
        data=[h.model_dump() for h in hostels],
        summary=f"Found {len(hostels)} matching hostel{'s' if len(hostels) != 1 else ''}.",
    )


async def _get_hostel(ctx: ToolContext, params: GetHostelParams) -> ToolResult:
    try:
        hostel = await ctx.hostel_repo.get_by_id(params.hostel_id)
    except RumiaUnavailable:
        return ToolResult(ok=False, error="source_unavailable", summary=_RUMIA_DOWN_SUMMARY)
    if not hostel:
        return ToolResult(ok=False, error="not_found", summary="That hostel listing could not be found.")
    return ToolResult(ok=True, data=hostel.model_dump(), summary=f"Retrieved details for {hostel.name}.")


search_hostels_tool = Tool(
    name="search_hostels",
    description=(
        "Search verified and demo hostel/housing listings near DeKUT by budget, area, "
        "distance from campus, amenities, and verification status."
    ),
    params_model=HostelSearchParams,
    handler=_search_hostels,
)

get_hostel_tool = Tool(
    name="get_hostel",
    description="Fetch full details for a single hostel listing by id.",
    params_model=GetHostelParams,
    handler=_get_hostel,
)
