from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

ALLOWED_CATEGORIES = {"maintenance", "security", "academic", "hostel", "utilities", "other"}


class ComplaintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reference_code: str
    student_id: str
    category: str
    details: str
    location: str
    attachment_reference: str | None
    status: str
    created_at: dt.datetime
    updated_at: dt.datetime


class ComplaintCreate(BaseModel):
    category: str = Field(max_length=40)
    details: str = Field(min_length=10, max_length=2000)
    location: str = Field(default="", max_length=160)
    attachment_reference: str | None = Field(default=None, max_length=500)

    @property
    def is_valid_category(self) -> bool:
        return self.category in ALLOWED_CATEGORIES
