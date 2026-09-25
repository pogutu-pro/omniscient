"""Realistic DeKUT/Nyeri demo dataset.

Everything inserted here is clearly synthetic sample data used to make the
product usable end-to-end without Rumia — never claims of real, verified
off-campus listings. Hostel rows are inserted with `source="mock"` so the
UI and API responses can be honest about provenance (see
repositories/hostel_repository.py for how a real Rumia-backed listing
would instead carry `source="rumia"`).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import hash_password
from app.models.academics import AcademicDeadline, Course, Programme, TimetableEntry
from app.models.complaint import Complaint
from app.models.housing import Hostel
from app.models.past_paper import PastPaper
from app.models.student import Student
from app.repositories.complaint_repository import generate_reference_code
from app.services.storage.factory import get_storage_backend

TODAY = dt.date.today()


async def is_seeded(session: AsyncSession) -> bool:
    result = await session.execute(select(Student.id).limit(1))
    return result.scalar_one_or_none() is not None


def _placeholder_pdf(title: str) -> bytes:
    """A minimal, valid, single-page PDF so downloads work end-to-end.

    This is demo content standing in for a real scanned/typed exam paper —
    never presented to students as an authoritative source.
    """
    text = f"({title} - Omniscient demo past paper. Replace with the real scanned paper.)"
    stream = f"BT /F1 14 Tf 40 700 Td {text} Tj ET"
    pdf = f"""%PDF-1.4
