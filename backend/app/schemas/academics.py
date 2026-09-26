from __future__ import annotations

import datetime as dt
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

# "4.2" — a year of study, a dot, and the semester within the academic year.
# Kept as a string because it is a label, not a number: "4.2" is neither 4.2
# nor 42, and the sheets print it exactly this way.
YEAR_GROUP_PATTERN = r"^[1-6]\.[1-3]$"

# DeKUT's two 12-hour clock spellings: "7AM-8AM" and "12PM-1PM".
HHMM_PATTERN = r"^(?:[01]\d|2[0-3]):[0-5]\d$"
ACADEMIC_YEAR_PATTERN = r"^\d{4}/\d{4}$"


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
    lecturer: str | None = None
    lecture_hours: int | None = None
    lab_hours: int | None = None
    class_size: int | None = None


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
    academic_year: str
    semester: int
    year_group: str
    stream: str | None = None
    lecturer: str | None = None


class AcademicDeadlineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str
    category: str
    due_date: dt.date
    programme_id: str | None = None


class TimetableQuery(BaseModel):
    programme_code: str | None = Field(default=None, max_length=20)
    year_of_study: int | None = Field(default=None, ge=1, le=6)
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    academic_year: str | None = Field(default=None, pattern=ACADEMIC_YEAR_PATTERN)
    year_group: str | None = Field(default=None, pattern=YEAR_GROUP_PATTERN)
    stream: str | None = Field(default=None, max_length=20)
    course_code: str | None = Field(default=None, max_length=20)


class AcademicTermOut(BaseModel):
    """One trimester of an academic year, as published.

    `provisional` is the important field: the usual period is a rule, but the
    real start, end and reporting dates are announced per programme and move,
    so a seeded term is a plan to confirm rather than a fact.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    academic_year: str
    trimester: int = Field(ge=1, le=3)
    label: str
    start_date: dt.date
    end_date: dt.date
    reporting_date: dt.date | None = None
    provisional: bool = True
    notes: str = ""


class AcademicTermCreate(BaseModel):
    academic_year: str = Field(pattern=ACADEMIC_YEAR_PATTERN)
    trimester: int = Field(ge=1, le=3)
    label: str = Field(default="", max_length=60)
    start_date: dt.date
    end_date: dt.date
    reporting_date: dt.date | None = None
    provisional: bool = True
    notes: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _end_after_start(self) -> AcademicTermCreate:
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        if self.reporting_date and not self.start_date <= self.reporting_date <= self.end_date:
            raise ValueError("reporting_date must fall inside the term")
        return self

    @model_validator(mode="after")
    def _default_label(self) -> AcademicTermCreate:
        # Students and the assistant both say "Semester 2"; a blank label would
        # make every consumer invent its own wording.
        if not self.label.strip():
            self.label = f"Semester {self.trimester}"
        return self


class AcademicsMeta(BaseModel):
    """Everything the Academics screen needs to build its controls.

    Sent as one payload rather than as several list endpoints so the screen
    renders from a single request, and so the year-group and stream lists can
    never disagree with the timetable they describes.
    """

    academic_years: list[str]
    year_groups: list[str]
    streams: list[str]
    session_types: list[str]
    deadline_categories: list[str]
    venues: list[str]
    current_academic_year: str
    current_trimester: int
    terms: list[AcademicTermOut]


class ProgrammeCreate(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2, max_length=160)
    school: str = Field(default="", max_length=160)


class CourseCreate(BaseModel):
    programme_id: str
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2, max_length=160)
    year_of_study: int = Field(ge=1, le=6)
    semester: int = Field(ge=1, le=3)
    lecturer: str | None = Field(default=None, max_length=120)
    lecture_hours: int | None = Field(default=None, ge=0, le=40)
    lab_hours: int | None = Field(default=None, ge=0, le=40)
    class_size: int | None = Field(default=None, ge=0, le=10_000)


class TimetableEntryCreate(BaseModel):
    course_id: str
    day_of_week: int = Field(ge=0, le=6)
    start_time: str = Field(pattern=HHMM_PATTERN)
    end_time: str = Field(pattern=HHMM_PATTERN)
    venue: str = Field(min_length=1, max_length=120)
    session_type: str = Field(default="lecture", max_length=20)
    academic_year: str = Field(pattern=ACADEMIC_YEAR_PATTERN)
    semester: int = Field(ge=1, le=3)
    year_group: str = Field(pattern=YEAR_GROUP_PATTERN)
    stream: str | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _end_after_start(self) -> TimetableEntryCreate:
        # Both are zero-padded 24-hour strings, so they compare correctly as
        # strings. Without this a session can be booked that ends before it
        # starts, which then renders as a negative-length block in the
        # timetable grid and never shows up as an error anywhere.
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class AcademicDeadlineCreate(BaseModel):
    programme_id: str | None = None
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=500)
    category: str = Field(default="general", max_length=40)
    due_date: dt.date


class AcademicDeadlineQuery(BaseModel):
    programme_code: str | None = Field(default=None, max_length=20)
    category: str | None = Field(default=None, max_length=40)
    limit: int = Field(default=20, ge=1, le=100)
    # Deadlines in the past are the default's job to hide: the student-facing
    # question is always "what is due next", and a past exam date is noise.
    # The admin screen opts back in so it can clean up what it has published.
    include_past: bool = False


# Course codes are a letter prefix and a number ("CCS 1101"), but a few
# departments issue unnumbered codes for project units ("CAPSTONE II"), so
# the check cannot be a single strict pattern. Used by the importer.
COURSE_CODE_LIKE = re.compile(r"^[A-Z][A-Z &]*\d{0,4}$")


class TimetableImportReportOut(BaseModel):
    academic_year: str
    term_label: str
    programme_code: str
    courses_created: int
    courses_updated: int
    sessions_created: int
    sessions_updated: int
    sessions_removed: int
    sessions_without_a_catalogue_entry: list[str]
    warnings: list[str]
    official_trimester: int | None = None
    summary: str

