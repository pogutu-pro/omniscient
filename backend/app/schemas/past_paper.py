from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PastPaperOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    course_code: str
    course_name: str
    programme_id: str
    academic_year: str
    semester: int
    exam_type: str
    file_name: str
    download_url: str


class PastPaperSearchParams(BaseModel):
    query: str | None = Field(default=None, max_length=200)
    course_code: str | None = Field(default=None, max_length=20)
    programme_code: str | None = Field(default=None, max_length=20)
    academic_year: str | None = Field(default=None, max_length=9)
    limit: int = Field(default=10, ge=1, le=50)
