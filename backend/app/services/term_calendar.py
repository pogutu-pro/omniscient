"""DeKUT's trimester calendar.

DeKUT does not run a two-semester year. The academic year opens in September
and is divided into three trimesters of roughly four months each:

===========  =====================
Semester     Usual period
===========  =====================
Semester 1   January - April
Semester 2   May - August
Semester 3   September - December
===========  =====================

Two consequences run through the rest of the app:

1. An academic year is named after the September it opens in, so its
   Semester 3 falls in the *earlier* calendar year than Semesters 1 and 2.
   "2026/2027 Semester 3" is September-December **2026**.
2. A published departmental timetable does not always agree with the official
   numbering. The September-December 2026 CS sheet, for instance, files its
   cohorts under "SEMESTER 1" and "SEMESTER 2" while the official calendar
   calls the whole term Semester 3. Omniscient keeps the department's label
   (that is the timetable students actually read) and resolves the official
   trimester separately, rather than silently rewriting either one.

The *usual* periods are a rule and live here. The real start, end and
reporting dates are not a rule - they are announced per programme, school,
intake and year, and move when there is industrial action or another
disruption - so they are stored per term in the `academic_terms` table and
can be corrected by an admin. See `app.models.academics.AcademicTerm`.
"""
from __future__ import annotations

import datetime as dt
import re

# The department writes a cohort as a year of study and a semester, e.g.
# "4.2" or "Year 2.2". Kept here so the pattern has one definition.
YEAR_GROUP_PATTERN = re.compile(r"^(\d{1,2})[.\s](\d{1,2})$")

_MONTH_ABBREVIATIONS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)

# (trimester, first month, last month) in calendar terms. A trimester is
# allowed to wrap the year boundary so this stays three rows.
TRIMESTER_PERIODS: tuple[tuple[int, int, int], ...] = (
    (1, 1, 4),  # January - April
    (2, 5, 8),  # May - August
    (3, 9, 12),  # September - December
)

_LAST_DAY_OF_MONTH = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _days_in_month(year: int, month: int) -> int:
    if month == 2:
        # Leap year, without importing calendar for one expression.
        return 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28
    return _LAST_DAY_OF_MONTH[month]


def academic_year_for(month: dt.date | int) -> str:
    """The "2026/2027" label for a date, or for a month number.

    September onwards belongs to the year that opened that September;
    January-August still belongs to the one that opened the previous year.
    """
    if isinstance(month, dt.date):
        year, month_number = month.year, month.month
    else:
        year, month_number = dt.date.today().year, month
    opening = year if month_number >= 9 else year - 1
    return f"{opening}/{opening + 1}"


def opening_year_of(academic_year: str) -> int:
    """The calendar year an academic year opens in ("2026/2027" -> 2026)."""
    return int(str(academic_year).split("/")[0])


def trimester_for_month(month: int) -> int:
    """Which trimester a calendar month falls in."""
    for trimester, first, last in TRIMESTER_PERIODS:
        if first <= month <= last:
            return trimester
    raise ValueError(f"{month} is not a valid month number")


def current_trimester(today: dt.date | None = None) -> tuple[str, int]:
    """The academic year and trimester a date falls in."""
    day = today or dt.date.today()
    return academic_year_for(day), trimester_for_month(day.month)


def term_period(academic_year: str, trimester: int) -> tuple[dt.date, dt.date]:
    """The usual first and last day of a trimester.

    Deliberately the published pattern rather than confirmed dates: use
    `academic_terms` for the dates an admin has entered.
    """
    period = next((p for p in TRIMESTER_PERIODS if p[0] == trimester), None)
    if period is None:
        raise ValueError(f"DeKUT has no Semester {trimester}; the year has three trimesters")
    _, first_month, last_month = period
    opening = opening_year_of(academic_year)
    # Semesters 1 and 2 fall in the second calendar year, Semester 3 in the
    # first, because the year opened in September.
    year = opening if first_month >= 9 else opening + 1
    return dt.date(year, first_month, 1), dt.date(year, last_month, _days_in_month(year, last_month))


def trimester_from_label(label: str, academic_year: str) -> int | None:
    """The trimester a term title refers to, e.g. "SEPTEMBER - DECEMBER" -> 3.

    Returns `None` when the title names no recognisable period, so callers
    can report the ambiguity instead of guessing.
    """
    if not academic_year:
        return None
    # "Semester 2" / "Trimester 2" is explicit, so it wins over any month the
    # title happens to mention.
    numbered = re.search(r"\b(?:semester|trimester)\s*([123])\b", label.lower())
    if numbered:
        return int(numbered.group(1))
    haystack = label.lower()
    months = [index + 1 for index, name in enumerate(_MONTH_ABBREVIATIONS) if name in haystack]
    for name, month in (("sept", 9), ("oct", 10), ("nov", 11), ("dec", 12), ("aug", 8), ("jul", 7)):
        if name in haystack:
            months.append(month)
    for trimester, first, last in TRIMESTER_PERIODS:
        if any(first <= month <= last for month in months):
            return trimester
    return None


def parse_year_group(year_group: str) -> tuple[int, int] | None:
    """Split "4.2" into (4, 2). Returns `None` if it is not a cohort label."""
    match = YEAR_GROUP_PATTERN.match(str(year_group).strip())
    if not match:
        return None
    year_of_study, semester = int(match.group(1)), int(match.group(2))
    if not 1 <= year_of_study <= 9 or not 1 <= semester <= 3:
        return None
    return year_of_study, semester
