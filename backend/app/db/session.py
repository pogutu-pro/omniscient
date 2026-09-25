from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

# statement_cache_size=0 disables asyncpg's server-side prepared-statement
# cache. It costs a little performance on a direct connection but is
# required for correctness against any transaction-mode connection pooler
# in front of Postgres (Neon's pooled endpoint, Supabase's pooler, plain
# PgBouncer) - those rotate the underlying server connection between
# statements, which breaks asyncpg's default prepared-statement reuse in
# ways that are easy to misdiagnose (intermittent "prepared statement does
# not exist" errors under load). Always on rather than conditional, since
# it's a no-op cost on a direct/unpooled connection and this one setting
# is what makes the same DATABASE_URL work against either kind.
connect_args: dict = {"statement_cache_size": 0}
if settings.database_ssl:
    connect_args["ssl"] = "require"

engine = create_async_engine(settings.database_url, pool_pre_ping=True, future=True, connect_args=connect_args)

AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
