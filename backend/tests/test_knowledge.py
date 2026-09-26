"""Tests for the OMNISCIENT knowledge base.

Three layers, tested at the level each one can actually fail:

- The parser and the text utilities are pure, so they are tested against the
  real 119-page dataset text as well as small hand-written fixtures. The
  fixture cases pin behaviour the real document depends on but does not
  obviously advertise; the real-document cases catch the things nobody
  thought to write a fixture for.
- The repository is tested through a real SQLite database, because the whole
  point of writing a portable `ILIKE` query instead of PostgreSQL full-text
  search is that this is the query production runs.
- The search service is tested for the answers it must get right, including
  the ones where returning nothing is the correct answer.
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.knowledge_repository import KnowledgeNotIngested, SqlKnowledgeRepository
from app.services.knowledge_ingest import KnowledgeIngestError, extract_text, ingest_knowledge_pdf
from app.services.knowledge_parser import parse_knowledge_document
from app.services.knowledge_search import format_for_llm, search_knowledge
from app.services.knowledge_text import normalise_for_search, tokenize

# --------------------------------------------------------------------------
# Text utilities
# --------------------------------------------------------------------------


def test_normalise_folds_case_punctuation_and_whitespace():
    assert normalise_for_search("Dean's   Office  —  E-MAIL!") == "dean office email"


def test_normalise_joins_a_hyphenated_word_rather_than_splitting_it():
    # This document labels contacts "E-MAIL". Split the hyphen and the
    # minimum-token filter drops the lone "e", so the label indexes as "mail"
    # while anyone typing "email" produces "email" — and the two never meet.
    assert normalise_for_search("E-MAIL") == normalise_for_search("email") == "email"


def test_normalise_keeps_digit_groups_separate_for_phone_compaction():
    # The hyphen must still separate digit runs, or the compactor sees one
    # 12-digit number instead of a 10-digit phone number.
    assert normalise_for_search("0709-202-942") == normalise_for_search("0709 202 942")
    assert normalise_for_search("0709 202 942").endswith("0709202942")


def test_normalise_keeps_digits_so_phones_are_searchable():
    # Stripping digits would make a phone number unsearchable, which is the
    # single most common question the dataset is asked.
    assert normalise_for_search("+254 712 345 678").endswith("254712345678")


def test_tokenize_drops_stopwords_but_keeps_meaning():
    tokens = tokenize("What is the Dean's office email?")
    assert "dean" in tokens
    assert "email" in tokens
    assert "the" not in tokens
    assert "what" not in tokens


def test_tokenize_singularises_simple_plurals():
    # "How do I pay my fees" must reach a fact whose value is "Fee payment".
    assert "fee" in tokenize("How do I pay my fees?")


def test_tokenize_deduplicates_and_preserves_order():
    assert tokenize("email email phone") == ["email", "phone"]


def test_tokenize_empty_for_punctuation_only():
    assert tokenize("   ...  ") == []


# --------------------------------------------------------------------------
# Parser — hand-written fixtures for the shapes the real document relies on
# --------------------------------------------------------------------------

FIXTURE = """OMNISCIENT DATASET
Title: DeKUT Knowledge Base

1. CONTACT DETAILS
Dean's office E-mail: dean@dekut.ac.ke
Dean's office phone: +254 712 000 111

2. PAYMENT PROCESS
Step 1 — Open the DeKUT Student Portal
Step 2 — Log in
Step 3 — Select "Make Payment"

