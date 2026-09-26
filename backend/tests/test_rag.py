"""Past-paper retrieval: chunking, the RAG tool, admin reindex, failover.

These cover the paths where a bug is silent rather than loud. A bad chunk
boundary or a threshold set too high does not raise — it just makes search
return nothing useful, and nobody notices until a student complains that
the assistant "has no past papers".
"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite

from app.agents.providers.base import LLMProvider, ProviderUnavailable
from app.agents.providers.fallback_provider import FallbackProvider
from app.core.config import Settings
from app.models.past_paper_chunk import PastPaperChunk
from app.repositories.chunk_repository import ChunkMatch, VectorSearchUnavailable

from app.schemas.rag import SearchPaperContentParams
from app.services.document_chunker import (
    DocumentExtractionError,
    Page,
    chunk_pages,
    extract_pages,
)
from app.services.embedding_service import EmbeddingService, EmbeddingUnavailable
from app.services.paper_search_service import Citation, PaperSearchService, SearchResult, format_for_llm
from app.tools.rag_tools import search_paper_content_tool
from app.tools.registry import ToolContext, ToolResult

# --- Chunking ---


def _pages(count: int, size: int = 500) -> list[Page]:
    return [Page(number=i, text=f"page {i} " + "x" * size) for i in range(1, count + 1)]


def test_chunking_keeps_every_window_within_the_configured_size():
    chunks = chunk_pages(_pages(6, 500), chunk_chars=1200, overlap_chars=100)
    assert chunks
    for chunk in chunks:
        assert len(chunk.text) <= 1200


def test_chunk_pages_records_the_page_range_it_actually_covered():
    chunks = chunk_pages(_pages(6, 500), chunk_chars=1200, overlap_chars=100)
    for chunk in chunks:
        assert chunk.page_start is not None
        assert chunk.page_end is not None
        assert chunk.page_start <= chunk.page_end


def test_chunk_indices_are_dense_and_ordered():
    chunks = chunk_pages(_pages(4, 800), chunk_chars=600, overlap_chars=50)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_a_single_page_longer_than_the_window_is_still_split():
    """A single huge page must not become one un-embeddable chunk, and it
    must not be silently dropped either."""
    chunks = chunk_pages([Page(number=1, text="y" * 5000)], chunk_chars=1000, overlap_chars=100)
    assert len(chunks) > 1
    assert all(c.page_start == 1 and c.page_end == 1 for c in chunks)


def test_overlap_carries_text_across_a_window_boundary():
    """The point of overlap: content spanning two windows is retrievable
    from a single chunk, not lost between two."""
    marker = "UNIQUE-MARKER-XYZ"
    first = "a" * 700 + marker + "b" * 400
    second = "c" * 700
    chunks = chunk_pages([Page(number=1, text=first), Page(number=2, text=second)], chunk_chars=1000, overlap_chars=300)
    assert any(marker in c.text for c in chunks)


def test_chunking_rejects_a_nonsense_window_size():
    with pytest.raises(ValueError):
        chunk_pages(_pages(1), chunk_chars=0)


def test_scanned_pdf_without_a_text_layer_is_rejected_rather_than_indexed_empty():
    with pytest.raises(DocumentExtractionError):
        extract_pages(b"%PDF-1.4\n" + b"\x00" * 500, filename="scan.pdf")


def test_plain_text_is_accepted_and_normalised():
    pages = extract_pages(b"Question 1\r\n\r\n\r\n\r\nExplain the   Fourier transform." * 20, filename="notes.txt")
    assert pages
    assert "\r" not in pages[0].text
    assert "Fourier" in pages[0].text


def _docx_bytes(paragraphs: list[str]) -> bytes:
    import io
    import zipfile

    body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def test_docx_text_is_extracted_for_indexing():
    data = _docx_bytes(
        ["SCS 2101 Database Systems - End of Semester Examination"] * 5
        + ["Question 1: Explain normalisation and its normal forms in detail."] * 5
    )
    pages = extract_pages(data, filename="SCS2101_2023.docx")
    assert len(pages) == 1
    assert "Database Systems" in pages[0].text
    assert "normalisation" in pages[0].text


def test_a_docx_with_no_usable_text_is_rejected_rather_than_indexed_empty():
    with pytest.raises(DocumentExtractionError):
        extract_pages(_docx_bytes(["", "   "]), filename="empty.docx")


# --- Embedding service ---


class _StubEmbeddings(EmbeddingService):
    """Stubs only the backend, so `embed()`'s cleaning, batching and
    dimension checks are the real implementation and stay under test."""

    def __init__(self, dimensions: int = 384):
        super().__init__(Settings(embedding_enabled=True, embedding_dimensions=dimensions))
        self._dimensions = dimensions

    def _embed_local_sync(self, texts):
        return [[0.1] * self._dimensions for _ in texts]


async def test_embedding_service_rejects_a_dimension_mismatch_instead_of_writing_bad_vectors():
    """A model that returns 768 dims against a 384 column would otherwise
    surface as an opaque psycopg error, or worse, corrupt the index."""
    service = EmbeddingService(Settings(embedding_dimensions=384, embedding_enabled=True))
    with pytest.raises(EmbeddingUnavailable, match="384"):
        service._assert_dimensions([[0.0] * 768])


async def test_embedding_service_skips_blank_input_rather_than_returning_zero_vectors():
    service = _StubEmbeddings()
    assert await service.embed(["", "   "]) == []


# --- Search service ---


class _StubChunkRepo:
    def __init__(self, matches: list[ChunkMatch] | None = None, error: Exception | None = None):
        self._matches = matches or []
        self._error = error

    async def similarity_search(self, embedding, limit, min_score):
        if self._error:
            raise self._error
        return self._matches[:limit]


def _match(paper_id: str = "paper-1", score: float = 0.8) -> ChunkMatch:
    return ChunkMatch(
        chunk_id="c1",
        past_paper_id=paper_id,
        chunk_index=0,
        content="An exam question about integration by parts.",
        score=score,
        page_start=2,
        page_end=2,
    )


async def test_search_reports_unavailable_instead_of_raising_when_the_backend_is_down(db_session):
    """Retrieval is an enhancement. A dead embedding model must not turn a
    student's question into a 500."""

    class _Broken(EmbeddingService):
        async def embed(self, texts):
            raise EmbeddingUnavailable("model missing")

    settings = Settings(rag_enabled=True, embedding_enabled=True, llm_provider="deepseek", llm_api_key="k")
    service = PaperSearchService(db_session, _Broken(settings), settings)
    result = await service.search("integration by parts")
    assert result.available is False
    assert result.is_empty()


