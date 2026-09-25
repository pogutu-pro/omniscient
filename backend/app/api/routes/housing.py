from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_hostel_repo
from app.repositories.hostel_repository import HostelRepository
from app.schemas.housing import HostelOut, HostelSearchParams

router = APIRouter(prefix="/api/housing", tags=["housing"])


@router.get("/hostels", response_model=list[HostelOut])
async def search_hostels(
    max_budget_ksh: int | None = Query(default=None, ge=0),
    min_budget_ksh: int | None = Query(default=None, ge=0),
    area: str | None = Query(default=None),
    max_distance_km: float | None = Query(default=None, ge=0),
    verified_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=50),
    repo: HostelRepository = Depends(get_hostel_repo),
) -> list[HostelOut]:
    params = HostelSearchParams(
        max_budget_ksh=max_budget_ksh,
        min_budget_ksh=min_budget_ksh,
        area=area,
        max_distance_km=max_distance_km,
        verified_only=verified_only,
        limit=limit,
    )
    return await repo.search(params)


@router.get("/hostels/{hostel_id}", response_model=HostelOut)
async def get_hostel(hostel_id: str, repo: HostelRepository = Depends(get_hostel_repo)) -> HostelOut:
    hostel = await repo.get_by_id(hostel_id)
    if not hostel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hostel not found")
    return hostel
