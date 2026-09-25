from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class ProgrammeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    school: str


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    programme_id: str
    code: str
    name: str
    year_of_study: int
    semester: int


class TimetableEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    course_code: str
    course_name: str
    day_of_week: int
    start_time: str
    end_time: str
    venue: str
    session_type: str


class AcademicDeadlineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str
    category: str
    due_date: dt.date


class TimetableQuery(BaseModel):
    programme_code: str | None = Field(default=None, max_length=20)
    year_of_study: int | None = Field(default=None, ge=1, le=6)
    day_of_week: int | None = Field(default=None, ge=0, le=6)
