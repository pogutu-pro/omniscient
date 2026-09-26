"""Semantic-ish lookup over the DeKUT campus knowledge dataset.

The OMNISCIENT dataset holds atomic campus facts (offices, contacts, fees,
procedures, rules) and is searched by token overlap, not embeddings — see
`services/knowledge_search.py` for why. This tool is the single way the chat
agent can reach it, which is what turns "I don't know" into a real answer
about how DeKUT works.

It never fails the turn: if the dataset was never ingested, or nothing
matches, the result says so plainly and the orchestrator keeps going.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.knowledge_search import format_for_llm, search_knowledge
from app.tools.registry import Tool, ToolContext, ToolResult


class SearchCampusKnowledgeParams(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=500,
        description="The student's question in their own words, e.g. 'how do I pay fees'.",
    )


async def _search_campus_knowledge(ctx: ToolContext, params: SearchCampusKnowledgeParams) -> ToolResult:
    if ctx.knowledge_repo is None:
        return ToolResult(
            ok=True,
            data={"available": False, "matched": False, "context": ""},
            summary="Campus knowledge is not available on this deployment.",
        )

    answer = await search_knowledge(ctx.knowledge_repo, params.query)
    context = format_for_llm(answer)

    if not answer.available:
        return ToolResult(
            ok=True,
            data={"available": False, "matched": False, "context": context},
            summary="The campus knowledge dataset is not loaded.",
        )
    if answer.is_empty:
        return ToolResult(
            ok=True,
            data={"available": True, "matched": False, "context": context},
            summary="Nothing in the campus dataset matched that question.",
        )

    return ToolResult(
        ok=True,
        data={
            "available": True,
            "matched": True,
            "context": context,
            "facts": [fact.as_dict() for fact in answer.facts],
        },
        summary=f"Found {len(answer.facts)} campus fact(s).",
    )


search_campus_knowledge_tool = Tool(
    name="search_campus_knowledge",
    description=(
        "Look up factual information about DeKUT from the campus dataset: offices and contacts "
        "(deans, chairpersons, phone numbers, emails), fees and payment procedures, registration, "
        "examination rules and other campus facts. Use this for questions about how DeKUT works or "
        "who to contact - not for hostels, timetables, past papers or complaints, which have their "
        "own tools."
    ),
    params_model=SearchCampusKnowledgeParams,
    handler=_search_campus_knowledge,
)
