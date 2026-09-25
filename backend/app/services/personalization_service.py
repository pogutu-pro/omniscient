"""Controlled personalization.

Only a small, product-purposed set of fields is ever persisted to a
student's `preferences` (see models/student.py): their last housing
budget/area, and a couple of academic display prefs. There is no open-ended
memory dump, and nothing here can override an explicit value present in
the *current* request — see `resolve_housing_preferences` below, which is
the one rule this whole module exists to enforce.
"""
from __future__ import annotations

from dataclasses import dataclass

_ALLOWED_KEYS = {"housing_max_budget_ksh", "housing_area", "programme_code_display"}


@dataclass
class ResolvedValue:
    value: object
    source: str  # "current_request" | "remembered_preference" | "default"
    explanation: str


def sanitize_preferences(preferences: dict) -> dict:
    """Drop anything outside the allowed, documented preference keys."""
    return {k: v for k, v in preferences.items() if k in _ALLOWED_KEYS}


def resolve_housing_preferences(
    *, current_max_budget: int | None, current_area: str | None, remembered: dict
) -> tuple[ResolvedValue, ResolvedValue]:
    """Merge the current request with remembered preferences.

    An explicit value on the current request always wins, even if it
    contradicts what was remembered — e.g. a student who previously asked
    for hostels under KSh 8,000 but now asks for under KSh 12,000 gets
    12,000, not the older, cheaper preference.
    """
    if current_max_budget is not None:
        budget = ResolvedValue(current_max_budget, "current_request", "Using the budget you just gave.")
    elif "housing_max_budget_ksh" in remembered:
        budget = ResolvedValue(
            remembered["housing_max_budget_ksh"],
            "remembered_preference",
            f"Using your usual budget of KSh {remembered['housing_max_budget_ksh']:,} since none was given this time.",
        )
    else:
        budget = ResolvedValue(None, "default", "No budget constraint applied.")

    if current_area is not None:
        area = ResolvedValue(current_area, "current_request", "Using the area you just gave.")
    elif "housing_area" in remembered:
        area = ResolvedValue(
            remembered["housing_area"],
            "remembered_preference",
            f"Using your usual area ({remembered['housing_area']}) since none was given this time.",
        )
    else:
        area = ResolvedValue(None, "default", "No area constraint applied.")

    return budget, area


def preferences_from_housing_search(*, max_budget_ksh: int | None, area: str | None) -> dict:
    update: dict = {}
    if max_budget_ksh is not None:
        update["housing_max_budget_ksh"] = max_budget_ksh
    if area is not None:
        update["housing_area"] = area
    return update