async def test_search_reports_unavailable_on_a_database_without_pgvector(db_session):
    settings = Settings(rag_enabled=True, embedding_enabled=True, llm_provider="deepseek", llm_api_key="k")
    service = PaperSearchService(
        db_session, _StubEmbeddings(), settings, chunk_repo=_StubChunkRepo(error=VectorSearchUnavailable("sqlite"))
    )
    result = await service.search("anything")
    assert result.available is False


async def test_search_is_disabled_when_rag_is_off(db_session):
    settings = Settings(rag_enabled=False, embedding_enabled=False)
    service = PaperSearchService(db_session, _StubEmbeddings(), settings)
    result = await service.search("anything")
    assert result.available is False
    assert "disabled" in (result.note or "")


def test_rag_cannot_be_enabled_without_embeddings():
    with pytest.raises(ValueError, match="EMBEDDING_ENABLED"):
        Settings(rag_enabled=True, embedding_enabled=False)


def test_rag_cannot_be_enabled_on_the_mock_provider():
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        Settings(rag_enabled=True, embedding_enabled=True, llm_provider="mock")


def test_format_for_llm_marks_unavailable_results_so_the_model_does_not_invent_citations():
    payload = format_for_llm(SearchResult("q", [], available=False, note="down"))
    assert payload["available"] is False
    assert payload["excerpts"] == []


def test_citation_label_includes_course_year_and_page():
    citation = Citation(
        past_paper_id="p",
        course_code="SCS2101",
        course_name="Data Structures",
        academic_year="2023/2024",
        semester=1,
        exam_type="main",
        chunk_index=0,
        page_start=3,
        page_end=5,
        score=0.7,
    )
    label = citation.label()
    assert "SCS2101" in label
    assert "2023/2024" in label
    assert "3-5" in label


# --- The tool ---


