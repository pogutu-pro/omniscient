from __future__ import annotations

from app.agents.content_blocks import build_blocks_for_tool


def test_unknown_tool_returns_no_blocks():
    assert build_blocks_for_tool("not_a_real_tool", True, {"x": 1}) == []


def test_failed_tool_result_returns_no_blocks():
    assert build_blocks_for_tool("search_hostels", False, [{"name": "X"}]) == []


def test_empty_data_returns_no_blocks():
    assert build_blocks_for_tool("search_hostels", True, None) == []


def _hostel(**overrides) -> dict:
    defaults = dict(
        id="h1",
        name="Boma View Hostel",
        area="Boma",
        distance_from_campus_km=0.4,
        price_ksh=6500,
        verified=True,
        amenities=["wifi", "water"],
        availability="available",
        description="Demo listing",
        contact_phone=None,
        source="mock",
        image_url=None,
    )
    defaults.update(overrides)
    return defaults


def test_search_hostels_single_result_gives_table_only():
    blocks = build_blocks_for_tool("search_hostels", True, [_hostel()])
    assert [b.type for b in blocks] == ["table"]
    assert blocks[0].rows[0]["name"] == "Boma View Hostel"
    assert blocks[0].rows[0]["price"] == "KSh 6,500"


def test_search_hostels_multiple_results_adds_price_chart():
    hostels = [_hostel(id="h1", name="A", price_ksh=5000), _hostel(id="h2", name="B", price_ksh=7000)]
    blocks = build_blocks_for_tool("search_hostels", True, hostels)
    assert [b.type for b in blocks] == ["table", "chart"]
    assert blocks[1].series[0].label == "A"
    assert blocks[1].series[0].value == 5000


def test_search_hostels_empty_list_gives_no_blocks():
    assert build_blocks_for_tool("search_hostels", True, []) == []


def test_get_hostel_gives_card_with_fields():
    block = build_blocks_for_tool("get_hostel", True, _hostel(image_url="http://x/img.jpg"))[0]
    assert block.type == "card"
    assert block.title == "Boma View Hostel"
    assert block.image_url == "http://x/img.jpg"
    assert block.badge == "Verified"
    assert any(f.label == "Price" for f in block.fields)


def test_get_hostel_unverified_badge_tone_is_warning():
    block = build_blocks_for_tool("get_hostel", True, _hostel(verified=False))[0]
    assert block.badge == "Unverified"
    assert block.badge_tone == "warning"


def test_get_timetable_gives_table_with_day_names():
    entries = [
        {
            "id": "t1",
            "course_id": "c1",
            "course_code": "SCS 2101",
            "course_name": "Database Systems",
            "day_of_week": 0,
            "start_time": "08:00",
            "end_time": "10:00",
            "venue": "LT1",
            "session_type": "lecture",
        }
    ]
    block = build_blocks_for_tool("get_timetable", True, entries)[0]
    assert block.type == "table"
    assert block.rows[0]["day"] == "Monday"
    assert "SCS 2101" in block.rows[0]["course"]


def test_list_academic_deadlines_gives_list_block():
    deadlines = [
        {"id": "d1", "title": "Fee clearance", "description": "Clear fees", "category": "fees", "due_date": "2027-01-01"}
    ]
    block = build_blocks_for_tool("list_academic_deadlines", True, deadlines)[0]
    assert block.type == "list"
    assert block.items[0].title == "Fee clearance"
    assert block.items[0].badge == "fees"


def test_search_past_papers_gives_file_block():
    papers = [
        {
            "id": "p1",
            "course_code": "SCS 2101",
            "course_name": "Database Systems",
            "academic_year": "2023/2024",
            "semester": 1,
            "exam_type": "main",
            "file_name": "scs2101.pdf",
            "download_url": "http://x/download",
        }
    ]
    block = build_blocks_for_tool("search_past_papers", True, papers)[0]
    assert block.type == "file"
    assert block.files[0].kind == "pdf"
    assert block.files[0].url == "http://x/download"


def test_file_complaint_gives_status_card():
    complaint = {
        "id": "c1",
        "reference_code": "OMN-ABC123",
        "category": "maintenance",
        "details": "Leaking tap",
        "location": "Room B14",
        "status": "submitted",
    }
    block = build_blocks_for_tool("file_complaint", True, complaint)[0]
    assert block.type == "card"
    assert block.title == "Complaint filed"
    assert block.badge == "submitted"
    assert block.badge_tone == "info"
    assert any(f.value == "OMN-ABC123" for f in block.fields)


def test_builder_exception_returns_empty_list_not_a_crash():
    # Missing required keys should degrade to "no block", never raise.
    assert build_blocks_for_tool("search_hostels", True, [{"unexpected": True}]) == []
