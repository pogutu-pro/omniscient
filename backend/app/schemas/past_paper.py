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


class PastPaperCreate(BaseModel):
    """`file_reference`/`file_name` must be a key already returned by
    POST /api/files/upload - this endpoint only ever attaches metadata to
    a file that has already gone through upload validation, it never
    accepts raw file bytes itself."""

    course_id: str
    programme_id: str
    academic_year: str = Field(min_length=4, max_length=9, pattern=r"^\d{4}(/\d{4})?$")
    semester: int = Field(ge=1, le=3)
    exam_type: str = Field(default="main", pattern="^(main|supplementary|cat)$")
    file_reference: str = Field(min_length=1, max_length=500)
    file_name: str = Field(min_length=1, max_length=255)
