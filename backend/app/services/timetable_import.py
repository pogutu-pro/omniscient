"""Import a departmental teaching timetable spreadsheet.

DeKUT issues each department's timetable as a workbook whose main sheet is a
grid: rows are a day of the week times a year group, columns are the hour
from 07:00, and each cell holds "COURSE CODE - venue". A class that runs for
three hours is written **once, merged across the columns it occupies**, so the
merge is the only record of how long the session lasts. Underneath the grid
sits a course catalogue carrying each unit's full name, lecturer, weekly
hours and class size.

That shape has three consequences this module exists to handle:

* Merged cells are the session length, so a cell's value must be read from
  the merge anchor and its span taken from the merge's columns.
* The grid has no machine-readable course names or venues - "CCS 3208 RCL 1"
  is one string holding both, and the separator is inconsistent (`" - "`,
  `"-"`, or nothing at all).
* The grid says nothing about whether a session is a lecture, a lab or a
  tutorial, so the import does not guess: it labels everything `lecture`
  except sessions whose venue is explicitly online, and says so in the
  report.

Parsing (`parse_timetable_workbook`) does no database work, so the awkward
parts are testable without a session. Writing (`import_timetable`) is
idempotent: re-running against a corrected draft updates the same rows
instead of duplicating them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from openpyxl import load_workbook
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academics import Course, Programme, TimetableEntry
from app.services.term_calendar import trimester_from_label
DAY_NAMES = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
DAY_INDEX = {name: index for index, name in enumerate(DAY_NAMES)}

# "7AM-8AM", "12PM-1PM", "11AM - 12PM".
SLOT_PATTERN = re.compile(r"(\d{1,2})\s*(AM|PM)\s*[-–—]\s*(\d{1,2})\s*(AM|PM)", re.IGNORECASE)
# "YEAR 4.2", "YEAR 1.1 (CS)", "YEAR 2.2".
GROUP_PATTERN = re.compile(r"^YEAR\s*(\d)\s*\.\s*(\d)\s*(?:\(\s*([A-Za-z&]+)\s*\))?$", re.IGNORECASE)
# "YEAR 1 SEMESTER 1" - the catalogue's section heading.
SECTION_PATTERN = re.compile(r"^YEAR\s*(\d)\s+SEMESTER\s*(\d)$", re.IGNORECASE)
COURSE_CODE_PATTERN = re.compile(r"^[A-Z][A-Z& ]{1,15}\d{0,4}$")
# Used only when a grid cell names a code the catalogue never lists.
LOOSE_CODE_PATTERN = re.compile(r"^([A-Z]{2,4}\s?\d{3,4})\b")
CLASS_SIZE_PATTERN = re.compile(r"CLASS\s*SIZE\s*[-–:]\s*(\d+)", re.IGNORECASE)
DASHES = " \t-–—:,;"

# Grid cells that name a session rather than a course code. The capstone is
# written out in full where every other cell uses a code, and drops the
# roman numeral the catalogue uses for it.
CELL_ALIASES = {
    "CAPSTONE PROJECT 2": "CAPSTONE II",
}

# Venues spelled several ways across the sheet, mapped to one spelling. Keyed
# on the upper-cased, whitespace-collapsed cell text.
VENUE_ALIASES = {
    "ONLINE": "Online",
    "SEMINAR ROOM": "Seminar Room",
    "AUDITORIUM": "Auditorium",
    "FOOD SCIENCE WORKSHOP": "Food Science Workshop",
    "RCL1": "RCL 1",
    "RCL 1": "RCL 1",
    "RC 18": "RC 18",
    # The sheet's own placeholder, meaning "room not decided yet".
    "VENUE": "To be confirmed",
    "TO BE CONFIRMED": "To be confirmed",
    "TBC": "To be confirmed",
}

VENUE_NOT_DECIDED = "To be confirmed"


class TimetableImportError(Exception):
    """The file is not a teaching timetable this importer understands."""


@dataclass(frozen=True)
class ParsedCourse:
    code: str
    name: str
    year_of_study: int
    semester: int
    lecturer: str | None = None
    lecture_hours: int | None = None
    lab_hours: int | None = None
    class_size: int | None = None


@dataclass(frozen=True)
class ParsedSession:
    course_code: str
    day_of_week: int
    start_time: str
    end_time: str
    venue: str
    session_type: str
    year_group: str
    stream: str | None = None


@dataclass
class ParsedTimetable:
    academic_year: str
    term_label: str
    courses: list[ParsedCourse] = field(default_factory=list)
    sessions: list[ParsedSession] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # The trimester the term's dates actually correspond to in DeKUT's
    # three-trimester year. Kept beside the department's own cohort labels
    # rather than replacing them: a September-December sheet is officially
    # Semester 3, but the sheet may label its cohorts "Semester 1" or
    # "Semester 2", and the timetable students read is the sheet's.
    official_trimester: int | None = None


@dataclass
class ImportReport:
    academic_year: str
    term_label: str
    programme_code: str
    courses_created: int = 0
    courses_updated: int = 0
    sessions_created: int = 0
    sessions_updated: int = 0
    sessions_removed: int = 0
    sessions_without_a_catalogue_entry: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Which trimester of the three-trimester year this term is. Not the same
    # thing as the cohort semesters printed on the sheet.
    official_trimester: int | None = None

    def summary(self) -> str:
        trimester = f", Semester {self.official_trimester}" if self.official_trimester else ""
        return (
            f"{self.academic_year} ({self.term_label}{trimester}) -> {self.programme_code}: "
            f"{self.courses_created} course(s) created, {self.courses_updated} updated, "
            f"{self.sessions_created} session(s) created, {self.sessions_updated} updated"
            + (f", {self.sessions_removed} removed" if self.sessions_removed else "")
        )


def _squash(value: object) -> str:
    """Collapse all whitespace (including the non-breaking spaces the sheet
    is full of, e.g. "1.\\xa0\\xa0") into single spaces and strip the ends."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _to_24_hour(hour: int, meridiem: str) -> str:
    hour = hour % 12
    if meridiem.upper() == "PM":
        hour += 12
    return f"{hour:02d}:00"


