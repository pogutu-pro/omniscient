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
from app.schemas.housing import HostelCreate, HostelOut, HostelSearchParams, HostelUpdate


class HostelWriteNotSupported(Exception):
    """Raised when a write is attempted against a read-only repository
    (RumiaPostgresHostelRepository). Admin CRUD only ever operates on
    Omniscient's own data - it can never write into Rumia."""


class HostelRepository(ABC):
    @abstractmethod
    async def search(self, params: HostelSearchParams) -> list[HostelOut]: ...

    @abstractmethod
    async def get_by_id(self, hostel_id: str) -> HostelOut | None: ...

    @abstractmethod
    async def create(self, data: HostelCreate) -> HostelOut: ...

    @abstractmethod
    async def update(self, hostel_id: str, data: HostelUpdate) -> HostelOut | None: ...

    @abstractmethod
    async def delete(self, hostel_id: str) -> bool: ...


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


def _to_out(hostel: Hostel, settings: Settings) -> HostelOut:
    """Builds HostelOut manually (rather than `.model_validate(hostel, from_attributes=True)`)
    because `image_url` isn't a column - it's computed from `image_key` the
    same way PastPaperOut.download_url is computed from a stored key."""
    return HostelOut(
        id=hostel.id,
        name=hostel.name,
        area=hostel.area,
        latitude=hostel.latitude,
        longitude=hostel.longitude,
        distance_from_campus_km=hostel.distance_from_campus_km,
        price_ksh=hostel.price_ksh,
        verified=hostel.verified,
        amenities=hostel.amenities,
        availability=hostel.availability,
        description=hostel.description,
        contact_phone=hostel.contact_phone,
        source=hostel.source,
        image_key=hostel.image_key,
        image_url=f"{settings.api_url}/api/files/{hostel.image_key}" if hostel.image_key else None,
    )


class MockHostelRepository(HostelRepository):
    """Demo-data implementation backed by Omniscient's own database."""

    def __init__(self, session: AsyncSession, settings: Settings):
        self._session = session
        self._settings = settings

    async def search(self, params: HostelSearchParams) -> list[HostelOut]:
        stmt = select(Hostel)
        stmt = _apply_filters(stmt, params)
        stmt = stmt.order_by(Hostel.verified.desc(), Hostel.distance_from_campus_km.asc()).limit(params.limit)
        result = await self._session.execute(stmt)
        hostels = result.scalars().all()
        if params.amenities:
            wanted = {a.lower() for a in params.amenities}
            hostels = [h for h in hostels if wanted.issubset({a.lower() for a in h.amenities})]
        return [_to_out(h, self._settings) for h in hostels]

    async def get_by_id(self, hostel_id: str) -> HostelOut | None:
        hostel = await self._session.get(Hostel, hostel_id)
        return _to_out(hostel, self._settings) if hostel else None

    async def create(self, data: HostelCreate) -> HostelOut:
        hostel = Hostel(**data.model_dump(), source="mock")
        self._session.add(hostel)
        await self._session.commit()
        await self._session.refresh(hostel)
        return _to_out(hostel, self._settings)

    async def update(self, hostel_id: str, data: HostelUpdate) -> HostelOut | None:
        hostel = await self._session.get(Hostel, hostel_id)
        if not hostel:
            return None
        for field, value in data.model_dump().items():
            setattr(hostel, field, value)
        await self._session.commit()
        await self._session.refresh(hostel)
        return _to_out(hostel, self._settings)

    async def delete(self, hostel_id: str) -> bool:
        hostel = await self._session.get(Hostel, hostel_id)
        if not hostel:
            return False
        await self._session.delete(hostel)
        await self._session.commit()
        return True


class RumiaPostgresHostelRepository(HostelRepository):
    """Read-only implementation against Rumia's listings data.

    Intentionally minimal: this class exists to define the integration
    boundary and prove the interface is satisfiable by a second data
    source, not to claim a live Rumia connection exists. It must only ever
    be pointed at read-only, listings-only credentials — never Rumia's
    user or lead tables, and never anything with write permission.
    """

    def __init__(self, rumia_database_url: str, settings: Settings):
        if not rumia_database_url:
            raise ValueError("RumiaPostgresHostelRepository requires RUMIA_DATABASE_URL to be set")
        engine = create_async_engine(rumia_database_url, pool_pre_ping=True, future=True)
        self._session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
        self._settings = settings

    async def search(self, params: HostelSearchParams) -> list[HostelOut]:
        async with self._session_factory() as session:
            stmt = select(Hostel)
            stmt = _apply_filters(stmt, params)
            stmt = stmt.order_by(Hostel.verified.desc(), Hostel.distance_from_campus_km.asc()).limit(params.limit)
            result = await session.execute(stmt)
            return [_to_out(h, self._settings) for h in result.scalars().all()]

    async def get_by_id(self, hostel_id: str) -> HostelOut | None:
        async with self._session_factory() as session:
            hostel = await session.get(Hostel, hostel_id)
            return _to_out(hostel, self._settings) if hostel else None

    async def create(self, data: HostelCreate) -> HostelOut:
        raise HostelWriteNotSupported("Rumia-backed housing data is read-only")

    async def update(self, hostel_id: str, data: HostelUpdate) -> HostelOut | None:
        raise HostelWriteNotSupported("Rumia-backed housing data is read-only")

    async def delete(self, hostel_id: str) -> bool:
        raise HostelWriteNotSupported("Rumia-backed housing data is read-only")


def get_hostel_repository(session: AsyncSession, settings: Settings) -> HostelRepository:
    if settings.rumia_db_mode == "enabled" and settings.rumia_database_url:
        return RumiaPostgresHostelRepository(settings.rumia_database_url, settings)
    return MockHostelRepository(session, settings)
