from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.academic_repository import SqlAcademicRepository
from app.repositories.complaint_repository import SqlComplaintRepository
from app.repositories.hostel_repository import (
    HostelWriteNotSupported,
    MockHostelRepository,
    RumiaApiHostelRepository,
    RumiaUnavailable,
    _distance_from_text,
    _shared_repositories,
    get_hostel_repository,
)
from app.repositories.past_paper_repository import SqlPastPaperRepository
from app.repositories.student_repository import SqlStudentRepository
from app.schemas.academics import CourseCreate, ProgrammeCreate, TimetableQuery
from app.schemas.complaint import ComplaintCreate
from app.schemas.housing import HostelCreate, HostelSearchParams, HostelUpdate
from app.schemas.past_paper import PastPaperSearchParams
from app.schemas.student import StudentCreate
from tests.factories import make_course, make_hostel, make_past_paper, make_student, make_timetable_entry


class _FakeSettings:
    api_url = "http://testserver"


class _RumiaSettings:
    """Stands in for `Settings` with only the fields the Rumia repository reads."""

    api_url = "http://testserver"
    rumia_api_base_url = "https://rumia.test/api/v1"
    rumia_campus_slug = "dekut"
    rumia_timeout_seconds = 5.0
    rumia_cache_ttl_seconds = 60
    rumia_treat_active_as_verified = True
    rumia_db_mode = "disabled"

    def __init__(self, **overrides):
        for key, value in overrides.items():
            setattr(self, key, value)


async def test_hostel_search_filters_by_budget_and_area(db_session: AsyncSession):
    await make_hostel(db_session, name="Cheap Boma Room", area="Boma", price_ksh=4000)
    await make_hostel(db_session, name="Pricey Boma Room", area="Boma", price_ksh=15000)
    await make_hostel(db_session, name="Cheap Kamakwa Room", area="Kamakwa", price_ksh=4000)

    repo = MockHostelRepository(db_session, _FakeSettings())
    results = await repo.search(HostelSearchParams(max_budget_ksh=8000, area="Boma"))

    assert len(results) == 1
    assert results[0].name == "Cheap Boma Room"


async def test_hostel_search_verified_only(db_session: AsyncSession):
    await make_hostel(db_session, name="Verified", verified=True)
    await make_hostel(db_session, name="Unverified", verified=False)

    repo = MockHostelRepository(db_session, _FakeSettings())
    results = await repo.search(HostelSearchParams(verified_only=True))

    assert [h.name for h in results] == ["Verified"]


async def test_mock_hostel_repository_create_update_delete(db_session: AsyncSession):
    repo = MockHostelRepository(db_session, _FakeSettings())

    created = await repo.create(
        HostelCreate(name="Repo Test Hostel", area="Boma", distance_from_campus_km=0.4, price_ksh=5000)
    )
    assert created.source == "mock"

    updated = await repo.update(
        created.id,
        HostelUpdate(name="Renamed", area="Boma", distance_from_campus_km=0.4, price_ksh=5200, verified=True),
    )
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.verified is True

    assert await repo.delete(created.id) is True
    assert await repo.get_by_id(created.id) is None
    assert await repo.delete(created.id) is False


async def test_rumia_hostel_repository_writes_raise_not_supported():
    settings = _RumiaSettings()
    repo = RumiaApiHostelRepository(settings)

    with pytest.raises(HostelWriteNotSupported):
        await repo.create(HostelCreate(name="XX", area="Boma", distance_from_campus_km=0.4, price_ksh=5000))
    with pytest.raises(HostelWriteNotSupported):
        await repo.update("some-id", HostelUpdate(name="XX", area="Boma", distance_from_campus_km=0.4, price_ksh=5000))
    with pytest.raises(HostelWriteNotSupported):
        await repo.delete("some-id")


# --- Rumia HTTP repository ---------------------------------------------------
#
# Every test here drives the real repository through a mocked httpx
# transport, so the request Omniscient actually makes (and the mapping of
# whatever comes back) is covered without touching the network.


