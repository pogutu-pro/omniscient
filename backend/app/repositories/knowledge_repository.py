"""Storage for the knowledge base.

An ABC plus a SQLAlchemy implementation, which is the shape every other
domain in this codebase uses so that tests can inject a fake instead of
standing up a database.

The matching query is deliberately plain SQL rather than a full-text index.
`search_text` is a precomputed, lowercased, punctuation-stripped blob and the
query is a conjunction of `ILIKE '%token%'`, which renders identically on
PostgreSQL and on the SQLite database the test suite builds — so the tests
exercise the query that actually runs in production. The corpus is a few
hundred rows, where a sequential scan is already sub-millisecond; a GIN
index would cost more to maintain on write than it saves on read, and
`tsvector` configuration is a migration to keep in step forever. If the
corpus ever grows by three orders of magnitude, add `pg_trgm` GIN indexes
here and nothing above this layer changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import (
    KnowledgeDocument,
    KnowledgeFact,
    KnowledgeGuardrail,
    KnowledgeSection,
)

class KnowledgeNotIngested(RuntimeError):
    """Raised when the knowledge base is queried before anything is loaded.

    A distinct error rather than an empty result set, for the same reason
    `ChunkRepository.similarity_search` refuses instead of returning nothing:
    "no document has been ingested" and "your question matched nothing" look
    identical to a caller, and the second is a real answer while the first is
    a deployment mistake.
    """


@dataclass(frozen=True)
class ContentCounts:
    sections: int = 0
    facts: int = 0
    guardrails: int = 0

    def as_dict(self) -> dict[str, int]:
        return {"sections": self.sections, "facts": self.facts, "guardrails": self.guardrails}


def _token_filter(column: sa.ColumnElement[str], tokens: list[str]) -> sa.ColumnElement[bool]:
    """Rows matching *any* of `tokens`.

    An `OR` rather than an `AND` on purpose. Requiring every token would be
    stricter, but "how do I pay my fees" shares no token with a row about the
    payment form, and an empty result is a worse answer than a lower-ranked
    one. The ranking, not the filter, decides what is good enough — so the
    full corpus stays reachable and scoring stays in one place.

    Tokens come from `normalise_for_search` and are therefore restricted to
    `[a-z0-9]+`, which is what makes it safe to interpolate them into a LIKE
    pattern without escaping: there is no `%` or `_` in the input to widen
    the match beyond the token.
    """
    return or_(*(column.ilike(f"%{token}%") for token in tokens))


class KnowledgeRepository(ABC):
    @abstractmethod
    async def get_document(self) -> KnowledgeDocument | None: ...

    @abstractmethod
    async def upsert_document(self, slug: str, title: str, source_file: str, sha256: str) -> KnowledgeDocument: ...

    @abstractmethod
    async def replace_content(
        self,
        document_id: str,
        sections: list[dict],
        facts: list[dict],
        guardrails: list[dict],
    ) -> ContentCounts: ...

    @abstractmethod
    async def count_content(self, document_id: str) -> ContentCounts: ...

    @abstractmethod
    async def all_guardrails(self) -> list[KnowledgeGuardrail]: ...

    @abstractmethod
    async def candidate_facts(
        self, tokens: list[str], limit: int, categories: set[str] | None = None
    ) -> list[KnowledgeFact]: ...

    @abstractmethod
    async def candidate_sections(self, tokens: list[str], limit: int) -> list[KnowledgeSection]: ...

    @abstractmethod
    async def facts_with_attribute(self, attribute: str) -> list[KnowledgeFact]: ...


class SqlKnowledgeRepository(KnowledgeRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_document(self) -> KnowledgeDocument | None:
        """The loaded corpus, or `None` if nothing has been ingested.

        This is a single-document corpus by design — one source PDF, one set
        of facts — so the most recent row is the live one and there is no
        "which document did you mean" question to answer at query time. A
        future multi-corpus system would need a real selection rule here, and
        would want it chosen deliberately rather than inherited from a sort.
        """
        result = await self._session.execute(
            select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def upsert_document(self, slug: str, title: str, source_file: str, sha256: str) -> KnowledgeDocument:
        """Create or update the document row, keyed on slug.

        Re-ingesting a revised edition updates the provenance in place rather
        than adding a second corpus, so every fact, section and guardrail
        keeps pointing at the one document that is actually loaded.
        """
        result = await self._session.execute(select(KnowledgeDocument).where(KnowledgeDocument.slug == slug))
        document = result.scalar_one_or_none()
        if document is None:
            document = KnowledgeDocument(slug=slug, title=title, source_file=source_file, source_sha256=sha256)
            self._session.add(document)
        else:
            document.title = title
            document.source_file = source_file
            document.source_sha256 = sha256
        await self._session.flush()
        return document

    async def replace_content(
        self,
        document_id: str,
        sections: list[dict],
        facts: list[dict],
        guardrails: list[dict],
    ) -> ContentCounts:
        """Swap a document's whole content for a freshly parsed set.

        Delete-then-insert rather than upsert, matching
        `SqlChunkRepository.replace_chunks`: an ingest is a rare,
        operator-triggered action, and "the old content is gone and the new
        content is in" is a far easier invariant to reason about than a merge
        that has to decide what a section that no longer exists should do.
        The caller commits, so the swap is atomic to a reader.
        """
        await self._session.execute(
            delete(KnowledgeGuardrail).where(KnowledgeGuardrail.document_id == document_id)
        )
        await self._session.execute(delete(KnowledgeFact).where(KnowledgeFact.document_id == document_id))
        await self._session.execute(delete(KnowledgeSection).where(KnowledgeSection.document_id == document_id))

        if sections:
            self._session.add_all(
                [
                    KnowledgeSection(
                        document_id=document_id,
                        number=row["number"],
                        sort_key=row["sort_key"],
                        title=row["title"],
                        body=row["body"],
                        search_text=row["search_text"],
                        char_count=row["char_count"],
                    )
                    for row in sections
                ]
            )
        if facts:
            self._session.add_all(
                [
                    KnowledgeFact(
                        document_id=document_id,
                        section_number=row["section_number"],
                        category=row["category"],
                        entity=row["entity"],
                        attribute=row["attribute"],
                        value=row["value"],
                        detail=row["detail"],
                        ordinal=row["ordinal"],
                        search_text=row["search_text"],
                        char_count=row["char_count"],
                    )
                    for row in facts
                ]
            )
        if guardrails:
            self._session.add_all(
                [
                    KnowledgeGuardrail(
                        document_id=document_id,
                        rule_number=row["rule_number"],
                        title=row["title"],
                        body=row["body"],
                        search_text=row["search_text"],
                        char_count=row["char_count"],
                    )
                    for row in guardrails
                ]
            )
        await self._session.flush()
        return ContentCounts(sections=len(sections), facts=len(facts), guardrails=len(guardrails))

    async def count_content(self, document_id: str) -> ContentCounts:
        async def _count(model: type[sa.orm.DeclaredBase]) -> int:
            result = await self._session.execute(
                select(func.count()).select_from(model).where(model.document_id == document_id)  # type: ignore[attr-defined]
            )
            return int(result.scalar_one())

        return ContentCounts(
            sections=await _count(KnowledgeSection),
            facts=await _count(KnowledgeFact),
            guardrails=await _count(KnowledgeGuardrail),
        )

    async def all_guardrails(self) -> list[KnowledgeGuardrail]:
        """Every guardrail, unconditionally.

        Never filtered, never ranked, never top-k'd. A rule the assistant did
        not read is a rule it cannot obey, and the failures these prevent —
        inventing a bank account, renaming the Chairperson, describing an
        ambulance booking form that does not exist — are exactly the kind
        that sound plausible when missing. There are seven rows; loading them
        whole costs one indexed query and no ranking.
        """
        document = await self.get_document()
        if document is None:
            raise KnowledgeNotIngested("The knowledge base has not been ingested yet.")
        result = await self._session.execute(
            select(KnowledgeGuardrail)
            .where(KnowledgeGuardrail.document_id == document.id)
            .order_by(KnowledgeGuardrail.rule_number)
        )
        return list(result.scalars().all())

    async def candidate_facts(
        self, tokens: list[str], limit: int, categories: set[str] | None = None
    ) -> list[KnowledgeFact]:
        if not tokens:
            return []
        # Over-fetch relative to `limit` because scoring happens afterwards in
        # Python: the SQL narrows the corpus, the ranking decides. The ceiling
        # keeps a query that matches the whole table from pulling all of it
        # into memory on a corpus that has outgrown this design.
        statement = select(KnowledgeFact).where(_token_filter(KnowledgeFact.search_text, tokens))
        if categories:
            statement = statement.where(KnowledgeFact.category.in_(categories))
        statement = statement.limit(max(limit * 8, 200))
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def candidate_sections(self, tokens: list[str], limit: int) -> list[KnowledgeSection]:
        if not tokens:
            return []
        statement = (
            select(KnowledgeSection)
            .where(_token_filter(KnowledgeSection.search_text, tokens))
            .order_by(KnowledgeSection.sort_key)
            .limit(max(limit * 4, 100))
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def facts_with_attribute(self, attribute: str) -> list[KnowledgeFact]:
        """Every fact whose attribute ends with *attribute*, across the whole corpus.

        This is the attribute-lookup path: callers pass a short keyword such as
        ``"phone"`` and the query matches any stored attribute that ends with
        that word (e.g. ``"dean_s_office_phone"``).  Slugified attribute names
        are ``[a-z0-9_]``, so there is no escaping risk in the LIKE pattern.
        The match is case-insensitive for resilience, though in practice all
        stored attributes are already lower-case slugs.
        """
        document = await self.get_document()
        if document is None:
            raise KnowledgeNotIngested("The knowledge base has not been ingested yet.")
        result = await self._session.execute(
            select(KnowledgeFact)
            .where(
                KnowledgeFact.document_id == document.id,
                KnowledgeFact.attribute.ilike(f"%{attribute}"),
            )
            .order_by(KnowledgeFact.entity)
        )
        return list(result.scalars().all())