1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj
2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj
3 0 obj<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>endobj
4 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj
5 0 obj<< /Length {len(stream)} >>stream
{stream}
endstream
endobj
xref
0 6
trailer<< /Size 6 /Root 1 0 R >>
startxref
0
%%EOF"""
    return pdf.encode("latin-1", errors="replace")


async def seed(session: AsyncSession, settings: Settings) -> None:
    storage = get_storage_backend(settings)

    # --- Programmes ---
    programmes = {
        "BCS": Programme(code="BCS", name="BSc Computer Science", school="School of Computing & Information Technology"),
        "BIT": Programme(code="BIT", name="BSc Information Technology", school="School of Computing & Information Technology"),
        "BBIT": Programme(code="BBIT", name="BSc Business Information Technology", school="School of Business"),
        "BEEE": Programme(code="BEEE", name="BSc Electrical & Electronic Engineering", school="School of Engineering"),
        "BCE": Programme(code="BCE", name="BSc Civil Engineering", school="School of Engineering"),
    }
    session.add_all(programmes.values())
    await session.flush()

    # --- Courses ---
    courses = [
        Course(programme_id=programmes["BCS"].id, code="SCS 2101", name="Database Systems", year_of_study=2, semester=1),
        Course(programme_id=programmes["BCS"].id, code="SCS 2205", name="Data Structures & Algorithms", year_of_study=2, semester=1),
        Course(programme_id=programmes["BCS"].id, code="SCS 3110", name="Operating Systems", year_of_study=3, semester=1),
        Course(programme_id=programmes["BCS"].id, code="SCS 3214", name="Software Engineering", year_of_study=3, semester=2),
        Course(programme_id=programmes["BCS"].id, code="SCS 2308", name="Computer Networks", year_of_study=2, semester=2),
        Course(programme_id=programmes["BIT"].id, code="SIT 2102", name="Web Application Development", year_of_study=2, semester=1),
        Course(programme_id=programmes["BIT"].id, code="SIT 3105", name="Systems Analysis & Design", year_of_study=3, semester=1),
        Course(programme_id=programmes["BBIT"].id, code="SBB 2101", name="Business Information Systems", year_of_study=2, semester=1),
        Course(programme_id=programmes["BEEE"].id, code="SEE 2201", name="Electrical Circuit Theory", year_of_study=2, semester=1),
        Course(programme_id=programmes["BCE"].id, code="SCE 2101", name="Structural Mechanics", year_of_study=2, semester=1),
    ]
    session.add_all(courses)
    await session.flush()
    course_by_code = {c.code: c for c in courses}

    # --- Timetable (BCS year 2, semester 1, as the primary demo path) ---
    timetable = [
        TimetableEntry(course_id=course_by_code["SCS 2101"].id, day_of_week=0, start_time="08:00", end_time="10:00", venue="Block C - LT1", session_type="lecture"),
        TimetableEntry(course_id=course_by_code["SCS 2101"].id, day_of_week=2, start_time="14:00", end_time="17:00", venue="Comp Lab 2", session_type="lab"),
        TimetableEntry(course_id=course_by_code["SCS 2205"].id, day_of_week=0, start_time="10:00", end_time="12:00", venue="Block C - LT2", session_type="lecture"),
        TimetableEntry(course_id=course_by_code["SCS 2205"].id, day_of_week=3, start_time="08:00", end_time="10:00", venue="Block C - LT2", session_type="tutorial"),
        TimetableEntry(course_id=course_by_code["SCS 2308"].id, day_of_week=1, start_time="12:00", end_time="14:00", venue="Block D - LT1", session_type="lecture"),
        TimetableEntry(course_id=course_by_code["SCS 3110"].id, day_of_week=1, start_time="08:00", end_time="10:00", venue="Block C - LT3", session_type="lecture"),
        TimetableEntry(course_id=course_by_code["SCS 3110"].id, day_of_week=4, start_time="14:00", end_time="17:00", venue="Comp Lab 1", session_type="lab"),
        TimetableEntry(course_id=course_by_code["SCS 3214"].id, day_of_week=2, start_time="10:00", end_time="12:00", venue="Block C - LT1", session_type="lecture"),
        TimetableEntry(course_id=course_by_code["SIT 2102"].id, day_of_week=4, start_time="08:00", end_time="10:00", venue="Comp Lab 3", session_type="lab"),
        TimetableEntry(course_id=course_by_code["SEE 2201"].id, day_of_week=3, start_time="10:00", end_time="12:00", venue="Engineering Block - LT2", session_type="lecture"),
    ]
    session.add_all(timetable)

    # --- Academic deadlines ---
    deadlines = [
        AcademicDeadline(programme_id=programmes["BCS"].id, title="Semester unit registration closes", description="Register your units on the student portal before the deadline to avoid a late fee.", category="registration", due_date=TODAY + dt.timedelta(days=6)),
        AcademicDeadline(programme_id=None, title="Fee balance clearance for CATs", description="Clear at least 60% of tuition fees to be allowed to sit for CATs.", category="fees", due_date=TODAY + dt.timedelta(days=10)),
        AcademicDeadline(programme_id=None, title="CAT week begins", description="Continuous Assessment Tests for all schools begin.", category="exams", due_date=TODAY + dt.timedelta(days=21)),
        AcademicDeadline(programme_id=programmes["BCS"].id, title="Software Engineering group project submission", description="Final project report and repository link due on e-learning.", category="coursework", due_date=TODAY + dt.timedelta(days=28)),
        AcademicDeadline(programme_id=None, title="End-of-semester exam registration", description="Confirm your exam registration for all registered units.", category="exams", due_date=TODAY + dt.timedelta(days=35)),
    ]
    session.add_all(deadlines)

    # --- Housing (demo/mock listings around Nyeri, near DeKUT) ---
    hostels = [
        Hostel(name="Boma View Hostel", area="Boma", latitude=-0.4181, longitude=36.9558, distance_from_campus_km=0.4, price_ksh=6500, verified=True, amenities=["wifi", "water", "security", "furnished"], availability="available", description="Popular hostel a short walk from the main gate, with backup water and 24/7 security.", contact_phone="+254700100001", source="mock"),
        Hostel(name="Kamakwa Students Court", area="Kamakwa", latitude=-0.4235, longitude=36.9502, distance_from_campus_km=1.8, price_ksh=4500, verified=True, amenities=["wifi", "water", "parking"], availability="available", description="Quiet, affordable bedsitters popular with second and third years.", contact_phone="+254700100002", source="mock"),
        Hostel(name="Mawingo Heights", area="Mawingo", latitude=-0.4102, longitude=36.9601, distance_from_campus_km=2.3, price_ksh=8000, verified=True, amenities=["wifi", "water", "security", "gym", "furnished"], availability="limited", description="Modern apartments with a shared gym, a favourite for final-year students.", contact_phone="+254700100003", source="mock"),
        Hostel(name="Outspan Annex", area="Outspan", latitude=-0.4290, longitude=36.9470, distance_from_campus_km=3.1, price_ksh=3800, verified=False, amenities=["water"], availability="available", description="Budget rooms further from campus; verification pending.", contact_phone="+254700100004", source="mock"),
        Hostel(name="Ruring'u Green Court", area="Ruring'u", latitude=-0.4155, longitude=36.9530, distance_from_campus_km=1.1, price_ksh=7200, verified=True, amenities=["wifi", "water", "security", "furnished", "parking"], availability="available", description="Secure gated compound with a caretaker on site.", contact_phone="+254700100005", source="mock"),
        Hostel(name="Karatina Road Suites", area="Karatina Road", latitude=-0.4320, longitude=36.9440, distance_from_campus_km=3.6, price_ksh=5000, verified=False, amenities=["water", "parking"], availability="full", description="Larger units suited to sharing; currently fully booked.", contact_phone="+254700100006", source="mock"),
        Hostel(name="Majengo Student Lodge", area="Majengo", latitude=-0.4200, longitude=36.9580, distance_from_campus_km=0.9, price_ksh=5500, verified=True, amenities=["wifi", "water", "security"], availability="available", description="Close to the market and matatu stage, popular with first years.", contact_phone="+254700100007", source="mock"),
        Hostel(name="Boma Executive Bedsitters", area="Boma", latitude=-0.4170, longitude=36.9565, distance_from_campus_km=0.6, price_ksh=9500, verified=True, amenities=["wifi", "water", "security", "furnished", "gym"], availability="available", description="Premium furnished bedsitters with inverter backup power.", contact_phone="+254700100008", source="mock"),
        Hostel(name="Kamakwa Budget Rooms", area="Kamakwa", latitude=-0.4240, longitude=36.9495, distance_from_campus_km=2.0, price_ksh=3500, verified=False, amenities=["water"], availability="available", description="Simple single rooms at the lowest price point in the area.", contact_phone="+254700100009", source="mock"),
        Hostel(name="Mawingo Scholars Inn", area="Mawingo", latitude=-0.4110, longitude=36.9615, distance_from_campus_km=2.5, price_ksh=6800, verified=True, amenities=["wifi", "water", "security", "study room"], availability="limited", description="Includes a shared, quiet study room popular during exam season.", contact_phone="+254700100010", source="mock"),
        Hostel(name="Outspan Riverside", area="Outspan", latitude=-0.4305, longitude=36.9455, distance_from_campus_km=3.4, price_ksh=4200, verified=True, amenities=["water", "parking", "security"], availability="available", description="Scenic riverside location with a fenced compound.", contact_phone="+254700100011", source="mock"),
        Hostel(name="Ruring'u Campus Edge", area="Ruring'u", latitude=-0.4148, longitude=36.9545, distance_from_campus_km=0.7, price_ksh=7800, verified=True, amenities=["wifi", "water", "security", "furnished"], availability="available", description="Closest verified listing to the engineering block.", contact_phone="+254700100012", source="mock"),
    ]
    session.add_all(hostels)

    # --- Past papers (demo files) ---
    past_paper_specs = [
        (course_by_code["SCS 2101"], "2023/2024", 1, "main"),
        (course_by_code["SCS 2101"], "2022/2023", 1, "main"),
        (course_by_code["SCS 2205"], "2023/2024", 1, "main"),
        (course_by_code["SCS 3110"], "2023/2024", 1, "cat"),
        (course_by_code["SCS 3214"], "2022/2023", 2, "main"),
        (course_by_code["SIT 2102"], "2023/2024", 1, "supplementary"),
    ]
    for course, year, semester, exam_type in past_paper_specs:
        safe_year = year.replace("/", "-")
        file_name = f"{course.code.replace(' ', '')}_{safe_year}_S{semester}_{exam_type}.pdf"
        await storage.save(key=file_name, content=_placeholder_pdf(f"{course.code} {course.name}"), content_type="application/pdf")
        session.add(
            PastPaper(
                course_id=course.id,
                programme_id=course.programme_id,
                academic_year=year,
                semester=semester,
                exam_type=exam_type,
                file_reference=file_name,
                file_name=file_name,
            )
        )

    # --- Demo students ---
    demo_student = Student(
        registration_number="C026-01-0042/2022",
        full_name="Jane Wanjiru",
        email="jane.wanjiru@dekut.ac.ke",
        hashed_password=hash_password("Passw0rd!"),
        programme="BSc Computer Science",
        year_of_study=2,
        preferences={"housing_max_budget_ksh": 8000, "housing_area": "Boma"},
    )
    second_student = Student(
        registration_number="C026-01-0099/2023",
        full_name="Brian Mwangi",
        email="brian.mwangi@dekut.ac.ke",
        hashed_password=hash_password("Passw0rd!"),
        programme="BSc Information Technology",
        year_of_study=1,
        preferences={},
    )
    session.add_all([demo_student, second_student])
    await session.flush()

    # --- Demo complaint, so get_complaint_status has something to find ---
    session.add(
        Complaint(
            reference_code=generate_reference_code(),
            student_id=demo_student.id,
            category="maintenance",
            details="The tap in room B14 at Boma View Hostel has been leaking for three days.",
            location="Boma View Hostel, Room B14",
            status="in_review",
        )
    )

    await session.commit()