def _parse_slot(label: str) -> tuple[str, str] | None:
    match = SLOT_PATTERN.search(label)
    if not match:
        return None
    # Both ends go through the same 12-hour conversion, because the two ends
    # of a slot can carry different meridiems: "11AM-12PM" ends at noon, and
    # adding 12 to the 12 would wrongly give midnight.
    return (
        _to_24_hour(int(match.group(1)), match.group(2)),
        _to_24_hour(int(match.group(3)), match.group(4)),
    )


def _canonical_venue(raw: str) -> str:
    """One spelling per venue.

    Anything containing a digit is a room code ("RC 18", "RCL 1") and is kept
    as the sheet wrote it; anything else is title-cased, so "food science
    workshop" and "FOOD SCIENCE WORKSHOP" both land on the same value and the
    venue filter has one option per room rather than three.
    """
    cleaned = raw.strip(" \t-–—")
    upper = cleaned.upper()
    if upper in VENUE_ALIASES:
        return VENUE_ALIASES[upper]
    if not cleaned:
        return VENUE_NOT_DECIDED
    if any(character.isdigit() for character in cleaned):
        return cleaned
    return " ".join(word.capitalize() for word in cleaned.split())


def _find_header(worksheet) -> tuple[int, dict[int, tuple[str, str]]]:
    """Locate the grid's header row and map each labelled column to its times.

    Returns the header row number and a column -> (start, end) map covering
    only the columns the sheet actually labels. A trailing merge on the last
    header cell (N10:O10 reading "6PM-7PM") is how the sheet fits the label on
    screen, not a seventh-to-eighth evening slot, so unlabelled columns are
    left out and a session reaching into one is clamped with a warning.
    """
    for row in range(1, min(worksheet.max_row, 60) + 1):
        if _squash(worksheet.cell(row=row, column=1).value).upper() != "DAY":
            continue
        if _squash(worksheet.cell(row=row, column=2).value).upper() != "GROUP":
            continue
        slots: dict[int, tuple[str, str]] = {}
        for column in range(3, worksheet.max_column + 1):
            parsed = _parse_slot(_squash(worksheet.cell(row=row, column=column).value))
            if parsed:
                slots[column] = parsed
        if not slots:
            raise TimetableImportError(
                f"Row {row} looks like the timetable header but none of its columns name a time slot."
            )
        return row, slots
    raise TimetableImportError(
        "No timetable grid found: expected a row with 'DAY' in column A and 'GROUP' in column B."
    )


