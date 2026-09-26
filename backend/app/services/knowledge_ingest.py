"""Turn the OMNISCIENT dataset PDF into knowledge base rows.

The whole pipeline is pure until the last step: read the PDF, parse it into
plain dataclasses, then hand a set of flat dictionaries to the repository.
Keeping it that way is what makes the interesting part — the parser — testable
without a database, and it is why `test_knowledge.py` can assert on real
extraction output instead of on mocks.

Ingestion is idempotent. A document is keyed on its slug, its content is
swapped wholesale, and re-running with an unchanged PDF short-circuits on the
source hash. An operator can therefore run this on every deploy without
checking whether they already did.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from app.models.knowledge import section_sort_key
from app.repositories.knowledge_repository import ContentCounts, KnowledgeRepository
from app.services.knowledge_parser import ParsedDocument, parse_knowledge_document
from app.services.knowledge_text import normalise_for_search

logger = logging.getLogger(__name__)

KNOWLEDGE_SLUG = "omniscient-dataset"
KNOWLEDGE_TITLE = "OMNISCIENT Dataset (DeKUT)"


class KnowledgeIngestError(RuntimeError):
    """The source document could not be read at all."""


@dataclass(frozen=True)
class IngestReport:
    slug: str
    source_file: str
    sha256: str
    counts: ContentCounts
    changed: bool
    warnings: tuple[str, ...]
    skipped_reason: str | None = None

    def summary(self) -> str:
        if self.skipped_reason:
            return (
                f"skipped {self.source_file} (sha {self.sha256[:12]}) — {self.skipped_reason}; "
                f"knowledge base unchanged"
            )
        verb = "ingested" if self.changed else "verified"
        counts = self.counts
        return (
            f"{verb} {self.source_file} (sha {self.sha256[:12]}): "
            f"{counts.sections} sections, {counts.facts} facts, {counts.guardrails} guardrails"
            + (f"; {len(self.warnings)} warnings" if self.warnings else "")
        )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_text(pdf_path: Path) -> str:
    """Read the PDF's text layer.

    Reuses the project's existing `extract_pages`, so a PDF the chat
    attachment pipeline can read is a PDF this can read, and its "this is a
    scan with no text layer" error is reused verbatim rather than
    reimplemented slightly wrong.

    Pages are joined with a blank line. Joining with nothing — or with a
    space, as raw extraction does — fuses the last line of one page to the
    first line of the next, and this document puts section headings at page
    tops often enough that the fusion would silently swallow them.
    """
    from app.services.document_chunker import DocumentExtractionError, extract_pages

    try:
        pages = extract_pages(pdf_path.read_bytes(), pdf_path.name)
    except DocumentExtractionError as exc:
        raise KnowledgeIngestError(str(exc)) from exc
    return "\n\n".join(page.text for page in pages)


def _section_row(section) -> dict:
    search_text = normalise_for_search(section.number, section.title, section.body)
    return {
        "number": section.number,
        "sort_key": section_sort_key(section.number),
        "title": section.title,
        "body": section.body,
        "search_text": search_text,
        "char_count": len(search_text),
    }


def _fact_row(fact) -> dict:
    """Flatten a `ParsedFact` into column values.

    `search_text` is computed here, at write time, from the same normaliser
    the query side uses. That is what lets the matching expression stay a
    portable `ILIKE` instead of a database-specific full-text configuration:
    everything dialect-sensitive about tokenisation is already resolved by the
    time the row is built.
    """
    search_text = normalise_for_search(fact.entity, fact.attribute, fact.value, fact.detail)
    return {
        "section_number": fact.section_number,
        "category": fact.category,
        "entity": fact.entity,
        "attribute": fact.attribute,
        "value": fact.value,
        "detail": fact.detail,
        "ordinal": fact.ordinal,
        "search_text": search_text,
        "char_count": len(search_text),
    }


def _guardrail_row(guardrail) -> dict:
    search_text = normalise_for_search(guardrail.rule_number, guardrail.title, guardrail.body)
    return {
        "rule_number": guardrail.rule_number,
        "title": guardrail.title,
        "body": guardrail.body,
        "search_text": search_text,
        "char_count": len(search_text),
    }


def _dedupe_facts(facts) -> tuple[list, list[str]]:
    """Collapse exact duplicates, and report ones that only half agree.

    The unique constraint is (category, entity, attribute, ordinal), so two
    different values on one key cannot both exist. The parser has already
    tried to separate genuinely distinct facts; anything still colliding here
    is a real ambiguity in the source, and it is surfaced as a warning that
    the ingest report carries, rather than being silently resolved.
    """
    by_key: dict[tuple, list] = {}
    for fact in facts:
        by_key.setdefault((fact.category, fact.entity, fact.attribute, fact.ordinal), []).append(fact)

    kept: list = []
    warnings: list[str] = []
    for key, group in by_key.items():
        if len(group) == 1:
            kept.append(group[0])
            continue
        values = {fact.value for fact in group}
        if len(values) == 1:
            # Identical fact stated twice, e.g. a contact repeated in a
            # directory and again in a contacts section. Keeping one is
            # correct and makes the two sources reinforce instead of
            # competing.
            kept.append(group[0])
            continue
        category, entity, attribute, ordinal = key
        warnings.append(
            f"Conflicting {category} values for {entity!r}/{attribute!r}/{ordinal}: {sorted(values)}. "
            "Kept the first and dropped the rest."
        )
        kept.append(group[0])

    kept.sort(key=lambda fact: (fact.section_number, fact.category, fact.entity, fact.attribute, fact.ordinal))
    return kept, warnings


async def ingest_knowledge_pdf(
    repository: KnowledgeRepository,
    pdf_path: Path,
    *,
    slug: str = KNOWLEDGE_SLUG,
    title: str = KNOWLEDGE_TITLE,
    force: bool = False,
    text: str | None = None,
) -> IngestReport:
    """Parse `pdf_path` and load it, skipping work when nothing has changed.

    `text` exists so tests can drive the pipeline with a fixture string
    instead of a binary blob. The hash is then taken over the text actually
    parsed, not the file, so the "unchanged" check stays meaningful for both
    paths.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise KnowledgeIngestError(f"No such file: {pdf_path}")

    source_text = text if text is not None else extract_text(pdf_path)
    digest = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    source_file = pdf_path.name

    document = await repository.get_document()
    if not force and document is not None and document.slug == slug and document.source_sha256 == digest:
        return IngestReport(
            slug=slug,
            source_file=source_file,
            sha256=digest,
            counts=await repository.count_content(document.id),
            changed=False,
            warnings=(),
            skipped_reason="the stored source hash already matches this file",
        )

    parsed: ParsedDocument = parse_knowledge_document(source_text)
    facts, warnings = _dedupe_facts(parsed.facts)
    warnings = list(parsed.warnings) + warnings

    for warning in warnings:
        logger.warning("knowledge ingest: %s", warning)

    document = await repository.upsert_document(slug=slug, title=title, source_file=source_file, sha256=digest)
    counts = await repository.replace_content(
        document_id=document.id,
        sections=[_section_row(section) for section in parsed.sections],
        facts=[_fact_row(fact) for fact in facts],
        guardrails=[_guardrail_row(guardrail) for guardrail in parsed.guardrails],
    )

    return IngestReport(
        slug=slug,
        source_file=source_file,
        sha256=digest,
        counts=counts,
        changed=True,
        warnings=tuple(warnings),
    )
