from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts.verify_synthetic_planning import build_synthetic_catalog, run_verification
from src.calendar_versions import CalendarVersion
from src.models.data_manager_libretto import DataManagerLibretto
from src.models.data_manager_pazienti import DataManagerPazienti
from src.models.data_manager_sale_operatorie import DataManagerSaleOperatorie
from src.optimization import HighsSolver


@pytest.mark.skipif(not HighsSolver.is_available(), reason="highspy is unavailable")
def test_realistic_solve_and_actual_confirmation_preserve_legacy_history(tmp_path: Path) -> None:
    monday = date(2026, 10, 12)
    root = tmp_path / "data"
    build_synthetic_catalog(root, monday, 24)
    report = run_verification(root, monday, time_limit=300)
    assert report["written"] and report["scheduled"] > 1
    planned = DataManagerSaleOperatorie(root / "sale_operatorie")
    patients = DataManagerPazienti(root / "pazienti")
    books = DataManagerLibretto(root / "libretti")

    def activity_count() -> int:
        return sum(
            len(resident.get("attivita", [])) for resident in books.get_tutti_specializzandi()
        )

    def completed_count() -> int:
        return Counter(patient["stato"] for patient in patients.get_tutti_pazienti())["Completato"]

    original_activities = activity_count()
    original_completed = completed_count()
    planned.convalida_settimana(monday)
    assert activity_count() == original_activities
    assert completed_count() == original_completed
    planned_snapshot = {
        path: path.read_bytes() for path in (root / "sale_operatorie").glob("*.json")
    }
    actual = planned.for_version(CalendarVersion.EFFETTIVO)
    day = next(
        day for offset in range(5)
        if actual.get_operazioni((day := monday + timedelta(days=offset)).isoformat())
    ).isoformat()
    operations = actual.get_operazioni(day)
    removed_id = operations[0]["id_paziente"]
    actual.set_operazioni(day, operations[1:])

    assert patients.get_paziente_by_id(removed_id)["stato"] == "In Attesa"
    assert actual.get_stato_settimana(monday) == "BOZZA"
    actual.convalida_settimana(monday)

    assert actual.get_stato_settimana(monday) == "CONVALIDATO"
    assert activity_count() == original_activities + report["scheduled"] - 1
    assert completed_count() == original_completed + report["scheduled"] - 1
    assert all(path.read_bytes() == payload for path, payload in planned_snapshot.items())
