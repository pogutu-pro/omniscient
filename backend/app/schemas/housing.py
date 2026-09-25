from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class HostelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    area: str
    latitude: float | None = None
    longitude: float | None = None
    distance_from_campus_km: float
    price_ksh: int
    verified: bool
    amenities: list[str]
    availability: str
    description: str
    contact_phone: str | None = None
    source: str
    image_key: str | None = None
    image_url: str | None = None


class HostelSearchParams(BaseModel):
    """Validated parameters for a housing search — never raw LLM output."""

    max_budget_ksh: int | None = Field(default=None, ge=0, le=200_000)
    min_budget_ksh: int | None = Field(default=None, ge=0, le=200_000)
    area: str | None = Field(default=None, max_length=120)
    max_distance_km: float | None = Field(default=None, ge=0, le=50)
    amenities: list[str] = Field(default_factory=list)
    verified_only: bool = False
    limit: int = Field(default=10, ge=1, le=50)


class HostelCreate(BaseModel):
    """Admin-authored listing. `source` is always forced to "mock" by the
    repository — an admin can never claim a listing came from Rumia."""

    name: str = Field(min_length=2, max_length=160)
    area: str = Field(min_length=2, max_length=120)
    latitude: float | None = None
    longitude: float | None = None
    distance_from_campus_km: float = Field(ge=0, le=100)
    price_ksh: int = Field(ge=0, le=500_000)
    verified: bool = False
    amenities: list[str] = Field(default_factory=list)
    availability: str = Field(default="available", pattern="^(available|limited|full)$")
    description: str = Field(default="", max_length=500)
    contact_phone: str | None = Field(default=None, max_length=32)
    image_key: str | None = Field(default=None, max_length=500)


class HostelUpdate(HostelCreate):
    pass
