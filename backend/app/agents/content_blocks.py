"""Deterministic mapping from a tool's own result to a content block.

This is the entire "decision" of which rich UI to render — driven purely
by which tool ran and the shape of its (already-validated) data, never by
asking the model to choose or construct a block itself. See
schemas/content_blocks.py for why that boundary matters.

Every builder is defensive about missing/unexpected fields (tool data
comes from Pydantic schemas we control, but this module has no business
crashing a chat turn over a rendering decision) and returns an empty list
rather than a broken block when there's nothing worth showing.
"""
from __future__ import annotations

from typing import Any

from app.schemas.content_blocks import (
    BlockAction,
    CardBlock,
    ChartBlock,
    ChartSeriesItem,
    ContentBlock,
    FieldItem,
    FileBlock,
    FileItem,
    ListBlock,
    ListItem,
    TableBlock,
    TableColumn,
)

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def build_blocks_for_tool(tool_name: str, ok: bool, data: Any) -> list[ContentBlock]:
    if not ok or data is None:
        return []
    builder = _BUILDERS.get(tool_name)
    if not builder:
        return []
    try:
        return builder(data)
    except Exception:
        # A rendering decision should never break the chat turn itself -
        # the plain-text summary the model already has still gets through.
        return []


def _hostel_table_and_chart(hostels: list[dict]) -> list[ContentBlock]:
    if not hostels:
        return []
    blocks: list[ContentBlock] = [
        TableBlock(
            title="Hostels near campus",
            columns=[
                TableColumn(key="name", label="Name"),
                TableColumn(key="area", label="Area"),
                TableColumn(key="price", label="Price", align="right"),
                TableColumn(key="distance", label="Distance", align="right"),
                TableColumn(key="verified", label="Verified"),
                TableColumn(key="availability", label="Availability"),
            ],
            rows=[
                {
                    "name": h["name"],
                    "area": h["area"],
                    "price": f"KSh {h['price_ksh']:,}",
                    "distance": f"{h['distance_from_campus_km']} km",
                    "verified": "Verified" if h["verified"] else "Unverified",
                    "availability": h["availability"],
                }
                for h in hostels
            ],
        )
    ]
    if len(hostels) >= 2:
        blocks.append(
            ChartBlock(
                title="Price comparison",
                unit="KSh/month",
                series=[ChartSeriesItem(label=h["name"], value=h["price_ksh"]) for h in hostels[:8]],
            )
        )
    return blocks


def _hostel_card(hostel: dict) -> list[ContentBlock]:
    return [
        CardBlock(
            title=hostel["name"],
            subtitle=f"{hostel['area']} · {hostel['distance_from_campus_km']} km from campus",
            image_url=hostel.get("image_url"),
            badge="Verified" if hostel["verified"] else "Unverified",
            badge_tone="verified" if hostel["verified"] else "warning",
            fields=[
                FieldItem(label="Price", value=f"KSh {hostel['price_ksh']:,}/month"),
                FieldItem(label="Availability", value=hostel["availability"]),
                FieldItem(label="Amenities", value=", ".join(hostel["amenities"]) or "Not listed"),
            ]
            + ([FieldItem(label="Contact", value=hostel["contact_phone"])] if hostel.get("contact_phone") else []),
        )
    ]


def _timetable_table(entries: list[dict]) -> list[ContentBlock]:
    if not entries:
        return []
    return [
        TableBlock(
            title="Class timetable",
            columns=[
                TableColumn(key="day", label="Day"),
                TableColumn(key="time", label="Time"),
                TableColumn(key="course", label="Course"),
                TableColumn(key="venue", label="Venue"),
                TableColumn(key="type", label="Type"),
            ],
            rows=[
                {
                    "day": _DAY_NAMES[e["day_of_week"]],
                    "time": f"{e['start_time']} - {e['end_time']}",
                    "course": f"{e['course_code']} · {e['course_name']}",
                    "venue": e["venue"],
                    "type": e["session_type"],
                }
                for e in entries
            ],
        )
    ]


def _deadlines_list(deadlines: list[dict]) -> list[ContentBlock]:
    if not deadlines:
        return []
    return [
        ListBlock(
            title="Upcoming deadlines",
            items=[
                ListItem(
                    title=d["title"],
                    description=d["description"],
                    meta=str(d["due_date"]),
                    badge=d["category"],
                )
                for d in deadlines
            ],
        )
    ]


def _past_papers_file_block(papers: list[dict]) -> list[ContentBlock]:
    if not papers:
        return []
    return [
        FileBlock(
            title="Past papers",
            files=[
                FileItem(
                    name=p["file_name"],
                    url=p["download_url"],
                    kind="pdf",
                    description=f"{p['course_code']} · {p['academic_year']} semester {p['semester']} ({p['exam_type']})",
                )
                for p in papers
            ],
        )
    ]


def _single_past_paper_file_block(paper: dict) -> list[ContentBlock]:
    return _past_papers_file_block([paper])


def _complaint_card(complaint: dict, *, title: str) -> list[ContentBlock]:
    tone_by_status = {
        "submitted": "info",
        "in_review": "warning",
        "resolved": "verified",
        "rejected": "error",
    }
    return [
        CardBlock(
            title=title,
            subtitle=complaint["category"].replace("_", " ").title(),
            badge=complaint["status"].replace("_", " "),
            badge_tone=tone_by_status.get(complaint["status"], "neutral"),
            fields=[
                FieldItem(label="Reference", value=complaint["reference_code"]),
            ]
            + ([FieldItem(label="Location", value=complaint["location"])] if complaint.get("location") else []),
            actions=[BlockAction(label="View my complaints", href="/complaints")],
        )
    ]


_BUILDERS = {
    "search_hostels": _hostel_table_and_chart,
    "get_hostel": _hostel_card,
    "get_timetable": _timetable_table,
    "list_academic_deadlines": _deadlines_list,
    "search_past_papers": _past_papers_file_block,
    "get_past_paper": _single_past_paper_file_block,
    "file_complaint": lambda data: _complaint_card(data, title="Complaint filed"),
    "get_complaint_status": lambda data: _complaint_card(data, title="Complaint status"),
}