def _listing(**overrides) -> dict:
    """A Rumia listing shaped like the real `public.listings` payload."""
    payload = {
        "id": "93c72b02-cbc2-41d7-9bd9-373f74cbcf8e",
        "title": "BARAKA ",
        "slug": "baraka-boma",
        "description": "Fully furnished bedsitters.",
        "property_type": "hostel",
        "price": 9300.0,
        "area": "Boma",
        "specific_location": "Near Gate C",
        "county": "nyeri",
        "landlord_phone": "0790396326",
        "is_full": False,
        "amenities": ["Kitchen", "Study Area"],
        "latitude": -0.4005,
        "longitude": 36.9645,
        "distance_to_campus": "10 mins walk",
        "distance_category": "5-10min",
        "bathroom_type": "Private",
        "security_type": "24/7 CCTV & Guards",
        "wifi_included": True,
        "water_included": True,
        "electricity_included": False,
        "room_types": [
            {
                "room_type": "Bedsitter",
                "price": 9300.0,
                "is_available": True,
                "furnishing_items": ["Bed frame"],
            }
        ],
        "agent": {"phone": "+254742692160", "whatsapp": "+254742692160"},
        "images": [
            {"r2_url": "https://cdn.example/second.webp", "display_order": 1},
            {"r2_url": "https://cdn.example/first.webp", "display_order": 0},
        ],
    }
    payload.update(overrides)
    return payload


def _rumia_repo(handler, **setting_overrides) -> RumiaApiHostelRepository:
    settings = _RumiaSettings(**setting_overrides)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://rumia.test/api/v1")
    return RumiaApiHostelRepository(settings, client=client)


def _feed(*listings: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": list(listings), "total": len(listings), "page": 1, "limit": 200})

    return handler


def _one(listing: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=listing)

    return handler


def test_get_hostel_repository_defaults_to_mock():
    assert isinstance(get_hostel_repository(None, _RumiaSettings(rumia_db_mode="disabled")), MockHostelRepository)  # type: ignore[arg-type]


def test_get_hostel_repository_selects_rumia_when_enabled():
    repo = get_hostel_repository(None, _RumiaSettings(rumia_db_mode="enabled"))  # type: ignore[arg-type]
    assert isinstance(repo, RumiaApiHostelRepository)


async def test_rumia_search_maps_a_listing_onto_omniscients_schema():
    repo = _rumia_repo(_feed(_listing()))

    results = await repo.search(HostelSearchParams())

    assert len(results) == 1
    hostel = results[0]
    assert hostel.name == "BARAKA"  # trailing whitespace trimmed
    assert hostel.area == "Boma"
    assert hostel.price_ksh == 9300
    assert hostel.source == "rumia"
    assert hostel.image_key is None
    # display_order decides the cover, not response order.
    assert hostel.image_url == "https://cdn.example/first.webp"
    # The agent's number is preferred over the raw landlord number.
    assert hostel.contact_phone == "+254742692160"


async def test_rumia_search_only_requests_the_configured_campus():
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json={"items": []})

    repo = _rumia_repo(handler, rumia_campus_slug="dekut")
    await repo.search(HostelSearchParams())

    assert seen[0].path.endswith("/listings")
    assert seen[0].params["campus_slug"] == "dekut"


async def test_rumia_search_filters_distance_amenities_and_limit_client_side():
    close = _listing(id="a", title="Close", distance_to_campus="3 mins walk")  # 0.24 km
    far = _listing(id="b", title="Far", distance_to_campus="Over 3 kilometres", price=12000.0)  # 3.0 km
    no_wifi = _listing(id="c", title="No Wifi", wifi_included=False, amenities=[])  # 0.8 km
    repo = _rumia_repo(_feed(close, far, no_wifi))

    # Distance excludes the far listing only; "No Wifi" is still in range.
    assert [h.name for h in await repo.search(HostelSearchParams(max_distance_km=1.0))] == ["Close", "No Wifi"]
    assert [h.name for h in await repo.search(HostelSearchParams(amenities=["wifi"]))] == ["Close", "Far"]
    assert [h.name for h in await repo.search(HostelSearchParams(max_budget_ksh=9300))] == ["Close", "No Wifi"]
    assert [h.name for h in await repo.search(HostelSearchParams(min_budget_ksh=9301))] == ["Far"]
    assert len(await repo.search(HostelSearchParams(limit=2))) == 2


async def test_rumia_search_orders_by_distance_then_truncates_to_limit():
    listings = [
        _listing(id="a", title="Three", distance_to_campus="3 mins walk"),
        _listing(id="b", title="One", distance_to_campus="1 mins walk"),
        _listing(id="c", title="Two", distance_to_campus="2 mins walk"),
    ]
    repo = _rumia_repo(_feed(*listings))

    results = await repo.search(HostelSearchParams())

    assert [h.name for h in results] == ["One", "Two", "Three"]


