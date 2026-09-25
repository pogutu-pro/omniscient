from __future__ import annotations

from app.agents.providers.mock_provider import MockProvider


async def test_past_paper_query_strips_request_filler_and_keywords():
    provider = MockProvider()
    result = await provider.classify_intent("Find Database Systems past papers", [], [])
    assert result["intent"] == "past_papers"
    assert result["parameters"]["query"] == "database systems"


async def test_past_paper_query_handles_course_code_phrasing():
    provider = MockProvider()
    result = await provider.classify_intent("Show me SCS 2101 past papers please", [], [])
    assert result["parameters"]["query"] == "scs 2101"


async def test_past_paper_query_falls_back_to_full_message_if_stripping_empties_it():
    provider = MockProvider()
    result = await provider.classify_intent("past papers", [], [])
    # Every word was filler/keyword - fall back rather than searching on "".
    assert result["parameters"]["query"] == "past papers"