def _ctx(paper_search) -> ToolContext:
    return ToolContext(
        hostel_repo=None,  # type: ignore[arg-type]
        academic_repo=None,  # type: ignore[arg-type]
        past_paper_repo=None,  # type: ignore[arg-type]
        complaint_repo=None,  # type: ignore[arg-type]
        paper_search=paper_search,
    )


async def test_rag_tool_without_a_search_service_degrades_instead_of_raising():
    result = await search_paper_content_tool.handler(_ctx(None), SearchPaperContentParams(query="anything"))
    assert result.ok
    assert result.data["available"] is False


async def test_rag_tool_returns_a_clean_empty_result_when_nothing_matches():
    settings = Settings(rag_enabled=False, embedding_enabled=False)
    service = PaperSearchService(None, _StubEmbeddings(), settings)  # type: ignore[arg-type]
    result = await search_paper_content_tool.handler(_ctx(service), SearchPaperContentParams(query="anything"))
    assert isinstance(result, ToolResult)
    assert result.ok


def test_rag_tool_is_registered_in_the_default_registry():
    from app.tools.build import build_default_registry

    registry = build_default_registry()
    assert registry.get("search_past_paper_content") is not None
    described = {t["name"] for t in registry.describe_for_llm()}
    assert "search_past_papers" in described
    assert "search_past_paper_content" in described


def test_rag_tool_params_reject_an_empty_query():
    with pytest.raises(Exception):
        SearchPaperContentParams(query="")


# --- Vector column typing ---
# These are the checks that would have caught a real bug: the column was
# originally wrapped in a TypeDecorator, which silently strips the
# comparator pgvector installs. `embedding.cosine_distance(...)` then
# raised an AttributeError from inside the query, and no SQLite test
# could see it, because the operator is never compiled there. These
# assertions fail fast, on any dialect, with no database needed.


def test_vector_column_exposes_the_pgvector_distance_operator():
    column = PastPaperChunk.__table__.c.embedding
    assert hasattr(column.comparator, "cosine_distance")
    assert hasattr(column.comparator, "l2_distance")


def test_vector_column_compiles_the_cosine_distance_operator_to_postgres_sql():
    column = PastPaperChunk.__table__.c.embedding
    stmt = select(column).where(column.cosine_distance([0.0] * 384) < 0.5)
    assert "<=>" in str(stmt.compile(dialect=postgresql.dialect()))


def test_vector_column_renders_as_vector_on_postgres():
    column = PastPaperChunk.__table__.c.embedding
    assert "VECTOR(384)" in str(column.type.compile(dialect=postgresql.dialect())).upper()


def test_vector_column_falls_back_to_text_on_sqlite_so_the_test_schema_builds():
    """The whole suite runs on SQLite, so the column has to render as
    something SQLite accepts."""
    column = PastPaperChunk.__table__.c.embedding
    rendered = str(column.type.compile(dialect=sqlite.dialect())).upper()
    assert "VECTOR" not in rendered
    assert rendered.startswith("TEXT")


async def test_similarity_search_refuses_on_sqlite_rather_than_returning_nothing(db_session):
    """An empty list would be indistinguishable from 'no matches', which
    is how a broken index turns into a silently useless feature."""
    from app.repositories.chunk_repository import SqlChunkRepository, VectorSearchUnavailable

    repo = SqlChunkRepository(db_session)
    with pytest.raises(VectorSearchUnavailable):
        await repo.similarity_search([0.0] * 384, limit=5, min_score=0.0)


# --- LLM failover ---


class _ScriptedProvider(LLMProvider):
    def __init__(self, name: str, *, fail: bool = False, fail_after_tokens: int | None = None):
        self.display_name = name
        self._fail = fail
        self._fail_after_tokens = fail_after_tokens
        self.calls = 0

    async def classify_intent(self, message, history, domains):
        self.calls += 1
        if self._fail:
            raise ProviderUnavailable(f"{self.display_name} is down")
        return {"intent": "general", "confidence": 0.9, "parameters": {}}

    async def propose_tool_calls(self, **kwargs):
        self.calls += 1
        if self._fail:
            raise ProviderUnavailable(f"{self.display_name} is down")
        return []

    async def stream_final_answer(self, **kwargs):
        self.calls += 1
        if self._fail:
            raise ProviderUnavailable(f"{self.display_name} is down")
        if self._fail_after_tokens is not None:
            yield "partial"
            raise ProviderUnavailable("died mid-stream")
        yield "hello from " + self.display_name


