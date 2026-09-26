"""The DeKUT student-services knowledge base, stored for retrieval.

Why this is relational and not embedded
---------------------------------------
The sibling `past_paper_chunks` table is vector-indexed, and copying that
shape here would be the obvious move. It is also the wrong one, and the
deployment is what settles it.

This corpus is roughly 200 rows of *short, atomic, factual* statements: a
Dean's telephone number, an office e-mail, the name of a Students' Council
office holder, one step of a payment workflow. Two properties follow, and
both point away from embeddings:

1. The dominant question is an exact lookup. "What is the School of Science
   Dean's e-mail?" wants `dean-sos@dkut.ac.ke`. A lexical match returns that
   exactly; cosine similarity over 384 dimensions reliably does not, because
   a phone number and an e-mail are not semantically close to anything, they
   are simply strings. Putting the value in an indexed column makes the
   question a btree lookup instead of a ranking problem.
2. The corpus is small enough that a sequential scan is already
   sub-millisecond. A GIN index over 200 rows costs more to maintain on
   write than it saves on read, and `to_tsvector`/dictionary configuration
   would have to be maintained in a migration as well.

The cost side is decisive. This deployment is a single Oracle A1.Flex with
12 GB of RAM shared across four containers, two vCPUs, and an ARM target
(the CI matrix builds linux/arm64 specifically to prove the ONNX model
downloads there). `docker-compose.yml` already caps the backend at 1536 MB
*because* it hosts the embedding model. Adding a second retrieval path
would mean a ~90 MB model download, several hundred MB of resident memory
and CPU-bound inference on the critical path of every student chat turn —
paid on every question, to serve 200 rows, and on a box with the headroom
already explicitly rationed. `EMBEDDING_ENABLED` and `RAG_ENABLED` are
consequently unset in the live `.env`, so that path is not even running.

So: structured columns for exact lookups, a precomputed `search_text` blob
for lexical matching, and deterministic scoring in Python. No model, no
extension, no inference, no per-query cost. The trade-off is stated plainly:
a question phrased entirely in synonyms the document never uses ("how do I
bail out my fees?") matches weakly. That is a better failure than a
confident wrong phone number, and it is fixed by adding vocabulary, not by
adding a model. If the corpus ever grows into the hundreds of thousands of
rows, add pg_trgm or a tsvector column in a migration — the schema is not
what would have to change.

Shape of the data
-----------------
`KnowledgeDocument` holds provenance for the source file.
`KnowledgeSection` holds one numbered section's prose, and is what a
citation names.
`KnowledgeFact` holds one atomic, attributable claim. It is the table that
answers exact questions.
`KnowledgeGuardrail` holds the document's "do not invent" rules. They are
deliberately *not* facts: a guardrail has to be loaded unconditionally into
the assistant's context, not ranked against a query, because the whole
failure it prevents is a plausible-sounding answer the retrieval never
surfaced.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid

#: Sort weight per heading level. Section numbers are "1", "1.1", "13.1", so
#: they are not directly comparable as integers ("13" > "1.1" but "1" <
#: "1.1"). Multiplying each level by a fixed power of ten keeps the numeric
#: ordering identical to the document's own, which is what `ORDER BY` on
#: this column produces.
_SORT_STRIDE = 10_000


def section_sort_key(number: str) -> int:
    """Map a section number like "13.1" to a monotonically ordered integer.

    Two levels is all this document uses, and one extra digit of headroom is
    kept so a future "13.1.2" sorts between its neighbours rather than
    colliding with them.
    """
    parts = [p for p in number.split(".") if p.isdigit()]
    key = 0
    for depth, part in enumerate(parts[:3]):
        key += int(part) * (_SORT_STRIDE ** (2 - depth))
    return key


class KnowledgeDocument(Base, TimestampMixin):
    """One ingested source file, and the provenance needed to re-ingest it.

    `sha256` is what makes re-ingestion idempotent in the way that matters:
    re-running the importer against the same bytes is a no-op, while a
    revised edition is recognised as different content and re-ingested
    rather than silently merged into stale rows.
    """

    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    # Stable machine key for the corpus ("dekut-student-services"), not the
    # filename, so the ingest command can name a document that does not
    # exist yet.
    slug: Mapped[str] = mapped_column(sa.String(80), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    source_file: Mapped[str] = mapped_column(sa.String(500), nullable=False, default="")
    source_sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    # Denormalised counts, so an operator can see whether an ingest actually
    # produced content without running a COUNT over three tables.
    section_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    fact_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    guardrail_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)


class KnowledgeSection(Base, TimestampMixin):
    """One numbered section of the document, kept whole.

    Sections are the citation unit. Storing the prose of a section rather
    than arbitrary fixed-size windows means a quote can name the section it
    came from ("DeKUT Medical Centre Services, §24") and that number can be
    checked by opening the source document, which a character offset into an
    arbitrary window could never support.
    """

    __tablename__ = "knowledge_sections"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "1" for a top-level heading, "1.1" for a subsection.
    number: Mapped[str] = mapped_column(sa.String(12), nullable=False)
    sort_key: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(sa.String(300), nullable=False, default="")
    body: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    # Lowercased, punctuation-stripped title + body. Precomputed at write
    # time in Python so the matching expression is identical on PostgreSQL
    # and SQLite, which is what lets the test suite exercise the real query
    # path rather than a stand-in.
    search_text: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    char_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    __table_args__ = (
        sa.UniqueConstraint("document_id", "number", name="uq_kb_sections_document_number"),
        sa.Index("ix_kb_sections_document_sort", "document_id", "sort_key"),
    )


class KnowledgeFact(Base, TimestampMixin):
    """One atomic, attributable claim from the knowledge base.

    The generic (category, entity, attribute, value) shape is what makes
    exact questions cheap. "Who do I email about a pharmacy/physiology
    result?" becomes `attribute = 'email'` filtered on the entity, answered
    from a btree index with no ranking, no model and no scan of prose.

    `ordinal` is 0 rather than NULL for items that are not part of an
    ordered list, because a NULL in a unique constraint does not conflict
    with another NULL in PostgreSQL — the uniqueness guarantee that makes
    re-ingestion idempotent would silently not apply to exactly the rows
    that carry no ordering, which is most of them.

    `value` is Text, not a short string, because the same column holds an
    e-mail, a phone number, a person's name and a full sentence of policy
    depending on the category. Shortening it would truncate exactly the
    long, valuable values.
    """

    __tablename__ = "knowledge_facts"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalised from the parent section so a fact can be cited without
    # joining, and so a fact whose section is reworded still points at the
    # right place.
    section_number: Mapped[str] = mapped_column(sa.String(12), nullable=False, default="")
    category: Mapped[str] = mapped_column(sa.String(40), nullable=False, default="general")
    entity: Mapped[str] = mapped_column(sa.String(300), nullable=False, default="")
    attribute: Mapped[str] = mapped_column(sa.String(80), nullable=False, default="")
    value: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    # Supporting prose: a step's description, a leader's remit, a rule's
    # detail. Kept off `value` so an exact lookup returns the atom without
    # dragging a paragraph of context into the result set.
    detail: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    ordinal: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    search_text: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    char_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    __table_args__ = (
        sa.UniqueConstraint(
            "document_id",
            "category",
            "entity",
            "attribute",
            "ordinal",
            name="uq_kb_facts_identity",
        ),
        sa.Index("ix_kb_facts_document_category", "document_id", "category"),
        sa.Index("ix_kb_facts_entity", "entity"),
    )


class KnowledgeGuardrail(Base, TimestampMixin):
    """A "do not invent this" rule the assistant must always be given.

    Kept apart from `KnowledgeFact` because the access pattern is different
    in kind. A fact is *ranked* against a query and may legitimately lose.
    A guardrail is *precondition* knowledge: the document's rules exist
    because the failure they prevent is a confident, plausible answer —
    inventing a bank account, renaming the Students' Council Chairperson to
    "President", describing an ambulance booking form that does not exist.
    If such a rule can go unretrieved, it cannot do its job, so these rows
    are loaded whole and unconditionally, and never compete for a top-k
    slot.
    """

    __tablename__ = "knowledge_guardrails"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    title: Mapped[str] = mapped_column(sa.String(300), nullable=False, default="")
    body: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    search_text: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    char_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    __table_args__ = (
        sa.UniqueConstraint("document_id", "rule_number", name="uq_kb_guardrails_document_rule"),
    )