3. RULES
Rule 1 — Always confirm the amount before paying
Rule 2 — Never share your registration number
"""


def test_parser_splits_sections_with_numbers_titles_and_bodies():
    parsed = parse_knowledge_document(FIXTURE)
    numbers = [s.number for s in parsed.sections]
    assert "1" in numbers and "2" in numbers and "3" in numbers
    payment = next(s for s in parsed.sections if s.number == "2")
    assert "PAYMENT" in payment.title.upper()
    assert "Student Portal" in payment.body


def test_parser_extracts_label_value_facts():
    parsed = parse_knowledge_document(FIXTURE)
    pairs = {(f.entity, f.attribute): f.value for f in parsed.facts}
    # A contact's entity is the section it was found in, and the attribute is
    # the whole label slugified, so two sections can each carry their own
    # "dean's office" without colliding.
    assert pairs[("CONTACT DETAILS", "dean_s_office_e_mail")] == "dean@dekut.ac.ke"
    assert pairs[("CONTACT DETAILS", "dean_s_office_phone")] == "+254 712 000 111"


def test_parser_extracts_numbered_steps_as_facts():
    parsed = parse_knowledge_document(FIXTURE)
    steps = sorted(
        (f.ordinal, f.value) for f in parsed.facts if f.attribute == "step" and f.section_number == "2"
    )
    assert steps == [
        (1, "Open the DeKUT Student Portal"),
        (2, "Log in"),
        (3, 'Select "Make Payment"'),
    ]


def test_parser_extracts_rules_as_guardrails():
    parsed = parse_knowledge_document(FIXTURE)
    titles = " ".join(g.title for g in parsed.guardrails).lower()
    assert "confirm the amount" in titles
    assert "never share your registration number" in titles
    # Rules are guardrails and nothing else: a rule that is also stored as a
    # retrievable fact is a rule that can be quoted as a fact.
    assert not [f for f in parsed.facts if f.category == "rule"]


def test_parser_joins_a_rule_title_that_wraps_onto_the_next_line():
    # Rules 2 and 5 of the real document print this way. Reading only the
    # first line stores a rule whose body begins with the tail of its own
    # title, which truncates the instruction it exists to carry.
    text = (
        "9. IMPORTANT AI KNOWLEDGE RULES\n"
        "An AI system trained on this information should follow these rules:\n\n"
        'Rule 1 — Do not call the current DeKUTSO Chairperson "President"\n'
        "automatically.\n"
        "The current Student Council structure uses the title Chairperson.\n"
    )
    guardrail = parse_knowledge_document(text).guardrails[0]
    assert guardrail.title == 'Do not call the current DeKUTSO Chairperson "President" automatically.'
    assert guardrail.body.startswith("The current Student Council")
    # The section's framing prose is not part of Rule 1.
    assert "An AI system trained" not in guardrail.body


def test_parser_stops_a_rule_body_at_the_next_section():
    text = (
        "9. IMPORTANT AI RULES\n"
        "Rule 1 — Verify current information against official DeKUT communication.\n"
        "Operating arrangements should be verified.\n"
        "10. NEXT SECTION\n"
        "Unrelated body text.\n"
    )
    guardrail = parse_knowledge_document(text).guardrails[0]
    assert "NEXT SECTION" not in guardrail.body
    assert "Unrelated body text." not in guardrail.body


def test_parser_stores_a_step_without_repeating_its_number():
    # The ordinal is a column of its own, so restating "Step 3 —" inside the
    # value makes every retrieved step read like a transcript line.
    parsed = parse_knowledge_document(FIXTURE)
    steps = [f.value for f in parsed.facts if f.attribute == "step"]
    assert not [v for v in steps if v.lower().startswith("step ")]


def test_parser_ignores_front_matter_as_a_section():
    parsed = parse_knowledge_document(FIXTURE)
    assert all(s.number != "Title" for s in parsed.sections)
    assert all("Title:" not in s.title for s in parsed.sections)


def test_parser_handles_two_level_numbering():
    text = "1. FIRST\nBody one.\n\n1.1 SUB\nSub body.\n\n2. SECOND\nOther body.\n"
    parsed = parse_knowledge_document(text)
    numbers = {s.number for s in parsed.sections}
    assert {"1", "1.1", "2"} <= numbers


def test_parser_does_not_treat_a_phone_number_as_a_heading():
    # A bare "+254 7…" line looks like a short heading to any regex matching
    # short capitalised lines. Misreading it drops the whole section that
    # follows, so this is worth pinning.
    text = "1. CONTACT\n+254 712 000 111\nMore text here.\n"
    parsed = parse_knowledge_document(text)
    assert [s.number for s in parsed.sections] == ["1"]


def test_parser_does_not_let_a_wrapped_heading_swallow_the_next_line():
    text = "1. A VERY LONG HEADING THAT WRAPS\nAND CONTINUES ON THE NEXT LINE\nBody text.\n"
    parsed = parse_knowledge_document(text)
    assert len(parsed.sections) == 1
    assert "Body text." in parsed.sections[0].body


def test_parser_reports_no_warnings_on_the_fixture():
    assert parse_knowledge_document(FIXTURE).warnings == []


# --------------------------------------------------------------------------
# Parser — the real 119-page dataset
# --------------------------------------------------------------------------

REAL_TEXT = "/tmp/opencode/omniscient_dataset.txt"
pytestmark_real = pytest.mark.skipif(
    not __import__("pathlib").Path(REAL_TEXT).is_file(),
    reason="extracted dataset text is not present in this environment",
)


@pytestmark_real
def test_real_dataset_parses_without_warnings():
    parsed = parse_knowledge_document(open(REAL_TEXT, encoding="utf-8").read())
    assert parsed.warnings == []


@pytestmark_real
def test_real_dataset_finds_all_seven_guardrails():
    parsed = parse_knowledge_document(open(REAL_TEXT, encoding="utf-8").read())
    assert len(parsed.guardrails) == 7


@pytestmark_real
def test_real_dataset_finds_the_documented_section_count():
    parsed = parse_knowledge_document(open(REAL_TEXT, encoding="utf-8").read())
    # 41 numbered sections plus 10 subsections, per the dataset's own contents.
    assert len(parsed.sections) == 51


@pytestmark_real
def test_real_dataset_has_no_fact_identity_that_claims_two_values():
    parsed = parse_knowledge_document(open(REAL_TEXT, encoding="utf-8").read())
    seen: dict[tuple, set[str]] = {}
    for fact in parsed.facts:
        seen.setdefault((fact.category, fact.entity, fact.attribute, fact.ordinal), set()).add(fact.value)
    collisions = {key: values for key, values in seen.items() if len(values) > 1}
    assert collisions == {}


# --------------------------------------------------------------------------
# Ingest + repository, against a real database
# --------------------------------------------------------------------------


@pytest.fixture
def pdf_path(tmp_path):
    path = tmp_path / "dataset.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    return path


async def test_ingest_reports_counts_and_commits(db_session: AsyncSession, pdf_path):
    repository = SqlKnowledgeRepository(db_session)
    report = await ingest_knowledge_pdf(repository, pdf_path, text=FIXTURE)
    await db_session.commit()

    assert report.changed is True
    assert report.counts.sections == 3
    assert report.counts.guardrails == 2
    assert report.counts.facts > 0


async def test_ingest_is_idempotent_and_skips_an_unchanged_source(db_session: AsyncSession, pdf_path):
    repository = SqlKnowledgeRepository(db_session)
    first = await ingest_knowledge_pdf(repository, pdf_path, text=FIXTURE)
    await db_session.commit()
    second = await ingest_knowledge_pdf(repository, pdf_path, text=FIXTURE)
    await db_session.commit()

    assert first.changed is True
    assert second.changed is False
    assert "already matches" in (second.skipped_reason or "")


async def test_ingest_force_reparses_an_unchanged_source(db_session: AsyncSession, pdf_path):
    repository = SqlKnowledgeRepository(db_session)
    await ingest_knowledge_pdf(repository, pdf_path, text=FIXTURE)
    await db_session.commit()
    forced = await ingest_knowledge_pdf(repository, pdf_path, text=FIXTURE, force=True)
    await db_session.commit()
    assert forced.changed is True


async def test_reingest_replaces_content_rather_than_duplicating_it(db_session: AsyncSession, pdf_path):
    repository = SqlKnowledgeRepository(db_session)
    await ingest_knowledge_pdf(repository, pdf_path, text=FIXTURE)
    await db_session.commit()
    before = await repository.count_content((await repository.get_document()).id)

    await ingest_knowledge_pdf(repository, pdf_path, text="1. ONLY\nOne fact: nothing\n")
    await db_session.commit()
    document = await repository.get_document()
    after = await repository.count_content(document.id)

    assert after.sections == 1
    assert after.sections < before.sections
    assert after.facts == 1


async def test_ingest_rejects_a_missing_file(db_session: AsyncSession, tmp_path):
    repository = SqlKnowledgeRepository(db_session)
    with pytest.raises(KnowledgeIngestError, match="No such file"):
        await ingest_knowledge_pdf(repository, tmp_path / "absent.pdf")


def test_extract_text_rejects_a_non_pdf(tmp_path):
    # A file with no text layer must fail loudly here rather than load an
    # empty knowledge base that later reports "the dataset says nothing".
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")
    with pytest.raises(KnowledgeIngestError):
        extract_text(path)


async def test_search_before_ingest_says_the_base_is_unavailable(db_session: AsyncSession):
    repository = SqlKnowledgeRepository(db_session)
    answer = await search_knowledge(repository, "what is the deans email")
    assert answer.available is False
    assert "not loaded" in (answer.note or "")


async def test_all_guardrails_raises_before_ingest(db_session: AsyncSession):
    repository = SqlKnowledgeRepository(db_session)
    with pytest.raises(KnowledgeNotIngested):
        await repository.all_guardrails()


async def test_facts_with_attribute_is_an_exact_lookup(db_session: AsyncSession, pdf_path):
    repository = SqlKnowledgeRepository(db_session)
    await ingest_knowledge_pdf(repository, pdf_path, text=FIXTURE)
    await db_session.commit()
    rows = await repository.facts_with_attribute("phone")
    assert [row.value for row in rows] == ["+254 712 000 111"]


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------


@pytest.fixture
async def loaded(db_session: AsyncSession, pdf_path):
    repository = SqlKnowledgeRepository(db_session)
    await ingest_knowledge_pdf(repository, pdf_path, text=FIXTURE)
    await db_session.commit()
    return repository


async def test_search_finds_a_contact_by_email(loaded):
    answer = await search_knowledge(loaded, "what is the deans office email")
    assert answer.available is True
    assert any(fact.fact.value == "dean@dekut.ac.ke" for fact in answer.facts)


async def test_search_finds_a_phone_number_despite_punctuation(loaded):
    answer = await search_knowledge(loaded, "deans office phone number")
    assert any("712 000 111" in fact.fact.value for fact in answer.facts)


async def test_search_returns_the_payment_steps_in_order(loaded):
    answer = await search_knowledge(loaded, "how do i pay my fees at the portal")
    # Facts are sorted by score then ordinal; steps must all be present.
    step_values = [f.fact.value for f in answer.facts if f.fact.attribute == "step"]
    assert "Open the DeKUT Student Portal" in step_values
    assert 'Select "Make Payment"' in step_values
    # When two steps have equal score, ordinal order is preserved —
    # the portal step (ordinal 1) must appear before the login step (ordinal 2).
    portal_idx = step_values.index("Open the DeKUT Student Portal")
    login_idx = step_values.index("Log in") if "Log in" in step_values else len(step_values)
    assert portal_idx < login_idx


async def test_search_always_returns_every_guardrail(loaded):
    answer = await search_knowledge(loaded, "what is the deans office email")
    assert len(answer.guardrails) == 2


async def test_search_returns_guardrails_even_when_nothing_matches(loaded):
    answer = await search_knowledge(loaded, "how do I book a helicopter")
    assert answer.is_empty is True
    # A rule that was filtered out because the query missed it is a rule that
    # cannot be obeyed, so they survive a null result.
    assert len(answer.guardrails) == 2
    assert "could not find" in (answer.note or "").lower()


async def test_search_on_a_punctuation_only_query_returns_nothing_gracefully(loaded):
    answer = await search_knowledge(loaded, "   ...   ")
    assert answer.facts == []
    assert "no searchable words" in (answer.note or "")


async def test_search_truncates_a_pasted_prose_query(loaded):
    # tokenize() deduplicates, so we need 25+ *distinct* words to exceed MAX_QUERY_TOKENS=24.
    distinct_words = " ".join(f"word{i}" for i in range(30))
    answer = await search_knowledge(loaded, distinct_words)
    assert answer.available is True
    assert "truncated" in (answer.note or "")


async def test_max_facts_is_respected(loaded):
    answer = await search_knowledge(loaded, "payment", max_facts=1)
    assert len(answer.facts) <= 1


# --------------------------------------------------------------------------
# Prompt rendering
# --------------------------------------------------------------------------


async def test_format_puts_rules_before_facts(loaded):
    answer = await search_knowledge(loaded, "deans office email")
    text = format_for_llm(answer)
    assert text.index("Rules you must follow") < text.index("Facts from the dataset")
    assert "dean@dekut.ac.ke" in text
    assert "[no dataset match]" not in text


async def test_format_reports_an_unavailable_base_without_inventing_content(db_session: AsyncSession):
    repository = SqlKnowledgeRepository(db_session)
    text = format_for_llm(await search_knowledge(repository, "deans email"))
    assert "unavailable" in text
    assert "dean@" not in text


async def test_format_marks_a_null_result(loaded):
    text = format_for_llm(await search_knowledge(loaded, "helicopter booking"))
    assert "no dataset match" in text


def test_excerpt_is_centred_on_the_match_and_bounded(loaded=None):
    from app.services.knowledge_search import _excerpt

    body = "First sentence about fees. " + ("Filler prose. " * 200) + "The refund window is fourteen days."
    excerpt = _excerpt(body, ("refund",), window=120)
    assert "refund" in excerpt
    assert len(excerpt) < len(body)
    assert excerpt.startswith("…")