def _merge_map(worksheet) -> dict[tuple[int, int], tuple[int, int, int]]:
    """Map every covered cell to (anchor row, first column, last column).

    The anchor holds the value; the first and last columns give the session's
    span across the hourly columns, which is the only place its duration is
    recorded.
    """
    covered: dict[tuple[int, int], tuple[int, int, int]] = {}
    for cell_range in worksheet.merged_cells.ranges:
        span = (cell_range.min_row, cell_range.min_col, cell_range.max_col)
        for row in range(cell_range.min_row, cell_range.max_row + 1):
            for column in range(cell_range.min_col, cell_range.max_col + 1):
                covered[(row, column)] = span
    return covered


def _value_at(worksheet, row: int, column: int, covered) -> object:
    anchor_row, first_column, _ = covered.get((row, column), (row, column, column))
    return worksheet.cell(row=anchor_row, column=first_column).value


def _text_at(worksheet, row: int, column: int, covered) -> str:
    return _squash(_value_at(worksheet, row, column, covered))


def _parse_group(label: str) -> tuple[str, str | None] | None:
    match = GROUP_PATTERN.match(label.strip())
    if not match:
        return None
    stream = match.group(3).upper() if match.group(3) else None
    return f"{int(match.group(1))}.{int(match.group(2))}", stream


def _split_session_cell(
    text: str, known_codes: dict[str, str], reference: str, warnings: list[str]
) -> tuple[str, str] | None:
    """Pull the course code and the venue out of one grid cell.

    The code is matched against the catalogue rather than guessed from a
    pattern, because the venue follows it with no reliable separator:
    "CCS 3208 RCL 1", "CCS 2211 - RC 18" and "IGS 3202 -ONLINE" are the same
    three fields written three ways.
    """
    cleaned = _squash(text)
    if not cleaned:
        return None
    upper = cleaned.upper()

    code: str | None = None
    remainder = ""
    if upper in CELL_ALIASES:
        code = CELL_ALIASES[upper]
    else:
        for candidate in known_codes:  # longest first, so "SMA 1105" beats "SMA"
            if upper == candidate or upper.startswith(f"{candidate} ") or upper.startswith(f"{candidate}-"):
                code = known_codes[candidate]
                remainder = cleaned[len(candidate) :]
                break

    if code is None:
        loose = LOOSE_CODE_PATTERN.match(upper)
        if not loose:
            warnings.append(f"{reference}: could not read a course code out of {cleaned!r}; session skipped.")
            return None
        code = loose.group(1)
        remainder = cleaned[loose.end() :]
        warnings.append(
            f"{reference}: {code!r} is not in the sheet's course catalogue; imported with no name, "
            "lecturer or class size."
        )

    # A note in brackets right after the code ("CCS 1101 (FS+MATHS)") marks the
    # other departments the unit is shared with, not the venue.
    remainder = re.sub(r"^\s*\([^)]*\)", " ", remainder)
    venue = _canonical_venue(remainder)
    if venue == VENUE_NOT_DECIDED:
        warnings.append(f"{reference}: no venue given for {code}; recorded as {VENUE_NOT_DECIDED!r}.")
    return code, venue