async def test_rumia_verified_only_returns_nothing_when_source_cannot_verify():
    """With the vetting assertion switched off there is no verification
    signal to report, so claiming verified listings would be fabrication -
    an empty result is the honest answer."""
    repo = _rumia_repo(_feed(_listing()), rumia_treat_active_as_verified=False)

    assert await repo.search(HostelSearchParams(verified_only=True)) == []


async def test_rumia_treat_active_as_verified_is_opt_in():
    """Rumia vets listings before publishing them, so a live listing is
    treated as verified - the operator assertion behind the switch."""
    repo = _rumia_repo(_feed(_listing()), rumia_treat_active_as_verified=True)

    results = await repo.search(HostelSearchParams(verified_only=True))

    assert len(results) == 1
    assert results[0].verified is True


async def test_rumia_amenities_normalise_onto_omniscients_vocabulary():
    repo = _rumia_repo(_feed(_listing(amenities=["Study Area", "CCTV", "Something Unmapped"])))

    amenities = (await repo.search(HostelSearchParams()))[0].amenities

    assert "study room" in amenities  # Rumia's "Study Area" -> Omniscient's token
    assert "security" in amenities  # from CCTV + security_type
    assert "wifi" in amenities and "water" in amenities  # from the utility flags
    assert "furnished" in amenities  # from room type furnishing items
    assert "private bathroom" in amenities
    assert "something unmapped" in amenities  # unknown labels are kept, not dropped


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10 mins walk", 0.8),
        ("1 mins walk", 0.08),
        ("5 - 10 minutes walk", 0.6),
        ("In-campus", 0.0),
        ("about 3km", 3.0),
        ("3.7 kms", 3.7),
        ("Over 3 kilometres", 3.0),
        ("5 mins drive/45 mins walk", 3.6),  # the walk leg is the honest one
        ("30 bob distance via the matatu", None),  # unconvertible, so decline
        ("", None),
        (None, None),
    ],
)
def test_distance_from_text_handles_real_agent_prose(text, expected):
    assert _distance_from_text(text) == expected


async def test_rumia_distance_falls_back_to_category_then_coordinates():
    from_category = _listing(id="a", distance_to_campus="", distance_category="walking-500m")
    from_coords = _listing(
        id="b",
        distance_to_campus="",
        distance_category=None,
        latitude=-0.4235,
        longitude=36.9502,
    )
    repo = _rumia_repo(_feed(from_category, from_coords))

    by_id = {h.id: h for h in await repo.search(HostelSearchParams())}

    assert by_id["a"].distance_from_campus_km == 0.4
    assert by_id["b"].distance_from_campus_km == pytest.approx(3.24, abs=0.1)


async def test_rumia_availability_from_is_full_and_room_types():
    full = _listing(id="a", title="Full", is_full=True)
    none_left = _listing(id="b", title="NoneLeft", room_types=[{"is_available": False}])
    some_left = _listing(id="c", title="SomeLeft", room_types=[{"is_available": True}, {"is_available": False}])
    open_ = _listing(id="d", title="Open", room_types=[])
    repo = _rumia_repo(_feed(full, none_left, some_left, open_))

    by_name = {h.name: h.availability for h in await repo.search(HostelSearchParams(limit=50))}

    assert by_name == {"Full": "full", "NoneLeft": "full", "SomeLeft": "limited", "Open": "available"}


async def test_rumia_raises_rumia_unavailable_instead_of_returning_empty():
    """An unreachable source must not be reported as "no hostels found"."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    with pytest.raises(RumiaUnavailable):
        await _rumia_repo(handler).search(HostelSearchParams())


async def test_rumia_raises_on_a_malformed_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": "not-a-list"})

    with pytest.raises(RumiaUnavailable):
        await _rumia_repo(handler).search(HostelSearchParams())


async def test_rumia_fetches_the_campus_feed_once_for_every_filter():
    """The point of the whole-feed cache: filters are answered locally, so
    browsing by budget/area/distance costs one upstream call in total
    rather than one per distinct query."""
    calls = {"n": 0}
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        seen.append(request.url)
        return httpx.Response(200, json={"items": [_listing()]})

    repo = _rumia_repo(handler)
    await repo.search(HostelSearchParams())
    await repo.search(HostelSearchParams(area="Boma"))
    await repo.search(HostelSearchParams(max_budget_ksh=8000))
    await repo.search(HostelSearchParams(amenities=["wifi"]))

    assert calls["n"] == 1
    # One unfiltered campus fetch - not one filtered query per filter.
    assert set(seen[0].params) == {"campus_slug", "page", "limit"}


async def test_rumia_search_serves_the_cached_feed_while_refreshing_in_the_background():
    """Rumia takes seconds to answer, so a stale feed is served immediately
    and refreshed behind the request rather than making the user wait."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"items": [_listing()]})

    # TTL already elapsed by the time the second search runs.
    repo = _rumia_repo(handler, rumia_cache_ttl_seconds=60)
    await repo.search(HostelSearchParams())
    repo._fetched_at -= 61

    results = await repo.search(HostelSearchParams())

    assert len(results) == 1  # answered from cache, not blocked on upstream
    await repo._refresh  # let the background refresh land
    assert calls["n"] == 2


