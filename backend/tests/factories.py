from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.academics import Course, Programme, TimetableEntry
from app.models.housing import Hostel
from app.models.past_paper import PastPaper
from app.models.student import Student


async def make_student(session: AsyncSession, **overrides) -> Student:
    defaults = dict(
        registration_number="C026-01-0001/2023",
        full_name="Test Student",
        email="student@dekut.ac.ke",
        hashed_password=hash_password("Passw0rd!"),
        programme="BSc Computer Science",
        year_of_study=2,
        preferences={},
    )
    defaults.update(overrides)
    student = Student(**defaults)
    session.add(student)
    await session.commit()
    await session.refresh(student)
    return student


async def make_hostel(session: AsyncSession, **overrides) -> Hostel:
    defaults = dict(
        name="Boma View Hostel",
        area="Boma",
        distance_from_campus_km=0.4,
        price_ksh=6500,
        verified=True,
        amenities=["wifi", "water"],
        availability="available",
        description="Demo listing",
        source="mock",
    )
    defaults.update(overrides)
    hostel = Hostel(**defaults)
    session.add(hostel)
    await session.commit()
    await session.refresh(hostel)
    return hostel


async def make_course(session: AsyncSession, **overrides) -> Course:
    programme = Programme(code="BCS", name="BSc Computer Science", school="Computing")
    session.add(programme)
    await session.flush()
    defaults = dict(programme_id=programme.id, code="SCS 2101", name="Database Systems", year_of_study=2, semester=1)
    defaults.update(overrides)
    course = Course(**defaults)
    session.add(course)
    await session.commit()
    await session.refresh(course)
    return course


async def make_timetable_entry(session: AsyncSession, course: Course, **overrides) -> TimetableEntry:
    defaults = dict(course_id=course.id, day_of_week=0, start_time="08:00", end_time="10:00", venue="LT1", session_type="lecture")
    defaults.update(overrides)
    entry = TimetableEntry(**defaults)
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def make_past_paper(session: AsyncSession, course: Course, **overrides) -> PastPaper:
    defaults = dict(
        course_id=course.id,
        programme_id=course.programme_id,
        academic_year="2023/2024",
        semester=1,
        exam_type="main",
        file_reference="demo.pdf",
        file_name="demo.pdf",
    )
    defaults.update(overrides)
    paper = PastPaper(**defaults)
    session.add(paper)
    await session.commit()
    await session.refresh(paper)
    return paper
