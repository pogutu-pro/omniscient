from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import get_hostel_repo
from app.repositories.hostel_repository import HostelRepository, RumiaUnavailable
from app.schemas.housing import HostelAreasOut, HostelOut, HostelSearchParams

router = APIRouter(prefix="/api/housing", tags=["housing"])

# Housing listings change slowly and are identical for every visitor, so a
# browser (or an intermediary) may reuse the response for a short while and
# revalidate in the background afterwards. This is what makes returning to
# the Housing page feel instant instead of paying a fresh round trip (and,
# on a cold cache, a multi-second Rumia fetch) every time.
_LISTINGS_CACHE = "public, max-age=60, stale-while-revalidate=600"
_AREAS_CACHE = "public, max-age=300, stale-while-revalidate=3600"


@router.get("/areas", response_model=HostelAreasOut)
async def list_areas(response: Response, repo: HostelRepository = Depends(get_hostel_repo)) -> HostelAreasOut:
    response.headers["Cache-Control"] = _AREAS_CACHE
    try:
        return HostelAreasOut(areas=await repo.areas())
    except RumiaUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Housing listings are temporarily unavailable.",
        ) from exc


@router.get("/hostels", response_model=list[HostelOut])
async def search_hostels(
    response: Response,
    max_budget_ksh: int | None = Query(default=None, ge=0),
    min_budget_ksh: int | None = Query(default=None, ge=0),
    area: str | None = Query(default=None),
    max_distance_km: float | None = Query(default=None, ge=0),
    verified_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=50),
    repo: HostelRepository = Depends(get_hostel_repo),
) -> list[HostelOut]:
    response.headers["Cache-Control"] = _LISTINGS_CACHE
    params = HostelSearchParams(
        max_budget_ksh=max_budget_ksh,
        min_budget_ksh=min_budget_ksh,
        area=area,
        max_distance_km=max_distance_km,
        verified_only=verified_only,
        limit=limit,
    )
    try:
        return await repo.search(params)
    except RumiaUnavailable as exc:
        # 503, not an empty list: the upstream housing source being
        # unreachable is a server-side fault, and answering 200 with []
        # would tell a student there is no housing near campus.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Housing listings are temporarily unavailable.",
        ) from exc


@router.get("/hostels/{hostel_id}", response_model=HostelOut)
async def get_hostel(
    hostel_id: str, response: Response, repo: HostelRepository = Depends(get_hostel_repo)
) -> HostelOut:
    response.headers["Cache-Control"] = _LISTINGS_CACHE
    try:
        hostel = await repo.get_by_id(hostel_id)
    except RumiaUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Housing listings are temporarily unavailable.",
        ) from exc
    if not hostel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hostel not found")
    return hostel
