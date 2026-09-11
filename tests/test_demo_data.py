from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts.reset_demo_data import (
    DEMO_PATIENT_NAMES,
    DEMO_RESIDENT_NAMES,
    build_demo_snapshot,
    reset_demo_data,
)
from src.importers.patient_csv import read_patient_csv
from src.models.data_manager import DataManager
from src.optimization import HighsSolver
from src.optimization.platform_service import plan_platform_week


@pytest.mark.parametrize(
    "reference",
    [
        date(2026, 9, 8),
        date(2026, 8, 31),
        date(2027, 1, 1),
        date(2028, 2, 29),
        date(2026, 9, 6),
    ],
)
def test_demo_is_deterministic_recent_and_has_consistent_links(reference: date) -> None:
    files = build_demo_snapshot(reference)
    assert files == build_demo_snapshot(reference)
    json_files = {path: json.loads(text) for path, text in files.items() if path.endswith(".json")}
    patients = {
        record["id"]: record for path, record in json_files.items() if path.startswith("pazienti/")
    }
    residents = {
        record["id"]: record for path, record in json_files.items() if path.startswith("libretti/")
    }
    assert len(patients) == 20
    assert len(residents) == 8
    assert all(record["dati_sintetici"] for record in [*patients.values(), *residents.values()])
    assert {(record["nome"], record["cognome"]) for record in patients.values()} == set(
        DEMO_PATIENT_NAMES
    )
    assert {(record["nome"], record["cognome"]) for record in residents.values()} == set(
        DEMO_RESIDENT_NAMES
    )
    assert ("Pippo", "VerdeScuro") in DEMO_PATIENT_NAMES
    assert ("Mandringo", "Bello") in DEMO_RESIDENT_NAMES
    resident_labels = {
        f"{resident['cognome']} {resident['nome'][0]}." for resident in residents.values()
    }
    assert len(resident_labels) == len(residents)
    planned_ids = set()
    for path, month in json_files.items():
        if not path.startswith("sale_operatorie/"):
            continue
        for day_string, daily in month["turni"].items():
            day = date.fromisoformat(day_string)
            assert abs((day - reference).days) < 63
            assert day.weekday() < 5
            assert set(daily["specializzandi"].values()) <= resident_labels
            starts = set()
            for operation in daily["operazioni"]:
                assert operation["id_paziente"] in patients
                assert operation["id_specializzando"] in residents
                assert operation["id_paziente"] not in planned_ids
                planned_ids.add(operation["id_paziente"])
                key = operation["sala_operatoria"], operation["ora_inizio"]
                assert key not in starts
                starts.add(key)
                patient = patients[operation["id_paziente"]]
                assert operation["nome_paziente"] == f"{patient['cognome']} {patient['nome']}"
                assert operation["specializzando"] in resident_labels
                assert operation["durata"] == sum(op["durata"] for op in patient["interventi"])
                if patient["stato"] == "Completato":
                    assert day < reference
                    resident = residents[operation["id_specializzando"]]
                    assert any(activity["data"] == day_string for activity in resident["attivita"])
                    assert any(
                        activity["nome_paziente"] == operation["nome_paziente"]
                        for activity in resident["attivita"]
                    )
                else:
                    assert day >= reference
    assert len(planned_ids) == 8
    for path, month in json_files.items():
        if not path.startswith("scadenzario/"):
            continue
        for day_string, daily in month["turni"].items():
            day = date.fromisoformat(day_string)
            monday = day - timedelta(days=day.weekday())
            assignments = [value for role, value in daily.items() if role != "Tipo Guardia"]
            assignments.append(month["giro_visite"][monday.isoformat()])
            assert len(set(assignments)) == len(assignments)
            assert set(assignments) <= resident_labels


def test_reset_preserves_old_files_in_a_private_backup(tmp_path: Path) -> None:
    old = tmp_path / "mock_data" / "pazienti" / "old.json"
    old.parent.mkdir(parents=True)
    old.write_text('{"dati_sintetici": true}', encoding="utf-8")
    backup = reset_demo_data(tmp_path, date(2026, 9, 8))
    assert backup is not None
    assert (backup / "pazienti" / "old.json").read_text() == '{"dati_sintetici": true}'
    assert not old.exists()
    assert len(read_patient_csv(tmp_path / "mock_data" / "test_inserimento_bulk.csv").rows) == 8
    assert len(list((tmp_path / "mock_data" / "pazienti").glob("*.json"))) == 20


def test_refreshed_demo_can_be_planned_after_roster_confirmation(tmp_path: Path) -> None:
    if not HighsSolver.is_available():
        pytest.skip("HiGHS unavailable")
    reset_demo_data(tmp_path, date(2026, 9, 8))
    roster = DataManager(
        str(tmp_path / "mock_data" / "scadenzario"),
        str(tmp_path / "mock_data" / "libretti"),
    )
    roster.set_stato_mese(2026, 9, "CONVALIDATO")
    run = plan_platform_week(tmp_path, date(2026, 9, 14))
    assert run.result.has_solution
    assert run.result.objective is not None
    assert len(run.result.schedule) == 13
    assert run.context.excluded_other_draft_count == 2
    assert run.write_receipt is None
