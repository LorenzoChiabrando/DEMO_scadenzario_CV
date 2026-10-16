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


_DAILY_ROLES = (
    "Reparto I",
    "Reparto II",
    "Sala Op. I",
    "Sala Op. II",
    "Day Hospital",
    "Day Surgery",
)
_ROTATION_REFERENCE = date(2026, 10, 16)


def _snapshot(reference: date) -> dict[str, dict]:
    files = build_demo_snapshot(reference)
    return {path: json.loads(text) for path, text in files.items() if path.endswith(".json")}


def _weekly_roster(month: dict) -> dict[date, dict[str, str]]:
    """Assegnazioni per settimana (lunedì -> ruolo -> sigla), uguali in tutti i giorni."""

    weeks: dict[date, dict[str, str]] = {}
    for day_string, daily in month["turni"].items():
        day = date.fromisoformat(day_string)
        monday = day - timedelta(days=day.weekday())
        roles = {role: daily[role] for role in _DAILY_ROLES}
        roles["Giro Visite"] = month["giro_visite"][monday.isoformat()]
        assert weeks.setdefault(monday, roles) == roles, f"turni diversi nella settimana {monday}"
    return weeks


def test_roster_rotates_every_resident_through_several_roles() -> None:
    month = _snapshot(_ROTATION_REFERENCE)["scadenzario/2026-10.json"]
    weeks = [roles for _monday, roles in sorted(_weekly_roster(month).items())]

    for previous, following in zip(weeks, weeks[1:], strict=False):
        assert all(previous[role] != following[role] for role in previous)
    roles_by_resident: dict[str, set[str]] = {}
    for roles in weeks:
        for role, label in roles.items():
            roles_by_resident.setdefault(label, set()).add(role)
    assert len(roles_by_resident) == len(DEMO_RESIDENT_NAMES)
    assert all(len(roles) >= 3 for roles in roles_by_resident.values())


def test_a_week_across_two_months_has_the_same_roster_in_both_files() -> None:
    files = _snapshot(_ROTATION_REFERENCE)
    september = _weekly_roster(files["scadenzario/2026-09.json"])
    october = _weekly_roster(files["scadenzario/2026-10.json"])

    assert september[date(2026, 9, 28)] == october[date(2026, 9, 28)]


@pytest.mark.parametrize("reference", [_ROTATION_REFERENCE, date(2026, 9, 8), date(2027, 1, 1)])
def test_operating_rooms_and_operations_follow_the_roster(reference: date) -> None:
    files = _snapshot(reference)
    residents = {
        f"{record['cognome']} {record['nome'][0]}.": record["id"]
        for path, record in files.items()
        if path.startswith("libretti/")
    }
    for path, month in files.items():
        if not path.startswith("sale_operatorie/"):
            continue
        roster = files[path.replace("sale_operatorie/", "scadenzario/")]
        for day_string, daily in month["turni"].items():
            shift = roster["turni"][day_string]
            assert daily["specializzandi"] == {
                "OR I": shift["Sala Op. I"],
                "OR II": shift["Sala Op. II"],
            }
            for operation in daily["operazioni"]:
                assert operation["specializzando"] == shift["Sala Op. I"]
                assert operation["id_specializzando"] == residents[shift["Sala Op. I"]]


def test_ward_round_extra_activities_belong_to_last_weeks_ward_round_resident() -> None:
    files = _snapshot(_ROTATION_REFERENCE)
    last_week = date(2026, 10, 5)
    on_ward_round = files["scadenzario/2026-10.json"]["giro_visite"][last_week.isoformat()]

    with_extra = [
        f"{record['cognome']} {record['nome'][0]}."
        for path, record in files.items()
        if path.startswith("libretti/") and record["attivita_extra"]
    ]
    assert with_extra == [on_ward_round]
