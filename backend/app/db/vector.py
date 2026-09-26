"""Dual-dialect vector column type.

pgvector's `Vector` type only exists on PostgreSQL, but the test suite
builds the entire schema on SQLite (`Base.metadata.create_all`). Rather
than excluding the RAG tables from tests, the column renders as
`vector(384)` on PostgreSQL and plain `TEXT` everywhere else, so the same
model definitions load on both.

This uses `with_variant` rather than a hand-rolled `TypeDecorator`
deliberately. A TypeDecorator has to declare one static `impl`, and
SQLAlchemy derives the column comparator from *that*, not from whatever
`load_dialect_impl` returns for a given dialect. So wrapping pgvector's
type in one silently drops the comparator that provides
`embedding.cosine_distance(...)`, and the failure is an AttributeError
raised from inside a query — which no SQLite-only test can catch, because
the operator is never compiled there.

On SQLite the column is text and similarity search is genuinely
unavailable. `ChunkRepository.similarity_search` refuses rather than
silently returning nothing, so a test can never mistake "unsupported" for
"no matches".
"""
from __future__ import annotations

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

#: Width of every embedding column in the schema. Kept as a constant
#: because the model, the migration, and Settings.embedding_dimensions all
#: have to agree; see docs/DEPLOYMENT.md for the re-embed procedure when
#: this changes.
VECTOR_DIMENSIONS = 384

#: The column type to use in models. `vector(384)` on PostgreSQL, `TEXT`
#: on anything else.
VECTOR = Vector(VECTOR_DIMENSIONS).with_variant(sa.Text(), "sqlite")
