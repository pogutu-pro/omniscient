"""The Rumia integration boundary for housing data.

`HostelRepository` is the interface every domain tool depends on. Two
implementations satisfy it:

- `MockHostelRepository` — queries Omniscient's own PostgreSQL database,
  seeded with realistic DeKUT/Nyeri demo listings. This is what the app
  uses today and requires no external credentials.
- `RumiaPostgresHostelRepository` — reads from a *separate*, read-only
  Rumia listings connection. It never writes, never touches user/lead
  tables, and is only selected when `RUMIA_DB_MODE=enabled` and a
  connection string is actually configured.

`get_hostel_repository()` is the single place that decides which
implementation is active, driven entirely by configuration — no call site
elsewhere in the app needs to know or care which one it's talking to.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.models.housing import Hostel
from app.schemas.housing import HostelOut, HostelSearchParams


class HostelRepository(ABC):
    @abstractmethod
    async def search(self, params: HostelSearchParams) -> list[HostelOut]: ...

    @abstractmethod
    async def get_by_id(self, hostel_id: str) -> HostelOut | None: ...


def _apply_filters(stmt, params: HostelSearchParams):
    if params.max_budget_ksh is not None:
        stmt = stmt.where(Hostel.price_ksh <= params.max_budget_ksh)
    if params.min_budget_ksh is not None:
        stmt = stmt.where(Hostel.price_ksh >= params.min_budget_ksh)
    if params.area:
        stmt = stmt.where(Hostel.area.ilike(f"%{params.area}%"))
    if params.max_distance_km is not None:
        stmt = stmt.where(Hostel.distance_from_campus_km <= params.max_distance_km)
    if params.verified_only:
        stmt = stmt.where(Hostel.verified.is_(True))
    return stmt


class MockHostelRepository(HostelRepository):
    """Demo-data implementation backed by Omniscient's own database."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def search(self, params: HostelSearchParams) -> list[HostelOut]:
        stmt = select(Hostel)
        stmt = _apply_filters(stmt, params)
        stmt = stmt.order_by(Hostel.verified.desc(), Hostel.distance_from_campus_km.asc()).limit(params.limit)
        result = await self._session.execute(stmt)
        hostels = result.scalars().all()
        if params.amenities:
            wanted = {a.lower() for a in params.amenities}
            hostels = [h for h in hostels if wanted.issubset({a.lower() for a in h.amenities})]
        return [HostelOut.model_validate(h) for h in hostels]

    async def get_by_id(self, hostel_id: str) -> HostelOut | None:
        hostel = await self._session.get(Hostel, hostel_id)
        return HostelOut.model_validate(hostel) if hostel else None


class RumiaPostgresHostelRepository(HostelRepository):
    """Read-only implementation against Rumia's listings data.

    Intentionally minimal: this class exists to define the integration
    boundary and prove the interface is satisfiable by a second data
    source, not to claim a live Rumia connection exists. It must only ever
    be pointed at read-only, listings-only credentials — never Rumia's
    user or lead tables, and never anything with write permission.
    """

    def __init__(self, rumia_database_url: str):
        if not rumia_database_url:
            raise ValueError("RumiaPostgresHostelRepository requires RUMIA_DATABASE_URL to be set")
        engine = create_async_engine(rumia_database_url, pool_pre_ping=True, future=True)
        self._session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    async def search(self, params: HostelSearchParams) -> list[HostelOut]:
        async with self._session_factory() as session:
            stmt = select(Hostel)
            stmt = _apply_filters(stmt, params)
            stmt = stmt.order_by(Hostel.verified.desc(), Hostel.distance_from_campus_km.asc()).limit(params.limit)
            result = await session.execute(stmt)
            return [HostelOut.model_validate(h) for h in result.scalars().all()]

    async def get_by_id(self, hostel_id: str) -> HostelOut | None:
        async with self._session_factory() as session:
            hostel = await session.get(Hostel, hostel_id)
            return HostelOut.model_validate(hostel) if hostel else None


def get_hostel_repository(session: AsyncSession, settings: Settings) -> HostelRepository:
    if settings.rumia_db_mode == "enabled" and settings.rumia_database_url:
        return RumiaPostgresHostelRepository(settings.rumia_database_url)
    return MockHostelRepository(session)