def _parse_catalogue(worksheet, covered, warnings: list[str]) -> list[ParsedCourse]:
    """Read the course catalogue under the grid.

    The sheet prints it as two side-by-side blocks - one for BSc Computer
    Science, one for the year 1 Computer Security & Forensics cohort - and the
    left block is offset down by one row from the right one, because the left
    block has a title line where the right one has its first course. Each
    block is therefore read on its own terms and merged afterwards.
    """
    right_block_class_size: int | None = None
    for row in range(1, min(worksheet.max_row, 80) + 1):
        for column in range(1, worksheet.max_column + 1):
            match = CLASS_SIZE_PATTERN.search(_squash(worksheet.cell(row=row, column=column).value))
            if match:
                right_block_class_size = int(match.group(1))
                break
        if right_block_class_size:
            break

    # code, name, lecture hours, lab hours, lecturer, class size
    blocks = ((2, 3, 5, 6, 7, 8), (9, 10, 12, 13, 14, None))
    by_code: dict[str, ParsedCourse] = {}
    year_of_study = semester = 0

    for row in range(1, worksheet.max_row + 1):
        section = _squash(worksheet.cell(row=row, column=1).value).upper()
        section_match = SECTION_PATTERN.match(section)
        if section_match:
            year_of_study, semester = int(section_match.group(1)), int(section_match.group(2))
            continue
        if not year_of_study:
            continue

        for code_col, name_col, lecture_col, lab_col, lecturer_col, size_col in blocks:
            code = _text_at(worksheet, row, code_col, covered).upper()
            name = _text_at(worksheet, row, name_col, covered)
            if not code or not name or not COURSE_CODE_PATTERN.match(code):
                continue
            course = ParsedCourse(
                code=code,
                name=name,
                year_of_study=year_of_study,
                semester=semester,
                lecturer=_text_at(worksheet, row, lecturer_col, covered) or None,
                lecture_hours=_as_int(_text_at(worksheet, row, lecture_col, covered)),
                lab_hours=_as_int(_text_at(worksheet, row, lab_col, covered)),
                class_size=_as_int(_text_at(worksheet, row, size_col, covered)) if size_col else right_block_class_size,
            )
            existing = by_code.get(code)
            if existing is None:
                by_code[code] = course
            elif existing.name != course.name:
                # The same unit is listed under both programmes, sometimes
                # with a different spelling of the name. The left block wins
                # because it carries the lecturer and class size, but the
                # discrepancy is worth a human's eyes rather than a silent
                # choice.
                warnings.append(
                    f"{code} is listed twice with different names: {existing.name!r} and {course.name!r}. "
                    f"Kept {existing.name!r}."
                )

    return sorted(by_code.values(), key=lambda course: (course.year_of_study, course.semester, course.code))


def _as_int(value: str) -> int | None:
    match = re.search(r"\d+", value or "")
    return int(match.group()) if match else None


def _academic_year_for(term_label: str) -> str:
    """Derive "2026/2027" from a term label like "SEPTEMBER - DECEMBER 2026".

    A September-December term opens the academic year it is named for; a
    January-August term is the second half of the year that began the year
    before.
    """
    year_match = re.search(r"(20\d{2})", term_label)
    if not year_match:
        raise TimetableImportError(
            f"Could not find a year in the term {term_label!r}; pass --academic-year explicitly."
        )
    year = int(year_match.group(1))
    opens_the_year = bool(re.search(r"SEPT|OCT|NOV|DEC", term_label, re.IGNORECASE))
    start = year if opens_the_year else year - 1
    return f"{start}/{start + 1}"


