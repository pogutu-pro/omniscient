"""Central application configuration, sourced from environment variables.

Nothing here is a secret by default — see ../../../.env.example for the
documented list of variables an operator is expected to supply.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Where dotenv values are read from, relative to the process working
# directory. Overridable through the environment so it can be switched off
# entirely, which the test suite needs: `backend/.env` is a symlink to the
# repo-root `.env`, so without this a developer's local settings silently
# become the test environment. Set OMNISCIENT_ENV_FILE= (empty) to disable.
#
# Mutating `Settings.model_config["env_file"]` afterwards does NOT work on
# pydantic-settings 2.7.x — the dotenv source is built from the config
# captured at class-creation time — so the path has to be decided here.
_ENV_FILE = os.environ.get("OMNISCIENT_ENV_FILE", ".env")

# Markers that identify an unreplaced value from .env.example. Checked
# case-insensitively so REPLACE_ME, replace_me and a prose variant all
# count. The shipped default secret is matched separately because it does
# not carry the marker but is just as public.
_PLACEHOLDER_MARKERS = ("replace_me", "change-me", "changeme", "your-", "your_", "xxx", "<", "todo")


def _is_placeholder(value: str | None) -> bool:
    """True if a value is obviously still the template's placeholder.

    Only ever used to refuse a production start. False positives cost a
    startup error with a clear message; false negatives cost a deployment
    running on a public secret, so this errs towards suspicion.
    """
    if value is None:
        return True
    text = value.strip().lower()
    if not text:
        return True
    if text in {"insecure-development-key-change-me", "insecure-development-key"}:
        return True
    return any(marker in text for marker in _PLACEHOLDER_MARKERS)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # --- Application ---
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_url: str = "http://localhost:5173"
    api_url: str = "http://localhost:8000"
    secret_key: str = "insecure-development-key-change-me"
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
    # Matched in addition to cors_origins. Exists for hosts like Vercel that
    # mint a new preview-deployment URL per branch/PR, so those don't need
    # to be added to cors_origins by hand one at a time. Example:
    # ^https://omniscient(-[a-z0-9-]+)?\.vercel\.app$
    cors_origin_regex: str | None = None

    # --- Database ---
    database_url: str = "postgresql+asyncpg://omniscient:omniscient@localhost:5432/omniscient"
    database_url_sync: str = "postgresql+psycopg2://omniscient:omniscient@localhost:5432/omniscient"
    # Off by default (local Postgres in dev/CI doesn't need it). Set to
    # true for any managed Postgres that requires TLS - Neon, Supabase,
    # RDS, etc.
    database_ssl: bool = False

    # --- AI provider ---
    # "mock" needs no credentials and is the safe zero-config default.
    # "grok" (xAI) and "deepseek" are the intended real providers;
    # "openai", "anthropic" and "custom" (any other OpenAI-compatible
    # endpoint — Together, Mistral, a self-hosted vLLM/Ollama server, ...)
    # are drop-in alternatives. Switching providers is a config change
    # only: see agents/providers/factory.py.
    #
    # The primary is paired with an optional fallback. When the primary
    # cannot serve a turn — outage, rate limit, quota, malformed reply —
    # the request is transparently retried against the fallback, and the
    # execution trace names whichever provider actually answered. Leaving
    # the fallback fields empty means a primary failure surfaces to the
    # student as an error instead, which is the right behaviour when
    # there is no second provider configured.
    llm_provider: Literal["mock", "anthropic", "openai", "grok", "deepseek", "groq", "custom"] = "mock"
    llm_model: str = "claude-sonnet-5"
    llm_api_key: str | None = None
    llm_api_base: str | None = None  # required for "custom"; optional override for the rest
    llm_temperature: float = 0.2
    llm_fallback_provider: Literal["", "anthropic", "openai", "grok", "deepseek", "groq", "custom"] = ""
    llm_fallback_model: str | None = None
    llm_fallback_api_key: str | None = None
    llm_fallback_api_base: str | None = None

    # --- Embeddings (RAG) ---
    # Vectors come from a self-hosted model rather than a hosted API: it is
    # free, never rate-limits, and cannot fail mid-deploy because someone
    # else's API had a bad afternoon.
    #
    # "local" runs ONNX inference in this process via fastembed — no extra
    # container and no multi-gigabyte PyTorch image, which matters on a
    # small VM. Inference is CPU-bound and always dispatched to a worker
    # thread so it cannot stall the event loop mid-stream.
    # "tei" instead calls a Hugging Face Text Embedding Inference sidecar
    # over HTTP, for when you outgrow a single box. Both back the same
    # `EmbeddingService` interface, so nothing else changes.
    #
    # The model and the vector column width are a matched pair — changing
    # EMBEDDING_DIMENSIONS requires a new migration to resize the column
    # and a full re-embed of every stored chunk, or retrieval silently
    # returns nonsense.
    embedding_enabled: bool = False
    embedding_backend: Literal["local", "tei"] = "local"
    embedding_base_url: str = "http://tei:8080"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimensions: int = 384
    embedding_batch_size: int = 32
    embedding_timeout_seconds: float = 60.0

    # --- Past-paper retrieval (RAG) ---
    # Requires embedding_enabled. Off by default so a fresh checkout and a
    # local `docker compose up` work without the embedding service running.
    rag_enabled: bool = False
    rag_top_k: int = 6
    # Cosine similarity floor. Below this the "match" is noise and the
    # model is better off saying it found nothing.
    rag_min_score: float = 0.25
    rag_chunk_chars: int = 1200
    rag_chunk_overlap_chars: int = 150

    # --- Rumia integration boundary ---
    # `rumia_db_mode` is the single switch for the whole boundary: disabled
    # means every domain repository uses its Mock* implementation against
    # Omniscient's own seeded data, with no outbound network calls at all.
    rumia_db_mode: Literal["disabled", "enabled"] = "disabled"
    # Base URL of Rumia's public, unauthenticated read API (its FastAPI
    # service). No credential is configured for this transport by design —
    # a transport that cannot authenticate cannot escalate its own access.
    rumia_api_base_url: str = "https://rumia.co.ke/api/v1"
    # Rumia is campus-scoped (a single shared schema, discriminated by
    # `campuses.slug`). "dekut" is Dedan Kimathi University of Technology.
    rumia_campus_slug: str = "dekut"
    rumia_timeout_seconds: float = 10.0
    # Listings change rarely and Rumia's feed is public, so a short TTL
    # cache keeps chat turns fast without ever holding a stale listing for
    # longer than a minute. 0 disables caching entirely.
    rumia_cache_ttl_seconds: int = 60
    # Rumia's public API does not expose a `verified` field, because Rumia
    # does not publish one: a listing that is live on Rumia has already been
    # through Rumia's own vetting. Treating `is_active = true` as verified
    # is therefore an assertion about Rumia's process, not a field read from
    # their API - hence a switch. Set false and nothing is claimed to be
    # verified that we cannot see, and a `verified_only` search returns
    # nothing rather than passing off unvetted listings.
    rumia_treat_active_as_verified: bool = True
    # Only consulted if rumia_db_mode were ever switched to a direct
    # Postgres transport. Unused by the API transport, and must never be
    # given Rumia's superuser credentials.
    rumia_database_url: str | None = None

    # --- Storage ---
    storage_provider: Literal["local", "s3"] = "local"
    storage_local_path: str = "./backend/var/storage"
    s3_endpoint: str | None = None
    s3_bucket: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str | None = None
    # Path-style addressing (`<endpoint>/<bucket>/<key>`) is required by
    # Cloudflare R2 and by most S3-compatible providers; virtual-host style
    # (bucket.endpoint) is AWS's default and produces DNS lookups R2 does
    # not answer. Overridable because a genuine AWS deployment wants
    # "virtual".
    s3_addressing_style: Literal["auto", "path", "virtual"] = "auto"
    # Public base URL objects are reachable at, e.g.
    # https://files.omniscient.co.ke. Set it when the bucket is served
    # through a custom domain or an r2.dev dev-domain; falls back to
    # <endpoint>/<bucket>/<key> when empty, which is only reachable for a
    # genuinely public bucket.
    s3_public_url: str | None = None

    # --- Rate limiting ---
    rate_limit_chat_per_minute: int = 20
    rate_limit_default_per_minute: int = 60

    @field_validator("llm_api_base")
    @classmethod
    def _require_api_base_for_custom_provider(cls, v: str | None, info) -> str | None:
        if info.data.get("llm_provider") == "custom" and not v:
            raise ValueError("LLM_API_BASE is required when LLM_PROVIDER=custom")
        return v

    @model_validator(mode="after")
    def _rag_requires_embeddings(self) -> Settings:
        # Retrieval embeds the student's question before it can search, so
        # RAG on its own could never answer anything. Failing at startup
        # beats a feature that silently returns zero results forever.
        if self.rag_enabled and not self.embedding_enabled:
            raise ValueError("RAG_ENABLED=true requires EMBEDDING_ENABLED=true")
        if self.rag_enabled and self.llm_provider == "mock":
            raise ValueError(
                "RAG_ENABLED=true requires a real LLM_PROVIDER; the mock provider cannot ground "
                "retrieved chunks in an answer"
            )
        return self

    @model_validator(mode="after")
    def _production_secrets_must_be_real(self) -> Settings:
        """Refuse to start production on a placeholder or missing secret.

        Every failure here is a deployment that would otherwise look
        healthy and be subtly, expensively broken: a known SECRET_KEY
        means anyone can mint a valid token for any student, and a
        placeholder password means the database is reachable by anyone who
        has read this repository.

        Only enforced when APP_ENV=production. Development, staging and
        test keep their zero-config defaults, which is the whole point of
        the mock provider and the local storage backend.
        """
        if self.app_env != "production":
            return self

        problems: list[str] = []

        # SECRET_KEY: the placeholder check matters more than the length
        # check. A short-but-random key is merely weak; the shipped
        # default is public, and anyone holding it can forge a token for
        # any student id.
        if _is_placeholder(self.secret_key):
            problems.append("SECRET_KEY is still the placeholder from .env.example")
        elif len(self.secret_key) < 32:
            problems.append(f"SECRET_KEY is {len(self.secret_key)} characters; use at least 32 (openssl rand -hex 32)")

        # The database password only reaches Settings inside the URL, so
        # that is where it has to be checked.
        if _is_placeholder(self.database_url):
            problems.append("DATABASE_URL still contains a placeholder password")

        # A named provider with no key authenticates as "mock with a
        # broken URL" at best, and 401s from the vendor at worst.
        if self.llm_provider != "mock" and not (self.llm_api_key or "").strip():
            problems.append(f"LLM_API_KEY is required when LLM_PROVIDER={self.llm_provider}")
        elif self.llm_api_key and _is_placeholder(self.llm_api_key):
            problems.append("LLM_API_KEY is still the placeholder from .env.example")

        if self.has_llm_fallback:
            if not (self.llm_fallback_api_key or self.llm_api_key or "").strip():
                problems.append(
                    f"LLM_FALLBACK_API_KEY is required when LLM_FALLBACK_PROVIDER={self.llm_fallback_provider}"
                )
            elif _is_placeholder(self.llm_fallback_api_key or self.llm_api_key or ""):
                problems.append("LLM_FALLBACK_API_KEY is still the placeholder from .env.example")

        # S3 is all-or-nothing: half-configured credentials produce a
        # backend that boots fine and then 500s on the first upload.
        if self.storage_provider == "s3":
            missing = [
                name
                for name, value in (
                    ("S3_ENDPOINT", self.s3_endpoint),
                    ("S3_BUCKET", self.s3_bucket),
                    ("S3_ACCESS_KEY", self.s3_access_key),
                    ("S3_SECRET_KEY", self.s3_secret_key),
                )
                if not (value or "").strip() or _is_placeholder(value or "")
            ]
            if missing:
                problems.append(f"STORAGE_PROVIDER=s3 but these are missing or placeholders: {', '.join(missing)}")

        if problems:
            raise ValueError(
                "Refusing to start in production with unusable configuration:\n  - "
                + "\n  - ".join(problems)
                + "\n\nEvery REPLACE_ME in .env.example must be replaced. See docs/LAUNCH_CHECKLIST.md."
            )
        return self

    @property
    def has_llm_fallback(self) -> bool:
        return bool(self.llm_fallback_provider)

    @property
    def rag_is_live(self) -> bool:
        """True only when retrieval can actually run end to end."""
        return self.rag_enabled and self.embedding_enabled

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
