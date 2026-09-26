"""The typed tool registry.

Every capability the agent can invoke is registered here as a `Tool`:
a name, a human description (shown to the LLM so it can decide when to
use it), a Pydantic input model (validated before the handler ever runs),
and an async handler that contains the actual, deterministic business
logic. Handlers depend on repository *interfaces*, never on the LLM, and
never touch a database or the filesystem directly outside a repository.

Tools are independent of the LLM: every one of them can be constructed and
called directly in a unit test with no model in the loop at all.

Authorization is enforced by the tool itself via `ToolContext.student_id`
— the model saying "the user is authenticated" or "the user is an admin"
is never sufficient on its own. A tool that needs a student must check
`ctx.require_student()` before doing anything.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from app.repositories.academic_repository import AcademicRepository
from app.repositories.complaint_repository import ComplaintRepository
from app.repositories.hostel_repository import HostelRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.past_paper_repository import PastPaperRepository
from app.services.paper_search_service import PaperSearchService


class ToolAuthorizationError(Exception):
    """Raised when a tool is invoked without the access it requires."""


@dataclass
class ToolContext:
    """Everything a tool handler is allowed to touch.

    Deliberately narrow: repositories (never raw DB sessions) plus the
    caller's authenticated student id, if any. No settings, no LLM client.

    `paper_search` is optional and defaults to None so that a context
    built without retrieval still works — the RAG tool checks for it and
    reports "not available" rather than the whole agent failing to start.
    """

    hostel_repo: HostelRepository
    academic_repo: AcademicRepository
    past_paper_repo: PastPaperRepository
    complaint_repo: ComplaintRepository
    student_id: str | None = None
    paper_search: PaperSearchService | None = None
    # The DeKUT campus knowledge base (fees, offices, contacts, procedures).
    # Optional so a context built without it still works; the knowledge tool
    # reports "not loaded" rather than the agent failing to answer.
    knowledge_repo: KnowledgeRepository | None = None

    def require_student(self) -> str:
        if not self.student_id:
            raise ToolAuthorizationError("This action requires an authenticated student.")
        return self.student_id


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    summary: str = ""
    error: str | None = None


ToolHandler = Callable[[ToolContext, BaseModel], Awaitable[ToolResult]]


@dataclass
class Tool:
    name: str
    description: str
    params_model: type[BaseModel]
    handler: ToolHandler
    requires_auth: bool = False

    def input_schema(self) -> dict:
        return self.params_model.model_json_schema()


@dataclass
class ToolRegistry:
    _tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def describe_for_llm(self) -> list[dict]:
        """Compact, provider-agnostic tool descriptions for prompting."""
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema()}
            for t in self._tools.values()
        ]

    async def call(self, name: str, raw_params: dict, ctx: ToolContext) -> ToolResult:
        tool = self.get(name)
        if not tool:
            return ToolResult(ok=False, error=f"Unknown tool: {name}", summary=f"Tool '{name}' does not exist.")
        try:
            params = tool.params_model.model_validate(raw_params)
        except Exception as exc:  # pydantic ValidationError, kept generic on purpose
            return ToolResult(ok=False, error=str(exc), summary="Invalid input for this tool.")
        if tool.requires_auth and not ctx.student_id:
            return ToolResult(
                ok=False, error="unauthorized", summary="This action requires you to be signed in."
            )
        try:
            return await tool.handler(ctx, params)
        except ToolAuthorizationError as exc:
            return ToolResult(ok=False, error=str(exc), summary=str(exc))
        except Exception as exc:  # last line of defence: never crash the trace on tool failure
            return ToolResult(ok=False, error=str(exc), summary="That action failed unexpectedly.")