def parse_timetable_workbook(path: str, academic_year: str | None = None) -> ParsedTimetable:
    """Read a departmental timetable workbook into courses and sessions."""
    workbook = load_workbook(path, data_only=True)
    # The grid sheet is the one with a DAY/GROUP header; a departmental file
    # often carries per-cohort sheets alongside it.
    grid_sheet = covered = None
    header_row = 0
    slots: dict[int, tuple[str, str]] = {}
    for worksheet in workbook.worksheets:
        try:
            found_row, found_slots = _find_header(worksheet)
        except TimetableImportError:
            continue
        grid_sheet, header_row, slots = worksheet, found_row, found_slots
        covered = _merge_map(worksheet)
        break
    if grid_sheet is None:
        raise TimetableImportError(
            f"No sheet in {path!r} has a DAY/GROUP timetable grid. Sheets found: {workbook.sheetnames}"
        )
    assert covered is not None

    warnings: list[str] = []

    title_row = next(
        (
            row
            for row in range(1, header_row)
            if _squash(grid_sheet.cell(row=row, column=1).value).upper().startswith("TEACHING TIMETABLE")
        ),
        None,
    )
    raw_title = _squash(grid_sheet.cell(row=title_row, column=1).value) if title_row else ""
    term_label = re.sub(r"^TEACHING\s+TIMETABLE\s+FOR\s+", "", raw_title, flags=re.IGNORECASE)
    term_label = re.sub(r"\s+SEMESTER$", "", term_label, flags=re.IGNORECASE).strip()
    if not term_label:
        term_label = academic_year or "Unknown term"
    resolved_year = academic_year or _academic_year_for(term_label)

    courses = _parse_catalogue(grid_sheet, covered, warnings)
    known_codes = {course.code: course.code for course in sorted(courses, key=lambda c: -len(c.code))}
    if not known_codes:
        warnings.append(
            "No course catalogue found under the grid, so course codes and venues cannot be "
                "separated reliably; sessions will be imported with codes only."
        )

    sessions: list[ParsedSession] = []
    last_slot_column = max(slots)
    clamped_reported: set[str] = set()
    current_day: int | None = None

    for row in range(header_row + 1, grid_sheet.max_row + 1):
        day_text = _text_at(grid_sheet, row, 1, covered).upper()
        if day_text:
            if day_text in DAY_INDEX:
                current_day = DAY_INDEX[day_text]
            else:
                # The first non-weekday label in column A is the course
                # catalogue heading; everything below it is already read.
                break
        if current_day is None:
            continue

        group = _parse_group(_text_at(grid_sheet, row, 2, covered))
        if group is None:
            continue
        year_group, stream = group

        seen: set[tuple[int, int]] = set()
        for column in sorted(slots):
            text = _text_at(grid_sheet, row, column, covered)
            if not text:
                continue
            anchor_row, first_column, last_column = covered.get((row, column), (row, column, column))
            if (anchor_row, first_column) in seen:
                continue
            seen.add((anchor_row, first_column))

            reference = f"{grid_sheet.cell(row=anchor_row, column=first_column).coordinate}"
            if first_column not in slots:
                continue
            start = slots[first_column][0]
            if last_column > last_slot_column:
                end = slots[last_slot_column][1]
                if reference not in clamped_reported:
                    clamped_reported.add(reference)
                    warnings.append(
                        f"{reference} {text!r} is merged past the last labelled time slot, so it was "
                        f"read as {start}-{end}. Check it against the published timetable."
                    )
            else:
                end = slots[last_column][1]

            split = _split_session_cell(text, known_codes, reference, warnings)
            if split is None:
                continue
            code, venue = split
            sessions.append(
                ParsedSession(
                    course_code=code,
                    day_of_week=current_day,
                    start_time=start,
                    end_time=end,
                    venue=venue,
                    session_type="online" if venue == "Online" else "lecture",
                    year_group=year_group,
                    stream=stream,
                )
            )

    parsed = ParsedTimetable(
        academic_year=resolved_year,
        term_label=term_label,
        courses=courses,
        sessions=sessions,
        warnings=warnings,
        official_trimester=trimester_from_label(term_label, resolved_year),
    )
    parsed.warnings.extend(_trimester_warnings(parsed))
    parsed.warnings.extend(_clash_warnings(parsed))
    parsed.warnings.append(
        "The sheet does not say which sessions are lectures, labs or tutorials, so every session "
        "was imported as 'lecture' (online venues as 'online'). Set the real session types in the "
        "admin Academics panel."
    )
    return parsed


