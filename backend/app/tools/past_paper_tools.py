from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.past_paper import PastPaperSearchParams
from app.tools.registry import Tool, ToolContext, ToolResult


class GetPastPaperParams(BaseModel):
    paper_id: str = Field(min_length=1)


async def _search_past_papers(ctx: ToolContext, params: PastPaperSearchParams) -> ToolResult:
    papers = await ctx.past_paper_repo.search(params)
    if not papers:
        return ToolResult(ok=True, data=[], summary="No past papers matched that search.")
    return ToolResult(
        ok=True,
        data=[p.model_dump() for p in papers],
        summary=f"Found {len(papers)} past paper{'s' if len(papers) != 1 else ''}.",
    )


async def _get_past_paper(ctx: ToolContext, params: GetPastPaperParams) -> ToolResult:
    paper = await ctx.past_paper_repo.get_by_id(params.paper_id)
    if not paper:
        return ToolResult(ok=False, error="not_found", summary="That past paper could not be found.")
    return ToolResult(ok=True, data=paper.model_dump(), summary=f"Retrieved {paper.course_code} {paper.academic_year}.")


search_past_papers_tool = Tool(
    name="search_past_papers",
    description="Search past examination papers by unit/course name or code, programme, or academic year.",
    params_model=PastPaperSearchParams,
    handler=_search_past_papers,
)

get_past_paper_tool = Tool(
    name="get_past_paper",
    description="Fetch details and a download link for a single past paper by id.",
    params_model=GetPastPaperParams,
    handler=_get_past_paper,
)
