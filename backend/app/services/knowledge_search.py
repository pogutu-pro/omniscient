"""Answer a question from the OMNISCIENT knowledge base.

No embeddings, no vector database, no reranker. That is a deliberate
consequence of the deployment audit rather than a simplification: the target
is a 2 vCPU / 12 GB ARM instance with no embedding service, a 1536 MB memory
ceiling, and a corpus of a few hundred facts. An embedding pipeline there
would cost a model download, a per-query forward pass and a maintenance
surface, to solve a ranking problem this corpus does not have.

What replaces it:

- Facts are *atomic* — "phone number: +254 7…", "Chairperson: Prof. …" — so
  the answer to most questions is a row lookup, not a similarity judgement
  about two paragraphs. The top hit is normally the right answer, because
  there is nothing else it could plausibly be.
- Guardrails are loaded whole, every query, never ranked.
- Sections are the fallback, for the questions no fact answers.

Scoring is a small, fixed-weight sum rather than a learned model, so a
result can be explained ("this matched `fee` in the value and `payment` in
the entity") and, more importantly, so it cannot hallucinate a confidence.
The number returned is not a probability and must not be presented as one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.knowledge import KnowledgeFact, KnowledgeGuardrail, KnowledgeSection
from app.repositories.knowledge_repository import KnowledgeNotIngested, KnowledgeRepository
from app.services.knowledge_text import normalise_for_search, tokenize

# Field weights. An answer lives in `value`; `entity` and `attribute` say what
# the value is *about*, so they are strong evidence of a match but weaker
# evidence of an answer. `detail` is supporting prose and barely counts.
_VALUE_WEIGHT = 3.0
_ATTRIBUTE_WEIGHT = 2.5
_ENTITY_WEIGHT = 2.0
_DETAIL_WEIGHT = 0.5

# Sections invert the emphasis: a heading is a summary of its own body, so
# matching a section title is strong evidence the section is the right one.
_SECTION_TITLE_WEIGHT = 2.5
_SECTION_BODY_WEIGHT = 0.5

# Reward for matching a long run of the query verbatim. Guards against the
# single-token case: a fact about "fees" matches the word "fees" in almost
# any question about money, and only an exact phrase is discriminative.
_PHRASE_BONUS = 6.0
_PHRASE_MIN_TOKENS = 3

# Coverage multiplier. Rewards results that match *most* of the question, not
# just one rare word in it. This is what separates "the payment phone number"
# from a stray fact that happens to contain "number".
_COVERAGE_WEIGHT = 4.0

# A result must clear this to be returned. Low by design: the caller is an
# assistant that is told the score, and a thin answer clearly labelled as
# thin beats a confident fabrication. The search never returns a guardrail
# filtered by score, and never returns a section body it scored low.
MIN_SCORE = 2.0

# A query with more than this many tokens is not a question about the
# dataset; it is probably pasted prose, and tokenising it produces a filter
# so loose that ranking rather than filtering does all the work.
MAX_QUERY_TOKENS = 24

_CONTACT_HINTS = frozenset(
    {"email", "emails", "phone", "telephone", "contact", "number", "call", "reach", "extension"}
)
# Asking "who" wants a person, not a procedure. Sections titled "… PROCESS" or
# "… PROCEDURE" are demoted for these queries so a leadership fact outranks
# the process that mentions the same title.
_PERSONAL_HINTS = frozenset({"who", "chairperson", "chairman", "chairperson", "dean", "director", "leader", "head"})
_PROCEDURAL_TITLES = ("process", "procedure", "flow", "step", "steps", "workflow")


@dataclass(frozen=True)
class ScoredFact:
    fact: KnowledgeFact
    score: float
    matched: tuple[str, ...] = ()

    @property
    def answer(self) -> str:
        return self.fact.value

    def as_dict(self) -> dict:
        return {
            "section": self.fact.section_number,
            "category": self.fact.category,
            "entity": self.fact.entity,
            "attribute": self.fact.attribute,
            "value": self.fact.value,
            "detail": self.fact.detail or None,
            "score": round(self.score, 2),
        }


@dataclass(frozen=True)
class ScoredSection:
    section: KnowledgeSection
    score: float
    matched: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "section": self.section.number,
            "title": self.section.title,
            "excerpt": _excerpt(self.section.body, self.matched),
            "score": round(self.score, 2),
        }


@dataclass
class KnowledgeAnswer:
    """Everything a caller needs, and nothing that invites misuse.

    `available` is separate from the result lists on purpose. An assistant
    that cannot distinguish "not loaded" from "nothing matched" will say the
    dataset says nothing when in fact nobody loaded it.
    """

    available: bool
    query: str
    facts: list[ScoredFact] = field(default_factory=list)
    sections: list[ScoredSection] = field(default_factory=list)
    guardrails: list[KnowledgeGuardrail] = field(default_factory=list)
    note: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.facts and not self.sections

    def as_dict(self) -> dict:
        return {
            "available": self.available,
            "query": self.query,
            "note": self.note,
            "facts": [fact.as_dict() for fact in self.facts],
            "sections": [section.as_dict() for section in self.sections],
            "guardrails": [
                {"rule": g.rule_number, "title": g.title, "body": g.body} for g in self.guardrails
            ],
        }


def _token_hits(text: str, tokens: list[str]) -> list[str]:
    """Tokens present in `text`, tested against the normalised form.

    Matching the normalised text rather than the raw one is what makes
    "e-mail"/"email", "Telephone"/"TEL" and "Chairperson"/"CHAIRPERSON" all
    behave identically without a synonym list.
    """
    if not text:
        return []
    haystack = normalise_for_search(text)
    return [token for token in tokens if token in haystack]


def _phrase_bonus(query_tokens: list[str], text: str) -> float:
    """Reward a verbatim run of the query inside `text`.

    Uses the *normalised* query so that a question with a typo-free but
    differently-punctuated phrasing ("how do i pay my fees?") still matches
    ("how do i pay my fees"). Requires a run of real tokens: a single common
    word is not a phrase.
    """
    if len(query_tokens) < _PHRASE_MIN_TOKENS:
        return 0.0
    haystack = normalise_for_search(text)
    best = 0.0
    for start in range(len(query_tokens)):
        for end in range(len(query_tokens), start + _PHRASE_MIN_TOKENS - 1, -1):
            run = " ".join(query_tokens[start:end])
            if run and run in haystack:
                best = max(best, _PHRASE_BONUS * (end - start) / len(query_tokens))
                break
    return best


def _score_fact(fact: KnowledgeFact, tokens: list[str], query_tokens: list[str]) -> ScoredFact | None:
    in_value = _token_hits(fact.value, tokens)
    in_entity = _token_hits(fact.entity, tokens)
    in_attribute = _token_hits(fact.attribute, tokens)
    in_detail = _token_hits(fact.detail, tokens) if fact.detail else []

    score = (
        _VALUE_WEIGHT * len(in_value)
        + _ENTITY_WEIGHT * len(in_entity)
        + _ATTRIBUTE_WEIGHT * len(in_attribute)
        + _DETAIL_WEIGHT * len(in_detail)
    )
    if not score:
        return None

    matched = {*in_value, *in_entity, *in_attribute, *in_detail}
    score += _COVERAGE_WEIGHT * (len(matched) / len(tokens))
    score += _phrase_bonus(query_tokens, f"{fact.entity} {fact.attribute} {fact.value}")

    # An exact-value question ("what is the Dean's email") should not have to
    # out-rank a contact list that merely mentions emails.
    if fact.category == "contact" and tokens and _CONTACT_HINTS.intersection(tokens):
        score += 1.5
    return ScoredFact(fact=fact, score=score, matched=tuple(sorted(matched)))


def _score_section(
    section: KnowledgeSection, tokens: list[str], query_tokens: list[str]
) -> ScoredSection | None:
    in_title = _token_hits(f"{section.number} {section.title}", tokens)
    in_body = _token_hits(section.body, tokens)
    score = _SECTION_TITLE_WEIGHT * len(in_title) + _SECTION_BODY_WEIGHT * len(in_body)
    if not score:
        return None
    matched = {*in_title, *in_body}
    score += _COVERAGE_WEIGHT * (len(matched) / len(tokens))
    score += _phrase_bonus(query_tokens, f"{section.number} {section.title} {section.body}")

    # A section that matches only in its body, and not its title, is a weaker
    # answer than one whose title matched; a section that matches on a token
    # that only ever appears in procedure titles is weaker still.
    if not in_title:
        score *= 0.6
    title = section.title.lower()
    if any(token in _PERSONAL_HINTS for token in tokens) and any(word in title for word in _PROCEDURAL_TITLES):
        score *= 0.5
    return ScoredSection(section=section, score=score, matched=tuple(sorted(matched)))


_EXCERPT_WINDOW = 320
_WORD = re.compile(r"\S+")


def _clip(body: str, start: int, end: int) -> str:
    """`body[start:end]`, trimmed to whole words, with an ellipsis where cut."""
    snippet = body[start:end]
    if start > 0:
        space = snippet.find(" ")
        if space != -1:
            snippet = snippet[space + 1 :]
    if end < len(body):
        space = snippet.rfind(" ")
        if space != -1:
            snippet = snippet[:space]
    snippet = snippet.strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(body):
        snippet = snippet + "…"
    return snippet


def _excerpt(body: str, matched: tuple[str, ...], window: int = _EXCERPT_WINDOW) -> str:
    """The passage around the first match, cut to whole words.

    Sections here run to several thousand characters. Sending a whole section
    to a model costs tokens proportional to the section and invites it to
    answer from a passage that was not the match, so the excerpt is centred
    on the hit.

    The match is located by normalising the body *word by word* rather than
    normalising the whole body and searching that string. Normalisation
    changes length — it drops stop words and joins "e-mail" into "email" —
    so an index into the normalised text does not point at the same place in
    the raw text, and using one directly centres the window on the wrong
    passage while still looking plausible.
    """
    if not body:
        return ""
    if not matched:
        return _clip(body, 0, window)

    hit = next(
        (
            word
            for word in _WORD.finditer(body)
            if any(token in normalise_for_search(word.group()) for token in matched)
        ),
        None,
    )
    if hit is None:
        return _clip(body, 0, window)

    centre = (hit.start() + hit.end()) // 2
    start = max(0, centre - window // 2)
    end = min(len(body), start + window)
    start = max(0, end - window)
    return _clip(body, start, end)


async def search_knowledge(
    repository: KnowledgeRepository,
    query: str,
    *,
    max_facts: int = 5,
    max_sections: int = 3,
    min_score: float = MIN_SCORE,
    include_guardrails: bool = True,
) -> KnowledgeAnswer:
    """Answer `query` from the ingested dataset.

    Guardrails come back on every call, including when nothing matched, since
    a rule that was filtered out because the query did not mention it is a
    rule that cannot be obeyed.
    """
    cleaned = (query or "").strip()
    tokens = tokenize(cleaned)
    if not tokens:
        return KnowledgeAnswer(
            available=True,
            query=cleaned,
            note="The question contained no searchable words, so nothing was retrieved.",
        )
    if len(tokens) > MAX_QUERY_TOKENS:
        tokens = tokens[:MAX_QUERY_TOKENS]
        note = f"Long question truncated to its first {MAX_QUERY_TOKENS} searchable words."
    else:
        note = None

    try:
        guardrails = await repository.all_guardrails() if include_guardrails else []
    except KnowledgeNotIngested:
        return KnowledgeAnswer(
            available=False,
            query=cleaned,
            note=(
                "The knowledge base is not loaded. Answer from the conversation only, "
                "and say the dataset is unavailable rather than guessing its contents."
            ),
        )

    fact_rows = await repository.candidate_facts(tokens, limit=max_facts)
    section_rows = await repository.candidate_sections(tokens, limit=max_sections)

    facts: list[ScoredFact] = []
    for row in fact_rows:
        scored = _score_fact(row, tokens, tokens)
        if scored is not None and scored.score >= min_score:
            facts.append(scored)
    # Sort by score, then by the document's own order, so an exact tie is
    # broken by reading order rather than by whatever the database returned.
    facts.sort(key=lambda scored: (-scored.score, scored.fact.section_number, scored.fact.ordinal))

    sections: list[ScoredSection] = []
    for row in section_rows:
        scored_section = _score_section(row, tokens, tokens)
        if scored_section is not None and scored_section.score >= min_score:
            sections.append(scored_section)
    sections.sort(key=lambda scored: (-scored.score, scored.section.sort_key))

    answer = KnowledgeAnswer(
        available=True,
        query=cleaned,
        facts=facts[:max_facts],
        sections=sections[:max_sections],
        guardrails=guardrails,
        note=note,
    )
    if answer.is_empty:
        empty_note = (
            "Nothing in the dataset matched that question closely enough. "
            "Say you could not find it, and offer the nearest section titles."
        )
        answer.note = f"{note} {empty_note}".strip() if note else empty_note
    return answer


def format_for_llm(answer: KnowledgeAnswer) -> str:
    """Render an answer as the text block to place in the model's context.

    Ordering is deliberate: guardrails first, so they are read before the
    facts and are still in view when the facts are used; then facts, because
    an atomic value is the cheapest possible answer; then sections, as
    context for anything a fact did not settle.

    Capped because an unbounded dump of this dataset would be both expensive
    and worse: a model given fifty near-duplicate rows tends to blend them
    rather than pick one.
    """
    if not answer.available:
        return f"[knowledge base unavailable] {answer.note or ''}".strip()

    parts: list[str] = []
    if answer.guardrails:
        rules = "\n".join(f"- [{g.rule_number}] {g.title}: {g.body}" for g in answer.guardrails)
        parts.append(f"### Rules you must follow (from the dataset)\n{rules}")

    if answer.facts:
        lines = []
        for fact in answer.facts:
            detail = f" — {fact.fact.detail}" if fact.fact.detail else ""
            lines.append(
                f"- §{fact.fact.section_number} {fact.fact.entity} / {fact.fact.attribute}: "
                f"{fact.fact.value}{detail}"
            )
        parts.append("### Facts from the dataset\n" + "\n".join(lines))

    if answer.sections:
        lines = [f"- §{s.section.number} {s.section.title}: {s.as_dict()['excerpt']}" for s in answer.sections]
        parts.append("### Relevant sections\n" + "\n".join(lines))

    if not parts:
        return f"[no dataset match] {answer.note or ''}".strip()

    header = "### OMNISCIENT dataset (DeKUT) — authoritative context"
    footer = ""
    if answer.is_empty:
        footer = f"\n\n[no dataset match] {answer.note or ''}".strip()
        footer = f"\n\n{footer}"
    return f"{header}\n\n" + "\n\n".join(parts) + footer
