from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.complaint import ALLOWED_CATEGORIES, ComplaintCreate
from app.tools.registry import Tool, ToolContext, ToolResult


class GetComplaintStatusParams(BaseModel):
    reference_code: str = Field(min_length=3, max_length=20)


async def _file_complaint(ctx: ToolContext, params: ComplaintCreate) -> ToolResult:
    # Authorization is enforced here, not assumed from anything the model said.
    student_id = ctx.require_student()
    if params.category not in ALLOWED_CATEGORIES:
        return ToolResult(
            ok=False,
            error="invalid_category",
            summary=f"'{params.category}' is not a recognised complaint category.",
        )
    complaint = await ctx.complaint_repo.create(student_id, params)
    return ToolResult(
        ok=True,
        data=complaint.model_dump(mode="json"),
        summary=f"Complaint filed. Reference code {complaint.reference_code}.",
    )


async def _get_complaint_status(ctx: ToolContext, params: GetComplaintStatusParams) -> ToolResult:
    complaint = await ctx.complaint_repo.get_by_reference(params.reference_code)
    if not complaint:
        return ToolResult(ok=False, error="not_found", summary="No complaint found with that reference code.")
    # A student may only see the status of their own complaint.
    student_id = ctx.require_student()
    if complaint.student_id != student_id:
        return ToolResult(ok=False, error="forbidden", summary="That complaint does not belong to you.")
    return ToolResult(ok=True, data=complaint.model_dump(mode="json"), summary=f"Status: {complaint.status}.")


file_complaint_tool = Tool(
    name="file_complaint",
    description="File a new complaint (maintenance, security, academic, hostel, utilities, other) on the student's behalf.",
    params_model=ComplaintCreate,
    handler=_file_complaint,
    requires_auth=True,
)

get_complaint_status_tool = Tool(
    name="get_complaint_status",
    description="Check the status of a previously filed complaint by its reference code.",
    params_model=GetComplaintStatusParams,
    handler=_get_complaint_status,
    requires_auth=True,
)