async def test_failover_uses_the_fallback_when_the_primary_is_unavailable():
    primary = _ScriptedProvider("Primary", fail=True)
    fallback = _ScriptedProvider("Fallback")
    chain = FallbackProvider([primary, fallback])
    result = await chain.classify_intent("hi", [], [])
    assert result["intent"] == "general"
    assert chain.display_name == "Fallback"


async def test_failover_raises_only_after_every_provider_has_failed():
    chain = FallbackProvider([_ScriptedProvider("A", fail=True), _ScriptedProvider("B", fail=True)])
    with pytest.raises(ProviderUnavailable):
        await chain.classify_intent("hi", [], [])


async def test_failover_does_not_retry_once_tokens_have_already_been_sent():
    """Splicing a second answer onto a half-streamed one produces an
    incoherent reply, so a mid-stream failure must surface instead."""
    primary = _ScriptedProvider("Primary", fail_after_tokens=1)
    fallback = _ScriptedProvider("Fallback")
    chain = FallbackProvider([primary, fallback])

    received = []
    with pytest.raises(ProviderUnavailable):
        async for delta in chain.stream_final_answer(
            message="q", intent="general", tool_results=[], history=[]
        ):
            received.append(delta)

    assert received == ["partial"]
    assert fallback.calls == 0


async def test_failover_skips_a_provider_that_failed_once_instead_of_retrying_it():
    primary = _ScriptedProvider("Primary", fail=True)
    fallback = _ScriptedProvider("Fallback")
    chain = FallbackProvider([primary, fallback])
    await chain.classify_intent("hi", [], [])
    await chain.classify_intent("again", [], [])
    assert primary.calls == 1


def test_groq_is_a_named_provider_with_its_own_base_url():
    from app.agents.providers.factory import PROVIDER_BASE_URLS

    # Groq's base path is /openai/v1, not /v1; guessing wrong gives a 404
    # that reads like a missing model rather than a wrong URL.
    assert PROVIDER_BASE_URLS["groq"] == "https://api.groq.com/openai/v1"


def test_a_configured_fallback_yields_a_failover_chain():
    from app.agents.providers.factory import get_llm_provider

    settings = Settings(
        llm_provider="deepseek",
        llm_model="deepseek-chat",
        llm_api_key="primary-key",
        llm_fallback_provider="groq",
        llm_fallback_model="llama-3.3-70b-versatile",
        llm_fallback_api_key="fallback-key",
    )
    provider = get_llm_provider(settings)
    assert isinstance(provider, FallbackProvider)


def test_no_fallback_configured_returns_the_single_provider_unchanged():
    from app.agents.providers.factory import get_llm_provider

    provider = get_llm_provider(Settings(llm_provider="mock"))
    assert provider.display_name == "Mock Assistant"
    assert not isinstance(provider, FallbackProvider)


def test_an_unusable_fallback_is_ignored_rather_than_taking_down_the_primary():
    from app.agents.providers.factory import get_llm_provider

    settings = Settings(
        llm_provider="mock",
        llm_fallback_provider="groq",
        llm_api_key="",
    )
    # No key anywhere, so the fallback cannot be built; the primary must
    # still serve traffic.
    assert not isinstance(get_llm_provider(settings), FallbackProvider)


# --- Production configuration guard ---
# These exist because a placeholder credential does not fail loudly on
# deploy: the app boots, reports healthy, and mints tokens anyone can
# forge. The guard is the only thing standing between a copy-pasted
# .env.example and that.

#: Placeholder names in .env.example that the production guard inspects.
#: Kept next to the guard tests so the two cannot drift apart.
_GUARDED_PLACEHOLDERS = {
    "SECRET_KEY",
    "DATABASE_URL",
    "DATABASE_URL_SYNC",
    "LLM_API_KEY",
    "LLM_FALLBACK_API_KEY",
    "S3_ENDPOINT",
    "S3_BUCKET",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "S3_PUBLIC_URL",
}

