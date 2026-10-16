from __future__ import annotations

from datetime import date
from pathlib import Path

from src.models.data_manager import DataManager
from src.roster_month import (
    RESIDENT_ROLE_CODES,
    ROLE_KEYS,
    RosterMonth,
    load_roster_month,
    resident_rows,
)


def _manager(tmp_path: Path) -> DataManager:
    return DataManager(str(tmp_path / "scadenzario"), str(tmp_path / "libretti"))


def test_roles_follow_the_roster_order() -> None:
    assert ROLE_KEYS == (
        "Tipo Guardia",
        "Reparto I",
        "Reparto II",
        "Sala Op. I",
        "Sala Op. II",
        "Giro Visite",
        "Day Hospital",
        "Day Surgery",
    )


def test_month_snapshot_reads_cells_ward_round_and_state(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.set_valore_cella("2026-09-15", "Sala Op. I", "Rossi M.")
    manager.set_valore_cella("2026-09-15", "Tipo Guardia", "118")
    manager.set_giro_visite_settimana("2026-09-14", 2026, 9, "Bianchi A.")

    roster = load_roster_month(manager, 2026, 9)

    assert len(roster.dates) == 30
    assert roster.state == "BOZZA"
    assert roster.value(date(2026, 9, 15), "Sala Op. I") == "Rossi M."
    assert roster.value(date(2026, 9, 15), "Tipo Guardia") == "118"
    assert [roster.value(date(2026, 9, day), "Giro Visite") for day in range(14, 19)] == [
        "Bianchi A."
    ] * 5
    assert roster.value(date(2026, 9, 21), "Giro Visite") == ""


def test_weekends_and_unassigned_cells_are_empty(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.set_giro_visite_settimana("2026-09-14", 2026, 9, "Bianchi A.")

    roster = load_roster_month(manager, 2026, 9)

    assert roster.value(date(2026, 9, 19), "Giro Visite") == ""
    assert roster.value(date(2026, 9, 16), "Day Surgery") == ""
    assert not RosterMonth.is_workday(date(2026, 9, 19))
    assert RosterMonth.is_workday(date(2026, 9, 18))


_RESIDENTS = [
    {"id": "SP001", "nome": "Mario", "cognome": "Rossi", "stato": "Molinette"},
    {"id": "SP002", "nome": "Anna", "cognome": "Bianchi", "stato": "Molinette"},
    {"id": "SP003", "nome": "Luca", "cognome": "Verdi", "stato": "Altra Sede"},
]


def _september(values: dict) -> RosterMonth:
    return RosterMonth(2026, 9, "BOZZA", values)


def test_role_codes_cover_every_resident_role() -> None:
    assert RESIDENT_ROLE_CODES == {
        "Reparto I": "R1",
        "Reparto II": "R2",
        "Sala Op. I": "S1",
        "Sala Op. II": "S2",
        "Giro Visite": "GV",
        "Day Hospital": "DH",
        "Day Surgery": "DS",
    }


def test_resident_rows_list_active_residents_with_codes_and_totals() -> None:
    roster = _september(
        {
            (date(2026, 9, 15), "Sala Op. I"): "Rossi M.",
            (date(2026, 9, 16), "Reparto I"): "Rossi M.",
            (date(2026, 9, 15), "Tipo Guardia"): "118",
        }
    )

    rows = resident_rows(roster, _RESIDENTS)

    assert [row.label for row in rows] == ["Bianchi A.", "Rossi M."]
    rossi = rows[1]
    assert rossi.full_name == "Rossi Mario"
    assert rossi.codes[14] == "S1"
    assert rossi.codes[15] == "R1"
    assert rossi.codes[16] == ""
    assert rossi.total == 2
    assert rows[0].total == 0
    assert len(rossi.codes) == 30


def test_inactive_resident_present_in_the_month_is_still_listed() -> None:
    roster = _september({(date(2026, 9, 15), "Day Hospital"): "Verdi L."})

    rows = resident_rows(roster, _RESIDENTS)

    verdi = next(row for row in rows if row.label == "Verdi L.")
    assert verdi.codes[14] == "DH"
    assert verdi.total == 1


def test_two_roles_on_the_same_day_are_joined_and_both_counted() -> None:
    roster = _september(
        {
            (date(2026, 9, 15), "Reparto I"): "Rossi M.",
            (date(2026, 9, 15), "Sala Op. I"): "rossi m.",
        }
    )

    rossi = next(row for row in resident_rows(roster, _RESIDENTS) if row.label == "Rossi M.")

    assert rossi.codes[14] == "R1+S1"
    assert rossi.total == 2
