from __future__ import annotations

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class Student(Base, TimestampMixin):
    """A DeKUT student's Omniscient identity and light personalization profile.

    `preferences` holds a small, inspectable, product-purposed set of
    values (e.g. last housing budget/area) — never an unbounded memory
    dump. See services/personalization_service.py for how it is read and
    updated, and how an explicit current-request value always overrides it.
    """

    __tablename__ = "students"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    registration_number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    programme: Mapped[str] = mapped_column(String(120), nullable=False)
    year_of_study: Mapped[int] = mapped_column(nullable=False, default=1)
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
