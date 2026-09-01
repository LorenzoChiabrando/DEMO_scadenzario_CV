from __future__ import annotations

import calendar
from datetime import date

from src.controllers.controller_scadenzario import (
    _duplicate_operating_room_assignments,
    _missing_operating_room_assignments,
)


def _complete_month(year: int, month: int) -> dict:
    _, days_in_month = calendar.monthrange(year, month)
    return {
        "turni": {
            current.isoformat(): {
                "Sala Op. I": "Alpha R.",
                "Sala Op. II": "Beta R.",
            }
            for day_number in range(1, days_in_month + 1)
            if (current := date(year, month, day_number)).weekday() < 5
        }
    }


def test_complete_month_can_pass_the_operating_room_gate() -> None:
    data = _complete_month(2026, 6)

    assert _missing_operating_room_assignments(data, 2026, 6) == []
    assert _duplicate_operating_room_assignments(data, 2026, 6) == []


def test_gate_reports_blank_weekday_assignments_but_ignores_weekends() -> None:
    data = _complete_month(2026, 6)
    data["turni"]["2026-06-01"]["Sala Op. I"] = "  "
    data["turni"]["2026-06-02"].pop("Sala Op. II")
    data["turni"]["2026-06-06"] = {}

    assert _missing_operating_room_assignments(data, 2026, 6) == [
        "2026-06-01: Sala Op. I",
        "2026-06-02: Sala Op. II",
    ]


def test_gate_rejects_the_same_specialist_in_both_physical_rooms() -> None:
    data = _complete_month(2026, 6)
    data["turni"]["2026-06-03"]["Sala Op. II"] = " alpha r. "

    assert _duplicate_operating_room_assignments(data, 2026, 6) == ["2026-06-03"]
