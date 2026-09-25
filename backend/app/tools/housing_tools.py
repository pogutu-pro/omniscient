from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.housing import HostelSearchParams
from app.tools.registry import Tool, ToolContext, ToolResult


class GetHostelParams(BaseModel):
    hostel_id: str = Field(min_length=1)


async def _search_hostels(ctx: ToolContext, params: HostelSearchParams) -> ToolResult:
    hostels = await ctx.hostel_repo.search(params)
    if not hostels:
        return ToolResult(ok=True, data=[], summary="No hostels matched those filters.")
    return ToolResult(
        ok=True,
        data=[h.model_dump() for h in hostels],
        summary=f"Found {len(hostels)} matching hostel{'s' if len(hostels) != 1 else ''}.",
    )


async def _get_hostel(ctx: ToolContext, params: GetHostelParams) -> ToolResult:
    hostel = await ctx.hostel_repo.get_by_id(params.hostel_id)
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