async def test_rumia_search_blocks_on_a_fetch_when_the_cache_is_too_stale():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"items": [_listing()]})

    repo = _rumia_repo(handler, rumia_cache_ttl_seconds=60)
    await repo.search(HostelSearchParams())
    # Past the TTL plus the max-stale window, so the old feed is not served.
    repo._fetched_at -= repo._ttl + repo._MAX_STALE_SECONDS + 1

    await repo.search(HostelSearchParams())

    assert calls["n"] == 2


async def test_rumia_keeps_serving_the_cached_feed_when_a_refresh_fails():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={"items": [_listing()]})
        return httpx.Response(503, text="upstream down")

    repo = _rumia_repo(handler, rumia_cache_ttl_seconds=60)
    await repo.search(HostelSearchParams())
    repo._fetched_at -= 61

    results = await repo.search(HostelSearchParams())
    await repo._refresh

    # A broken refresh must not turn into "no hostels found" for the user.
    assert len(results) == 1


async def test_rumia_area_matches_wherever_the_location_is_written():
    """Rumia splits location across columns; a student typing "gate" means
    whichever one holds it."""
    repo = _rumia_repo(_feed(_listing(area="Boma", specific_location="Near Gate C", location="")))

    assert len(await repo.search(HostelSearchParams(area="gate"))) == 1
    assert len(await repo.search(HostelSearchParams(area="boma"))) == 1
    assert await repo.search(HostelSearchParams(area="kahawa")) == []


async def test_rumia_get_by_id_is_served_from_the_cached_feed():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"items": [_listing()]})

    repo = _rumia_repo(handler)
    await repo.search(HostelSearchParams())  # warm the feed
    hostel = await repo.get_by_id("93c72b02-cbc2-41d7-9bd9-373f74cbcf8e")

    assert hostel is not None and hostel.name == "BARAKA"
    assert calls["n"] == 1  # no second upstream call


async def test_rumia_get_by_id_resolves_a_slug_from_the_cached_feed():
    """The model quotes slugs it saw in a results table, and Rumia's detail
    route takes either form - both must be local lookups."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"items": [_listing()]})

    repo = _rumia_repo(handler)
    await repo.search(HostelSearchParams())  # warm the feed

    assert (await repo.get_by_id("baraka-boma")) is not None
    assert (await repo.get_by_id("BARAKA-BOMA")) is not None  # case-insensitive
    assert (await repo.get_by_id("93c72b02-cbc2-41d7-9bd9-373f74cbcf8e")) is not None
    assert calls["n"] == 1


async def test_rumia_get_by_id_falls_back_to_the_detail_endpoint():
    """An id outside the campus feed still resolves, via the detail route."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("/listings"):
            return httpx.Response(200, json={"items": []})
        return httpx.Response(200, json=_listing(id="other-id", title="Elsewhere"))

    repo = _rumia_repo(handler)
    hostel = await repo.get_by_id("other-id")

    assert seen == ["/api/v1/listings", "/api/v1/listings/other-id"]
    assert hostel is not None and hostel.name == "Elsewhere"


async def test_rumia_get_by_id_returns_none_for_a_missing_listing():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/listings"):
            return httpx.Response(200, json={"items": []})
        return httpx.Response(404, json={"detail": "Not found"})

    assert await _rumia_repo(handler).get_by_id("nope") is None


async def test_rumia_caches_repeat_lookups_within_the_ttl():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"items": [_listing()]})

    repo = _rumia_repo(handler, rumia_cache_ttl_seconds=60)
    await repo.search(HostelSearchParams())
    await repo.search(HostelSearchParams())
    await repo.get_by_id("93c72b02-cbc2-41d7-9bd9-373f74cbcf8e")

    assert calls["n"] == 1


