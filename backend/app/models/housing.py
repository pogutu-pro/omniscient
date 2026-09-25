from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class Hostel(Base, TimestampMixin):
    """A housing listing.

    `source` distinguishes Omniscient's own seeded demo data ("mock") from
    anything eventually synced in from Rumia ("rumia"), so the UI can be
    honest about provenance per the brief's demo-data requirement.
    """

    __tablename__ = "hostels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    area: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_from_campus_km: Mapped[float] = mapped_column(Float, nullable=False)
    price_ksh: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    amenities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    availability: Mapped[str] = mapped_column(String(20), nullable=False, default="available")
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="mock")
