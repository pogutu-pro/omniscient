"""The Rumia integration boundary for housing data.

`HostelRepository` is the interface every domain tool depends on. Two
implementations satisfy it:

- `MockHostelRepository` — queries Omniscient's own PostgreSQL database,
  seeded with realistic DeKUT/Nyeri demo listings. This is what the app
  uses by default and requires no external credentials.
- `RumiaApiHostelRepository` — reads Rumia's listings through Rumia's own
  public, unauthenticated HTTP API. No database credentials, no shared
  secrets, and structurally incapable of writing: it exposes no write
  path at all. Selected when `RUMIA_DB_MODE=enabled`.

`get_hostel_repository()` is the single place that decides which
implementation is active, driven entirely by configuration — no call site
elsewhere in the app needs to know or care which one it's talking to.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.housing import Hostel
from app.schemas.housing import HostelCreate, HostelOut, HostelSearchParams, HostelUpdate

logger = logging.getLogger(__name__)


class HostelWriteNotSupported(Exception):
    """Raised when a write is attempted against a read-only repository
    (the Rumia ones). Admin CRUD only ever operates on Omniscient's own
    data - it can never write into Rumia."""


class RumiaUnavailable(Exception):
    """Raised when Rumia cannot be reached or answers unusably.

    Deliberately distinct from "no hostels matched": the caller must never
    let an unreachable upstream be reported to a student as an empty
    result set, which would read as "there is no housing near campus".
    """


class HostelRepository(ABC):
    @abstractmethod
    async def search(self, params: HostelSearchParams) -> list[HostelOut]: ...

    @abstractmethod
    async def get_by_id(self, hostel_id: str) -> HostelOut | None: ...

    @abstractmethod
    async def areas(self) -> list[str]: ...

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

    async def areas(self) -> list[str]:
        stmt = select(Hostel.area).distinct().order_by(Hostel.area)
        result = await self._session.execute(stmt)
        return [row for row in result.scalars().all() if row]

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


# --- Rumia field mapping ----------------------------------------------------
#
# Rumia stores housing as `public.listings` rows (a listing is what
# Omniscient calls a hostel) and serves them over an unauthenticated HTTP
# API. Its vocabulary does not line up with Omniscient's, so every field
# crossing this boundary is mapped explicitly below rather than by
# coincidence. Anything Rumia expresses that Omniscient has no field for is
# folded into the fields it does have, and never silently dropped.

# DeKUT's main campus. Only used as a last-resort distance reference when
# a listing carries neither a distance string, a distance category, nor
# usable coordinates.
_DEKUT_LAT = -0.3975
_DEKUT_LNG = 36.9615

# Last-resort distance, in km, for the rare listing with no distance signal
# at all. Logged when used so it is observable rather than invisible.
_UNKNOWN_DISTANCE_KM = 1.5

# Walking speed used to turn Rumia's "10 mins walk" into a distance. Chosen
# deliberately slowly: a 4.8 km/h pace is an honest upper bound for a
# student carrying a laptop, and overstating the walk is worse than
# understating it.
_KM_PER_WALK_MINUTE = 0.08

# Rumia's own coarse buckets, used when the free-text distance is missing.
_DISTANCE_CATEGORY_KM: dict[str, float] = {
    "walking-500m": 0.4,
    "5-10min": 0.8,
    "1-2km": 1.5,
    "3km": 3.0,
    "over-3km": 3.5,
}

# Rumia's amenity labels are title-cased prose ("Study Area"); Omniscient's
# seeded vocabulary is short lowercase tokens ("study room"). Mapping onto
# the tokens Omniscient already uses is what lets one amenity filter mean
# the same thing regardless of which repository is active.
_RUMIA_AMENITY_TOKENS: dict[str, str] = {
    "kitchen": "kitchen",
    "study area": "study room",
    "study room": "study room",
    "laundry area": "laundry",
    "laundry": "laundry",
    "parking": "parking",
    "cctv": "cctv",
    "guard": "security",
    "security": "security",
    "balcony": "balcony",
    "gym": "gym",
    "furnished": "furnished",
}

# "km", "kms", "kilometres", "kilometers" - real listings use all of these.
_KM_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|–|to)?\s*(\d+(?:\.\d+)?)?\s*k(?:ilo)?(?:m|ms|met(?:re|er)s?)\b")
_MINUTES_PATTERN = re.compile(r"(\d+)\s*(?:-|–|to)?\s*(\d+)?\s*min(?:ute)?s?\b")


def _slugify_amenity(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip().lower())


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    return round(2 * radius_km * math.asin(math.sqrt(a)), 2)


def _range_midpoint(match: re.Match[str]) -> float:
    """Midpoint of a matched measurement, so "5 - 10 minutes" reads as 7.5
    rather than as whichever end the regex happened to capture."""
    low = float(match.group(1))
    high = float(match.group(2)) if match.group(2) else low
    return (low + high) / 2


def _distance_from_text(text: str | None) -> float | None:
    """Turn Rumia's free-text `distance_to_campus` into a distance in km.

    Real values are messy prose written by listing agents ("10 mins walk",
    "3.7 kms", "Over 3 kilometres", "5 mins drive/45 mins walk", "30 bob
    distance via the matatu"). The rules below are ordered so the most
    explicit unit wins, and anything we cannot read confidently returns
    None so a later fallback can try instead of a number being invented.
    """
    if not text:
        return None
    lowered = " ".join(text.strip().lower().split())
    if not lowered:
        return None
    if re.search(r"\bin[- ]?campus\b", lowered):
        return 0.0

    km_match = _KM_PATTERN.search(lowered)
    if km_match:
        return _range_midpoint(km_match)

    minutes = [_range_midpoint(m) for m in _MINUTES_PATTERN.finditer(lowered)]
    if minutes:
        # A drive/walk pair ("5 mins drive/45 mins walk") describes the
        # same trip two ways; the walk figure is the one that matters to a
        # student on foot, and it is the larger of the two.
        return round(max(minutes) * _KM_PER_WALK_MINUTE, 2)

    # e.g. "30 bob distance via the matatu" - a real distance, expressed
    # in matatus. Not convertible, so decline rather than guess.
    return None


def _distance_km(listing: dict[str, Any]) -> float:
    """Best available distance in km, in descending order of trust."""
    parsed = _distance_from_text(listing.get("distance_to_campus"))
    if parsed is not None:
        return parsed

    category = _DISTANCE_CATEGORY_KM.get((listing.get("distance_category") or "").strip().lower())
    if category is not None:
        return category

    lat, lng = listing.get("latitude"), listing.get("longitude")
    if lat is not None and lng is not None:
        return _haversine_km(_DEKUT_LAT, _DEKUT_LNG, float(lat), float(lng))

    logger.warning(
        "Rumia listing %r has no distance signal; falling back to %s km",
        listing.get("slug") or listing.get("id"),
        _UNKNOWN_DISTANCE_KM,
    )
    return _UNKNOWN_DISTANCE_KM


def _amenities(listing: dict[str, Any]) -> list[str]:
    """Merge Rumia's amenity labels and utility flags into one vocabulary."""
    tokens: list[str] = []

    def add(token: str | None) -> None:
        if token and token not in tokens:
            tokens.append(token)

    for label in listing.get("amenities") or []:
        if not isinstance(label, str):
            continue
        key = _slugify_amenity(label)
        add(_RUMIA_AMENITY_TOKENS.get(key, key))

    for flag, token in (
        ("wifi_included", "wifi"),
        ("water_included", "water"),
        ("electricity_included", "electricity"),
        ("hot_water_included", "hot water"),
        ("cooking_gas_included", "cooking gas"),
    ):
        if listing.get(flag):
            add(token)

    security = (listing.get("security_type") or "").strip()
    if security and security.lower() not in {"none", "no"}:
        add("security")
    bathroom = (listing.get("bathroom_type") or "").strip().lower()
    if bathroom:
        add(f"{bathroom} bathroom")

    room_types = listing.get("room_types") or []
    if any((rt.get("furnishing_items") or []) for rt in room_types if isinstance(rt, dict)):
        add("furnished")

    return tokens


def _availability(listing: dict[str, Any]) -> str:
    """Map onto Omniscient's available | limited | full vocabulary.

    Rumia has no availability column: it has `is_full` plus a set of room
    types that may individually be taken. Both are real signals, so both
    are used rather than assuming availability from the listing's price.
    """
    if listing.get("is_full"):
        return "full"
    room_types = [rt for rt in (listing.get("room_types") or []) if isinstance(rt, dict)]
    if room_types:
        if not any(rt.get("is_available", True) for rt in room_types):
            return "full"
        if not all(rt.get("is_available", True) for rt in room_types):
            return "limited"
    return "available"


def _contact_phone(listing: dict[str, Any]) -> str | None:
    """Prefer the agent's own contact, which is the number a student is
    meant to call, over the raw landlord number on the row."""
    agent = listing.get("agent") or {}
    for value in (agent.get("phone"), agent.get("whatsapp"), listing.get("landlord_phone")):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _cover_image(listing: dict[str, Any]) -> str | None:
    images = [img for img in (listing.get("images") or []) if isinstance(img, dict) and img.get("r2_url")]
    if not images:
        return None
    images.sort(key=lambda img: (img.get("display_order") if img.get("display_order") is not None else 0))
    return images[0]["r2_url"]


def _searchable_text(listing: dict[str, Any]) -> str:
    """Lowercased text an area query is matched against.

    Rumia spreads a listing's human-readable location across `area`,
    `specific_location` and `location`, and a student searching "gate" means
    whichever of those happens to hold it. All of them are included so the
    area box behaves the way someone typing into it expects.
    """
    parts = [
        listing.get("title"),
        listing.get("area"),
        listing.get("specific_location"),
        listing.get("location"),
        listing.get("county"),
    ]
    return " ".join(str(p).lower() for p in parts if p)


def _from_rumia(listing: dict[str, Any], settings: Settings) -> HostelOut:
    """Map one Rumia listing onto Omniscient's `HostelOut`.

    Built explicitly rather than via `model_validate(..., from_attributes)`
    because almost no field name lines up between the two schemas.
    """
    title = (listing.get("title") or "").strip()
    area = (listing.get("area") or "").strip()
    specific = (listing.get("specific_location") or "").strip()
    description = " ".join((listing.get("description") or "").split())
    if len(description) > 500:
        description = description[:497].rstrip() + "..."

    # `image_key` is a key in Omniscient's own file storage; Rumia serves
    # absolute URLs from its CDN. So the URL is passed through as-is and no
    # key is invented.
    return HostelOut(
        id=str(listing.get("id") or listing.get("slug")),
        name=title or "Unnamed listing",
        area=area or specific or (listing.get("county") or "Nyeri").title(),
        latitude=float(listing["latitude"]) if listing.get("latitude") is not None else None,
        longitude=float(listing["longitude"]) if listing.get("longitude") is not None else None,
        distance_from_campus_km=_distance_km(listing),
        price_ksh=int(round(float(listing.get("price") or 0))),
        verified=bool(settings.rumia_treat_active_as_verified),
        amenities=_amenities(listing),
        availability=_availability(listing),
        description=description,
        contact_phone=_contact_phone(listing),
        source="rumia",
        image_key=None,
        image_url=_cover_image(listing),
    )


def _matches(hostel: HostelOut, params: HostelSearchParams) -> bool:
    """Client-side filters for the things Rumia's API cannot filter on."""
    if params.max_budget_ksh is not None and hostel.price_ksh > params.max_budget_ksh:
        return False
    if params.min_budget_ksh is not None and hostel.price_ksh < params.min_budget_ksh:
        return False
    if params.max_distance_km is not None and hostel.distance_from_campus_km > params.max_distance_km:
        return False
    if params.verified_only and not hostel.verified:
        return False
    if params.amenities:
        available = {a.lower() for a in hostel.amenities}
        if not {a.lower() for a in params.amenities}.issubset(available):
            return False
    return True


@dataclass(frozen=True)
class _FeedEntry:
    """A mapped listing plus the text an area search should match against.

    The haystack is precomputed once per fetch because the area box is free
    text and a student may type "gate" or "Near Gate C", which lives in a
    different Rumia column than the one we display as `area`.
    """

    hostel: HostelOut
    haystack: str
    slug: str


class RumiaApiHostelRepository(HostelRepository):
    """Read-only housing data sourced from Rumia's public HTTP API.

    The transport is Rumia's own unauthenticated `GET /listings` endpoint.
    Three properties make this boundary safe by construction rather than by
    convention:

    - No credentials. There is no key, token or connection string to leak,
      rotate, or accidentally reuse somewhere else.
    - No write path. Rumia already filters to `is_active = true`; this
      class adds no write method, so "Omniscient mutated Rumia" is not a
      mistake anyone can make here - there is no code to make it with.
    - No schema coupling. Rumia's `listings` table is read through its own
      public contract, so a migration on Rumia's side cannot break us at
      the SQL level, and we never need write access or elevated roles on
      someone else's production database.

    Only DeKUT's campus is requested: Rumia is campus-scoped, and
    `rumia_campus_slug` is the discriminator.

    **Why this caches a whole campus feed rather than caching per query.**
    Rumia's listings endpoint answers in 4-6 seconds, so the cost that
    matters is the number of upstream calls, not local CPU. Caching per
    filter combination would still make one upstream call per distinct
    query, which is exactly as slow as no cache at all for a student
    clicking through filters. Instead the entire (small) campus feed is
    fetched once per TTL and every query filters it in memory, so filters
    are free and the upstream is hit once a minute at most.

    Reads are served stale-while-revalidate: once a feed has been fetched,
    requests are answered from it immediately and the refresh happens in
    the background, so a user never waits on Rumia mid-conversation. Past
    `max_stale`, the refresh is awaited instead - bounded staleness rather
    than unbounded, and never a silently wrong "no hostels found".
    """

    _FEED_LIMIT = 200
    # How long beyond the TTL a feed may still be served while a refresh
    # runs. Comfortably longer than a slow upstream response.
    _MAX_STALE_SECONDS = 600

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self._settings = settings
        self._campus_slug = settings.rumia_campus_slug
        self._ttl = settings.rumia_cache_ttl_seconds
        self._client = client or httpx.AsyncClient(
            base_url=settings.rumia_api_base_url.rstrip("/"),
            timeout=settings.rumia_timeout_seconds,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )
        self._owns_client = client is None

        self._feed: list[_FeedEntry] | None = None
        self._index: dict[str, _FeedEntry] = {}
        self._fetched_at = 0.0
        self._refresh: asyncio.Task | None = None
        # Per-listing detail responses (only needed for an id that is not in
        # the campus feed), keyed by id or slug.
        self._detail: dict[str, tuple[float, HostelOut | None]] = {}
        self._detail_locks: dict[str, asyncio.Lock] = {}

    async def aclose(self) -> None:
        if self._refresh and not self._refresh.done():
            self._refresh.cancel()
        if self._owns_client:
            await self._client.aclose()

    async def warm(self) -> int:
        """Fetch the campus feed up front (used at application startup).

        Returns the number of listings cached. Raises `RumiaUnavailable` if
        the upstream cannot be reached, which callers are expected to treat
        as non-fatal.
        """
        entries = await self._fetch_feed()
        return len(entries)

    # --- feed caching ------------------------------------------------------

    def _feed_is_fresh(self, now: float) -> bool:
        return self._feed is not None and (now - self._fetched_at) < self._ttl

    def _feed_is_usable(self, now: float) -> bool:
        return self._feed is not None and (now - self._fetched_at) < (self._ttl + self._MAX_STALE_SECONDS)

    async def _load_feed(self) -> list[_FeedEntry]:
        """Return the campus feed, refreshing in the background if it is
        merely stale and blocking only when there is nothing usable yet."""
        now = time.monotonic()
        if self._ttl <= 0:
            return await self._fetch_feed()
        if self._feed_is_fresh(now):
            return self._feed or []

        if self._feed_is_usable(now):
            self._start_refresh()
            return self._feed or []

        # Cold, or too stale to serve: block on a real fetch.
        return await self._fetch_feed()

    def _start_refresh(self) -> None:
        if self._refresh is not None and not self._refresh.done():
            return
        self._refresh = asyncio.create_task(self._refresh_soon())

    async def _refresh_soon(self) -> None:
        # Yield first so the caller keeps serving the cached feed instead of
        # waiting on this task to even reach its first await.
        await asyncio.sleep(0)
        try:
            await self._fetch_feed()
        except RumiaUnavailable as exc:
            # Keep serving the existing feed; the next request retries.
            logger.warning("Rumia background refresh failed, serving cached listings: %s", exc)

    async def _fetch_feed(self) -> list[_FeedEntry]:
        payload = await self._request(
            "/listings",
            {"campus_slug": self._campus_slug, "page": 1, "limit": self._FEED_LIMIT},
        )
        items = (payload or {}).get("items")
        if not isinstance(items, list):
            raise RumiaUnavailable("Rumia returned an unexpected listings payload")

        # Map once here rather than per query: the regex date/distance
        # parsing and amenity normalisation are the only non-trivial local
        # work, and there is no reason to redo them for every filter.
        entries = [
            _FeedEntry(
                hostel=_from_rumia(item, self._settings),
                haystack=_searchable_text(item),
                slug=str(item.get("slug") or ""),
            )
            for item in items
            if isinstance(item, dict)
        ]
        self._feed = entries
        # Rumia's own detail route accepts either a UUID or a slug, and both
        # turn up as ids in practice (the chat model quotes slugs it saw in
        # a table). Index both so neither costs an upstream call.
        self._index = {}
        for entry in entries:
            self._index[entry.hostel.id.lower()] = entry
            if entry.slug:
                self._index[entry.slug.lower()] = entry
        self._fetched_at = time.monotonic()
        return entries

    # --- requests ----------------------------------------------------------

    async def _request(self, path: str, query: dict[str, Any]) -> Any:
        try:
            response = await self._client.get(path, params=query)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            # 404 on a single listing is a real answer ("no such listing"),
            # not an upstream failure.
            if exc.response.status_code == 404:
                return None
            logger.warning("Rumia API returned %s for %s", exc.response.status_code, path)
            raise RumiaUnavailable(f"Rumia returned HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Rumia API request to %s failed: %s", path, exc)
            raise RumiaUnavailable("Rumia could not be reached") from exc

    async def search(self, params: HostelSearchParams) -> list[HostelOut]:
        entries = await self._load_feed()

        wanted_area = params.area.strip().lower() if params.area else None
        matched: list[HostelOut] = []
        for entry in entries:
            if wanted_area and wanted_area not in entry.haystack:
                continue
            if _matches(entry.hostel, params):
                matched.append(entry.hostel)

        matched.sort(key=lambda h: (not h.verified, h.distance_from_campus_km))
        return matched[: params.limit]

    async def get_by_id(self, hostel_id: str) -> HostelOut | None:
        # Almost every id a student or the model has is already in the feed,
        # by UUID or by slug, so this is a local lookup rather than a second
        # upstream call.
        await self._load_feed()
        entry = self._index.get(hostel_id.strip().lower())
        if entry is not None:
            return entry.hostel
        return await self._fetch_detail(hostel_id)

    async def areas(self) -> list[str]:
        """Distinct areas present in the listings.

        Derived from the data rather than hardcoded anywhere, because the
        set of areas is a property of whichever repository is active: Rumia's
        areas (Boma, Kahawa Ridge, Near Gate A, ...) are not the seeded demo
        ones, and a hardcoded list silently offers filters that match nothing.
        """
        await self._load_feed()
        areas = {entry.hostel.area for entry in (self._feed or []) if entry.hostel.area}
        return sorted(areas, key=str.casefold)

    async def _fetch_detail(self, hostel_id: str) -> HostelOut | None:
        """Detail fetch for an id outside the cached campus feed, deduplicated
        so concurrent requests for the same id make one upstream call."""
        now = time.monotonic()
        if self._ttl > 0:
            cached = self._detail.get(hostel_id)
            if cached and (now - cached[0]) < self._ttl:
                return cached[1]

        lock = self._detail_locks.setdefault(hostel_id, asyncio.Lock())
        async with lock:
            # Another waiter may have populated it while we queued.
            if self._ttl > 0:
                cached = self._detail.get(hostel_id)
                if cached and (time.monotonic() - cached[0]) < self._ttl:
                    return cached[1]

            payload = await self._request(f"/listings/{hostel_id}", {})
            hostel = None
            if isinstance(payload, dict) and payload.get("id"):
                hostel = _from_rumia(payload, self._settings)
            if self._ttl > 0:
                self._detail[hostel_id] = (time.monotonic(), hostel)
            return hostel

    async def create(self, data: HostelCreate) -> HostelOut:
        raise HostelWriteNotSupported("Rumia-backed housing data is read-only")

    async def update(self, hostel_id: str, data: HostelUpdate) -> HostelOut | None:
        raise HostelWriteNotSupported("Rumia-backed housing data is read-only")

    async def delete(self, hostel_id: str) -> bool:
        raise HostelWriteNotSupported("Rumia-backed housing data is read-only")


# One repository (and therefore one HTTP client, one connection pool and one
# feed cache) per distinct configuration, reused across requests.
#
# This matters: `get_hostel_repository` is a FastAPI dependency, so it runs
# per request. Constructing the repository per request would build a new
# `httpx.AsyncClient` each time - a fresh TLS handshake per request, and
# never closed - and would leave the cache empty on every call, making the
# TTL meaningless. Memoising on the config values keeps all three.
_shared_repositories: dict[tuple[Any, ...], RumiaApiHostelRepository] = {}


def get_hostel_repository(session: AsyncSession, settings: Settings) -> HostelRepository:
    """The only place that decides which housing data source is active.

    There is deliberately no direct-Postgres branch here. Reading Rumia's
    production database would mean either provisioning a role inside that
    database (a write to someone else's system) or reusing a superuser
    credential, and neither is a price worth paying for data that Rumia
    already serves read-only over HTTP. `RUMIA_DATABASE_URL` therefore has
    no consumer: the boundary is closed by construction, not by policy.
    """
    if settings.rumia_db_mode == "enabled":
        key = (
            settings.rumia_api_base_url,
            settings.rumia_campus_slug,
            settings.rumia_timeout_seconds,
            settings.rumia_cache_ttl_seconds,
            settings.rumia_treat_active_as_verified,
        )
        repo = _shared_repositories.get(key)
        if repo is None:
            repo = RumiaApiHostelRepository(settings)
            _shared_repositories[key] = repo
        return repo
    return MockHostelRepository(session, settings)