async def test_rumia_caching_can_be_disabled():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"items": [_listing()]})

    repo = _rumia_repo(handler, rumia_cache_ttl_seconds=0)
    await repo.search(HostelSearchParams())
    await repo.search(HostelSearchParams())

    assert calls["n"] == 2


def test_the_repository_is_reused_across_requests():
    """`get_hostel_repository` runs per request. If it built a new
    repository each time, every request would pay a fresh TLS handshake and
    start with an empty cache - which is what made this integration slow."""
    settings = _RumiaSettings(rumia_db_mode="enabled")
    try:
        first = get_hostel_repository(None, settings)  # type: ignore[arg-type]
        second = get_hostel_repository(None, settings)  # type: ignore[arg-type]
        assert first is second

        # A different configuration gets its own client and cache.
        other = get_hostel_repository(  # type: ignore[arg-type]
            None, _RumiaSettings(rumia_db_mode="enabled", rumia_campus_slug="other")
        )
        assert other is not first
    finally:
        # The clients here were never opened, so there is nothing to close;
        # this only stops them leaking into other tests via the memo.
        _shared_repositories.clear()


def test_the_boundary_has_no_direct_postgres_transport():
    """Regression guard: the factory must not grow a branch that connects to
    Rumia's production database. Doing so would need either write access to
    that database or a superuser credential, and Rumia already serves this
    same data read-only over HTTP."""
    import app.repositories.hostel_repository as module

    assert not hasattr(module, "RumiaPostgresHostelRepository")
    assert get_hostel_repository(None, _RumiaSettings(rumia_db_mode="enabled")).__class__ is RumiaApiHostelRepository  # type: ignore[arg-type]


async def test_academic_repository_programme_and_course_writes(db_session: AsyncSession):
    repo = SqlAcademicRepository(db_session)

    programme = await repo.create_programme(ProgrammeCreate(code="BSE", name="BSc Software Engineering"))
    assert programme.code == "BSE"

    course = await repo.create_course(
        CourseCreate(programme_id=programme.id, code="SSE 2101", name="Software Design", year_of_study=2, semester=1)
    )
    assert course.programme_id == programme.id

    assert await repo.delete_course(course.id) is True
    assert await repo.delete_course(course.id) is False


async def test_academic_repository_timetable_and_deadlines(db_session: AsyncSession):
    course = await make_course(db_session)
    await make_timetable_entry(db_session, course, day_of_week=0)
    await make_timetable_entry(db_session, course, day_of_week=2)

    repo = SqlAcademicRepository(db_session)
    monday_only = await repo.get_timetable(TimetableQuery(day_of_week=0))
    assert len(monday_only) == 1
    assert monday_only[0].course_code == course.code

    all_entries = await repo.get_timetable(TimetableQuery())
    assert len(all_entries) == 2


async def test_past_paper_repository_search_by_course_code(db_session: AsyncSession):
    course = await make_course(db_session)
    await make_past_paper(db_session, course, academic_year="2023/2024")
    await make_past_paper(db_session, course, academic_year="2022/2023")

    repo = SqlPastPaperRepository(db_session, _FakeSettings())
    results = await repo.search(PastPaperSearchParams(course_code="SCS 2101"))

    assert len(results) == 2
    assert all(r.course_code == "SCS 2101" for r in results)
    assert results[0].download_url.startswith("http://testserver/api/past-papers/")


async def test_complaint_repository_create_and_lookup(db_session: AsyncSession):
    student = await make_student(db_session)
    repo = SqlComplaintRepository(db_session)

    complaint = await repo.create(student.id, ComplaintCreate(category="maintenance", details="Broken tap in room B14"))
    assert complaint.reference_code.startswith("OMN-")
    assert complaint.status == "submitted"

    fetched = await repo.get_by_reference(complaint.reference_code)
    assert fetched is not None
    assert fetched.id == complaint.id

    mine = await repo.list_for_student(student.id)
    assert len(mine) == 1


async def test_student_repository_create_and_preferences(db_session: AsyncSession):
    repo = SqlStudentRepository(db_session)
    student = await repo.create(
        StudentCreate(
            registration_number="C026-01-0005/2023",
            full_name="New Student",
            email="new.student@dekut.ac.ke",
            password="Passw0rd!",
            programme="BSc IT",
            year_of_study=1,
        )
    )
    assert student.id

    updated = await repo.update_preferences(student.id, {"housing_max_budget_ksh": 9000})
    assert updated is not None
    assert updated.preferences["housing_max_budget_ksh"] == 9000
