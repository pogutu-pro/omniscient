"""add the DeKUT student-services knowledge base

Revision ID: a7c31e9b4d28
Revises: d2b7f40a9c15
Create Date: 2026-09-26 18:40:00.000000

The knowledge base is a 41-section institutional document (schools and
their contacts, DeKUTSO leadership, the fee-payment and registration
workflows, Medical Centre services, and a set of "do not invent this" rules)
that the assistant is expected to answer from rather than improvise.

It is stored relationally rather than as embedded chunks. The reasoning is
recorded in `app/models/knowledge.py` and depends on facts about this
deployment: the corpus is a few hundred rows of short atomic claims, the
target is a 12 GB / 2 vCPU ARM instance whose backend container is already
capped at 1536 MB to host the past-paper embedding model, and
`EMBEDDING_ENABLED`/`RAG_ENABLED` are unset in the live environment. A
second vector index would cost a model download, resident memory and
per-query CPU on the critical path of every chat turn, in exchange for
ranking ~200 rows that an indexed exact lookup answers outright.

Two consequences are visible in the schema:

- No `vector` column, so this revision creates no pgvector dependency and
  `alembic upgrade` stays valid on a PostgreSQL without the extension. The
  `CREATE EXTENSION` in b3f1c7a92d40 is untouched.
- `search_text` is a plain TEXT column holding lowercased, punctuation-
  stripped text, prepared by the application at write time. That keeps the
  matching expression identical on PostgreSQL and on the SQLite database the
  test suite builds, so the tests exercise the real query path rather than a
  dialect-specific stand-in. It is deliberately not a `tsvector` or a
  trigram index: at this table size a sequential scan is already
  sub-millisecond, and a GIN index would cost more to maintain on write than
  it saves on read.

The composite unique constraint on `knowledge_facts` is what makes
re-ingestion idempotent, and it is why `ordinal` is `NOT NULL DEFAULT 0`
rather than nullable: NULLs do not conflict with each other in a
PostgreSQL unique index, so a nullable ordinal would exempt the majority of
rows from the very guarantee the constraint exists to provide.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c31e9b4d28"
down_revision: Union[str, None] = "d2b7f40a9c15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("source_file", sa.String(length=500), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("section_count", sa.Integer(), nullable=False),
        sa.Column("fact_count", sa.Integer(), nullable=False),
        sa.Column("guardrail_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        # One row per corpus, so re-running the importer updates the existing
        # document instead of accumulating duplicates.
        sa.UniqueConstraint("slug", name="uq_kb_documents_slug"),
    )
    op.create_index("ix_kb_documents_source_sha256", "knowledge_documents", ["source_sha256"])

    op.create_table(
        "knowledge_sections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("number", sa.String(length=12), nullable=False),
        sa.Column("sort_key", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # CASCADE: a section whose document is gone is a section some future
        # search would happily quote with a citation pointing at nothing.
        sa.ForeignKeyConstraint(
            ["document_id"], ["knowledge_documents.id"], ondelete="CASCADE", name="fk_kb_sections_document"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "number", name="uq_kb_sections_document_number"),
    )
    # Reading a document in its own order is the only access pattern that
    # needs an index here.
    op.create_index("ix_kb_sections_document_sort", "knowledge_sections", ["document_id", "sort_key"])

    op.create_table(
        "knowledge_facts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("section_number", sa.String(length=12), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("entity", sa.String(length=300), nullable=False),
        sa.Column("attribute", sa.String(length=80), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["knowledge_documents.id"], ondelete="CASCADE", name="fk_kb_facts_document"
        ),
        sa.PrimaryKeyConstraint("id"),
        # The idempotency guarantee. The source document states some
        # contacts twice (once in the school section, once in the directory),
        # and this constraint is what collapses those into one row on
        # re-ingest instead of returning the phone number twice.
        sa.UniqueConstraint(
            "document_id", "category", "entity", "attribute", "ordinal", name="uq_kb_facts_identity"
        ),
    )
    op.create_index("ix_kb_facts_document_category", "knowledge_facts", ["document_id", "category"])
    op.create_index("ix_kb_facts_entity", "knowledge_facts", ["entity"])

    op.create_table(
        "knowledge_guardrails",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("rule_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["knowledge_documents.id"], ondelete="CASCADE", name="fk_kb_guardrails_document"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "rule_number", name="uq_kb_guardrails_document_rule"),
    )


def downgrade() -> None:
    op.drop_table("knowledge_guardrails")
    op.drop_index("ix_kb_facts_entity", table_name="knowledge_facts")
    op.drop_index("ix_kb_facts_document_category", table_name="knowledge_facts")
    op.drop_table("knowledge_facts")
    op.drop_index("ix_kb_sections_document_sort", table_name="knowledge_sections")
    op.drop_table("knowledge_sections")
    op.drop_index("ix_kb_documents_source_sha256", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
