"""Test-wide configuration, applied before anything imports the app.

The suite must not read the developer's real environment. Two things used
to leak in, both of which produced failures that looked like application
bugs:

- `backend/.env` is a symlink to the repo-root `.env`, and the app's
  Settings reads a dotenv file relative to the working directory (which
  is `backend/` under pytest). A developer with `RUMIA_DB_MODE=enabled`
  locally therefore had the housing tests calling the live Rumia API and
  asserting against Rumia's listings instead of their own fixtures.
- Mutating `Settings.model_config["env_file"] = None` to prevent that
  does *not* work on pydantic-settings 2.7.x — the source is built from
  the config captured when the class was created, so the dotenv file is
  still read. That approach has been removed rather than left in place
  looking like a guard.

The reliable lever is the process environment, which pydantic-settings
gives precedence over any env file. Every variable the suite depends on is
therefore pinned here, so the tests describe the same world on a
developer laptop, in CI, and in a container regardless of what any local
dotenv file says.
"""
from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.update(
    {
        "APP_ENV": "test",
        "SECRET_KEY": "test-secret-key",
        "STORAGE_LOCAL_PATH": tempfile.mkdtemp(prefix="omniscient-test-storage-"),
        # Switches off dotenv loading in app/core/config.py. This is the
        # load-bearing line: `backend/.env` is a symlink to the repo-root
        # `.env`, and reading it leaks local values such as a half-parsed
        # `LLM_API_BASE=  # comment` into every Settings() in the suite.
        # Real environment variables below still take effect.
        "OMNISCIENT_ENV_FILE": "",
        # No outbound calls, ever: the mock repositories serve seeded data.
        "RUMIA_DB_MODE": "disabled",
        # Deterministic provider, no API key, no network.
        "LLM_PROVIDER": "mock",
        "LLM_FALLBACK_PROVIDER": "",
        "LLM_API_KEY": "",
        "LLM_API_BASE": "",
        # Local temp storage; S3/R2 would need credentials.
        "STORAGE_PROVIDER": "local",
        # Vector search needs PostgreSQL + pgvector, which the SQLite test
        # database is not. Retrieval is exercised directly with fakes in
        # test_rag.py instead of through the HTTP layer.
        "EMBEDDING_ENABLED": "false",
        "RAG_ENABLED": "false",
    }
)

from app.db.base import Base  # noqa: E402
from app.models import *  # noqa: E402,F401,F403

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def app_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    from app.api.deps import get_db_session
    from app.core.rate_limit import _rate_limiter
    from app.main import app

    async def _override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session
    _rate_limiter._hits.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()