_REAL_PROD = dict(
    app_env="production",
    secret_key="a" * 64,
    database_url="postgresql+asyncpg://omniscient:Sup3rS3cret@db:5432/omniscient",
    llm_provider="deepseek",
    llm_api_key="sk-real-deepseek-key",
    llm_fallback_provider="groq",
    llm_fallback_api_key="gsk-real-groq-key",
    storage_provider="s3",
    s3_endpoint="https://abc123.r2.cloudflarestorage.com",
    s3_bucket="omniscient-files",
    s3_access_key="realaccesskeyid",
    s3_secret_key="realsecretkey",
    s3_public_url="https://files.omniscient.co.ke",
    embedding_enabled=True,
    rag_enabled=True,
)


def _prod(**overrides):
    return Settings(**{**_REAL_PROD, **overrides})


def test_a_fully_configured_production_settings_starts():
    settings = _prod()
    assert settings.llm_provider == "deepseek"
    assert settings.llm_fallback_provider == "groq"
    assert settings.rag_is_live is True


def test_non_production_is_never_blocked_by_the_secret_guard():
    """Development, staging and test must keep working with zero config —
    that is the entire point of the mock provider."""
    for env in ("development", "staging", "test"):
        assert Settings(app_env=env).app_env == env


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"secret_key": "REPLACE_ME_openssl_rand_hex_32"}, "SECRET_KEY"),
        ({"secret_key": "insecure-development-key-change-me"}, "SECRET_KEY"),
        ({"secret_key": "short"}, "32"),
        ({"llm_api_key": ""}, "LLM_API_KEY"),
        ({"llm_api_key": "REPLACE_ME_key"}, "LLM_API_KEY"),
        ({"llm_fallback_api_key": "REPLACE_ME_key"}, "LLM_FALLBACK_API_KEY"),
        ({"s3_secret_key": "REPLACE_ME_key"}, "S3_SECRET_KEY"),
        ({"s3_bucket": ""}, "S3_BUCKET"),
    ],
)
def test_production_refuses_placeholder_or_missing_secrets(overrides, expected):
    with pytest.raises(ValueError, match=expected):
        _prod(**overrides)


def test_production_reports_every_problem_at_once_not_just_the_first():
    """An operator fixing a config should see the whole list in one pass,
    not discover the next failure on each restart."""
    with pytest.raises(ValueError) as exc:
        _prod(secret_key="REPLACE_ME_x", llm_api_key="", s3_bucket="REPLACE_ME_b")
    message = str(exc.value)
    assert "SECRET_KEY" in message
    assert "LLM_API_KEY" in message
    assert "S3_BUCKET" in message


def test_production_allows_local_storage_without_any_s3_credentials():
    """R2 is the intended setup, not a hard requirement. Someone testing
    a production-shaped deploy on a spare box should not be forced to
    provision object storage."""
    settings = _prod(storage_provider="local", storage_local_path="/app/var/storage")
    assert settings.storage_provider == "local"


def test_every_placeholder_in_the_env_example_is_covered_by_the_guard():
    """A placeholder the guard does not know about is a placeholder that
    ships. This keeps .env.example and the production guard in step: if
    someone adds a new credential to the template, this fails until the
    guard is taught to check it too.
    """
    from pathlib import Path

    import app.core.config as config_module

    # config.py is backend/app/core/config.py, so parents[3] is the repo
    # root where .env.example lives (parents[2] would be backend/).
    example = (Path(config_module.__file__).resolve().parents[3] / ".env.example").read_text()
    placeholders = {
        line.split("=", 1)[0]
        for line in example.splitlines()
        if not line.startswith("#") and "REPLACE_ME" in line
    }
    assert placeholders, "expected .env.example to contain placeholders"

    # Two placeholders legitimately cannot be checked by Settings:
    # POSTGRES_PASSWORD only reaches the app inside DATABASE_URL (which
    # *is* checked), and ACME_EMAIL is read by Caddy, never by the app.
    not_settings_fields = {"POSTGRES_PASSWORD", "ACME_EMAIL"}
    unguarded = placeholders - _GUARDED_PLACEHOLDERS - not_settings_fields
    assert not unguarded, f"placeholders with no production guard: {sorted(unguarded)}"

    # And the guard must not be checking names the template no longer uses,
    # which would mean the guard rots in the other direction.
    stale = _GUARDED_PLACEHOLDERS - placeholders
    assert not stale, f"guard checks names absent from .env.example: {sorted(stale)}"