def _trimester_warnings(parsed: ParsedTimetable) -> list[str]:
    """Flag a sheet whose cohort numbering disagrees with the official calendar.

    DeKUT's year is three trimesters, so a September-December term is
    Semester 3. Departments do not always number their sheets that way - the
    September-December 2026 CS sheet files its cohorts under "SEMESTER 1" and
    "SEMESTER 2". Both are kept: the cohort label stays as printed, because
    that is the timetable students read, and the official trimester is
    recorded beside it. The warning exists so nobody has to guess which
    numbering a screen is showing.
    """
    trimester = parsed.official_trimester
    if trimester is None:
        return [
            f"Could not tell which trimester '{parsed.term_label}' falls in, so this term is not "
            "linked to the academic calendar. Rename the term on the sheet (e.g. 'SEPTEMBER - "
            "DECEMBER 2026') and re-import."
        ]
    printed = sorted(
        {course.semester for course in parsed.courses if 1 <= course.semester <= 3},
    )
    if printed and trimester not in printed:
        return [
            f"'{parsed.term_label}' is Semester {trimester} of {parsed.academic_year} in DeKUT's "
            f"three-trimester calendar, but the sheet numbers its cohorts Semester "
            f"{', '.join(str(s) for s in printed)}. The cohort labels were kept exactly as printed; "
            "the official trimester is recorded separately."
        ]
    return []


def _clash_warnings(parsed: ParsedTimetable) -> list[str]:
    """Two different units in the same slot for the same cohort is an error in
    the source, and it is invisible once the grid is flattened to a list."""
    occupied: dict[tuple[str, str | None, int, str], str] = {}
    warnings: list[str] = []
    for session in parsed.sessions:
        key = (session.year_group, session.stream, session.day_of_week, session.start_time)
        existing = occupied.get(key)
        if existing and existing != session.course_code:
            warnings.append(
                f"Year group {session.year_group}"
                f"{f' ({session.stream})' if session.stream else ''} has both {existing} and "
                f"{session.course_code} at {session.start_time} on "
                f"{DAY_NAMES[session.day_of_week].title()}."
            )
        occupied.setdefault(key, session.course_code)
    return warnings


