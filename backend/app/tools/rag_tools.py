"""Semantic search over the text inside past papers.

The companion to `search_past_papers`, which only matches on metadata
(course code, programme, year). This one embeds the student's question and
retrieves the passages that actually discuss it, which is what answers
"how did question 3b go" or "show me an example of a B-tree insertion"
when no course code is known.

It never fails the turn: if retrieval is off, the model is unbuilt, or the
embedding backend is down, the tool reports that plainly and the
orchestrator carries on with the tools that do work.
"""
from __future__ import annotations

from app.schemas.rag import SearchPaperContentParams
from app.services.paper_search_service import format_for_llm
from app.tools.registry import Tool, ToolContext, ToolResult


async def _search_paper_content(ctx: ToolContext, params: SearchPaperContentParams) -> ToolResult:
    if ctx.paper_search is None or not ctx.paper_search.is_live:
        return ToolResult(
            ok=True,
            data={"available": False, "note": "Past-paper text search is not enabled on this deployment.", "excerpts": []},
            summary="Past-paper text search is not available here.",
        )

    result = await ctx.paper_search.search(params.query, top_k=params.top_k)
    payload = format_for_llm(result)

    if not result.available:
        return ToolResult(ok=True, data=payload, summary=payload.get("note") or "Search is unavailable right now.")
    if result.is_empty():
        return ToolResult(ok=True, data=payload, summary="No past paper covers that.")

    return ToolResult(
        ok=True,
        data=payload,
        summary=(
            f"Found {len(result.matches)} relevant excerpt"
            f"{'s' if len(result.matches) != 1 else ''} in past papers."
        ),
    )


search_paper_content_tool = Tool(
    name="search_past_paper_content",
    description=(
        "Search inside the full text of past examination papers using meaning rather than keywords. "
        "Use this when a student asks about specific question content, a topic covered in an exam, or "
        "wants to see how something was answered - not when they are looking for a paper by course "
        "code or year, which 'search_past_papers' handles."
    ),
    params_model=SearchPaperContentParams,
    handler=_search_paper_content,
)
