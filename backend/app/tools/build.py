from __future__ import annotations

from app.tools.academic_tools import get_timetable_tool, list_deadlines_tool
from app.tools.complaint_tools import file_complaint_tool, get_complaint_status_tool
from app.tools.housing_tools import get_hostel_tool, search_hostels_tool
from app.tools.past_paper_tools import get_past_paper_tool, search_past_papers_tool
from app.tools.registry import ToolRegistry


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (
        search_hostels_tool,
        get_hostel_tool,
        get_timetable_tool,
        list_deadlines_tool,
        search_past_papers_tool,
        get_past_paper_tool,
        file_complaint_tool,
        get_complaint_status_tool,
    ):
        registry.register(tool)
    return registry