async def import_timetable(
    session: AsyncSession,
    parsed: ParsedTimetable,
    programme_code: str,
    *,
    overwrite_course_detail: bool = False,
    prune: bool = False,
) -> ImportReport:
    """Write a parsed timetable into the database, idempotently.

    A course is matched on (programme, code) and a session on the cohort and
    slot it occupies, so re-running against a corrected draft corrects rows in
    place instead of doubling the timetable. Existing course detail is only
    filled in, never overwritten, unless asked - an admin who has corrected a
    lecturer's name should not have it reverted by the next import.
    """
    result = await session.execute(select(Programme).where(Programme.code == programme_code))
    programme = result.scalar_one_or_none()
    if programme is None:
        raise TimetableImportError(
            f"No programme with code {programme_code!r}. Create it first, or pass an existing code."
        )

    report = ImportReport(
        academic_year=parsed.academic_year,
        term_label=parsed.term_label,
        programme_code=programme_code,
        warnings=list(parsed.warnings),
        official_trimester=parsed.official_trimester,
    )

    existing_courses = {
        course.code: course
        for course in (
            await session.execute(select(Course).where(Course.programme_id == programme.id))
        )
        .scalars()
        .all()
    }

    for parsed_course in parsed.courses:
        course = existing_courses.get(parsed_course.code)
        if course is None:
            course = Course(
                programme_id=programme.id,
                code=parsed_course.code,
                name=parsed_course.name,
                year_of_study=parsed_course.year_of_study,
                semester=parsed_course.semester,
                lecturer=parsed_course.lecturer,
                lecture_hours=parsed_course.lecture_hours,
                lab_hours=parsed_course.lab_hours,
                class_size=parsed_course.class_size,
            )
            session.add(course)
            existing_courses[parsed_course.code] = course
            report.courses_created += 1
            continue

        # A year, semester or name correction is structural: a course filed
        # under the wrong year would show up under the wrong year group, and
        # the catalogue name is what the department prints on the timetable
        # students read, so a typo they have since fixed ("Discrete
        # Mathemeatics") must not outlive the draft that fixed it. These are
        # always brought into line, whatever --overwrite says.
        changed = (
            course.year_of_study != parsed_course.year_of_study
            or course.semester != parsed_course.semester
            or course.name != parsed_course.name
        )
        course.year_of_study = parsed_course.year_of_study
        course.semester = parsed_course.semester
        course.name = parsed_course.name
        # The rest is enrichment an admin is more likely to have adjusted on
        # purpose - a class size that changed mid-term, a substitute lecturer -
        # so it only fills a blank unless --overwrite is given.
        for field_name in ("lecturer", "lecture_hours", "lab_hours", "class_size"):
            incoming = getattr(parsed_course, field_name)
            if incoming is None:
                continue
            if overwrite_course_detail or getattr(course, field_name) in (None, ""):
                if getattr(course, field_name) != incoming:
                    setattr(course, field_name, incoming)
                    changed = True
        if changed:
            report.courses_updated += 1

    await session.flush()

    for parsed_session in parsed.sessions:
        course = existing_courses.get(parsed_session.course_code)
        if course is None:
            # The grid names a unit the catalogue never defines. Importing a
            # code with a blank name would render an empty card, so the code
            # is used as the name and the gap is reported.
            course = Course(
                programme_id=programme.id,
                code=parsed_session.course_code,
                name=parsed_session.course_code,
                year_of_study=int(parsed_session.year_group.split(".")[0]),
                semester=int(parsed_session.year_group.split(".")[1]),
            )
            session.add(course)
            existing_courses[parsed_session.course_code] = course
            report.sessions_without_a_catalogue_entry.append(parsed_session.course_code)

        stream_filter = (
            TimetableEntry.stream.is_(None)
            if parsed_session.stream is None
            else TimetableEntry.stream == parsed_session.stream
        )
        found = await session.execute(
            select(TimetableEntry).where(
                TimetableEntry.course_id == course.id,
                TimetableEntry.academic_year == parsed.academic_year,
                TimetableEntry.year_group == parsed_session.year_group,
                stream_filter,
                TimetableEntry.day_of_week == parsed_session.day_of_week,
                TimetableEntry.start_time == parsed_session.start_time,
            )
        )
        entry = found.scalar_one_or_none()
        if entry is None:
            session.add(
                TimetableEntry(
                    course_id=course.id,
                    day_of_week=parsed_session.day_of_week,
                    start_time=parsed_session.start_time,
                    end_time=parsed_session.end_time,
                    venue=parsed_session.venue,
                    session_type=parsed_session.session_type,
                    academic_year=parsed.academic_year,
                    semester=course.semester,
                    year_group=parsed_session.year_group,
                    stream=parsed_session.stream,
                )
            )
            report.sessions_created += 1
            continue

        if (entry.end_time, entry.venue, entry.session_type) != (
            parsed_session.end_time,
            parsed_session.venue,
            parsed_session.session_type,
        ):
            entry.end_time = parsed_session.end_time
            entry.venue = parsed_session.venue
            entry.session_type = parsed_session.session_type
            report.sessions_updated += 1

    if prune:
        report.sessions_removed = await _prune_absent_sessions(session, parsed)

    await session.commit()
    if report.sessions_without_a_catalogue_entry:
        unique = sorted(set(report.sessions_without_a_catalogue_entry))
        report.warnings.append(
            f"{len(unique)} unit(s) appear in the grid but not the catalogue and were imported with "
            f"their code as the name: {', '.join(unique)}."
        )
    return report


async def _prune_absent_sessions(session: AsyncSession, parsed: ParsedTimetable) -> int:
    """Drop this term's sessions for the imported cohorts that the sheet no
    longer lists, so a withdrawn class does not linger in the app.

    Only rows inside the imported term and the imported year groups are
    considered, so other cohorts' timetables are never touched.
    """
    expected: set[tuple[str, str | None, int, str]] = {
        (session.course_code, session.stream, session.day_of_week, session.start_time)
        for session in parsed.sessions
    }
    year_groups = {session.year_group for session in parsed.sessions}
    rows = (
        await session.execute(
            select(TimetableEntry, Course).join(Course, TimetableEntry.course_id == Course.id).where(
                TimetableEntry.academic_year == parsed.academic_year,
                TimetableEntry.year_group.in_(year_groups),
            )
        )
    ).all()

    stale_ids = [
        entry.id
        for entry, course in rows
        if (course.code, entry.stream, entry.day_of_week, entry.start_time) not in expected
    ]
    if stale_ids:
        await session.execute(delete(TimetableEntry).where(TimetableEntry.id.in_(stale_ids)))
    return len(stale_ids)
