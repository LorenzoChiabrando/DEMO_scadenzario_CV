"""Synthetic end-to-end checks of planned and performed calendar boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.calendar_versions import CalendarVersion, CalendarVersionError
from src.controllers.controller_libretto import ControllerLibretto
from src.controllers.controller_scadenzario import ControllerScadenzario
from src.models.data_manager import DataManager
from src.models.data_manager_libretto import DataManagerLibretto
from src.models.data_manager_sale_operatorie import DataManagerSaleOperatorie
from src.models.patient_plan_state import read_operational_plan_months
from src.optimization import HighsSolver, SolveStatus
from src.optimization.exceptions import PlatformPersistenceError
from src.optimization.platform_io import load_platform_context, persist_platform_week_plan
from src.optimization.platform_mapping import PlatformDayPlan, PlatformWeekPlan
from src.optimization.platform_service import plan_platform_week
from src.optimization.solver import HighsConfig
from src.planning_schema import OPTIMIZATION_KEY
from src.views.components import messages

WEEKS = (date(2026, 5, 4), date(2026, 9, 28), date(2026, 12, 28))


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _snapshot(directory: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in sorted(directory.rglob("*.json"))}


def _operation(patient_id: str = "P1", resident_id: str = "R1") -> dict:
    return {
        "id_paziente": patient_id,
        "nome_paziente": f"Synthetic {patient_id}",
        "intervento": "Synthetic procedure",
        "codice_intervento": "SYN-A",
        "ora_inizio": "08:00",
        "ora_fine": "09:00",
        "durata": 60,
        "sala_operatoria": "OR-1",
        "id_specializzando": resident_id,
        "specializzando": "Alpha T." if resident_id == "R1" else "Beta T.",
        "ruolo_specializzando": "OR I",
    }


@dataclass(slots=True)
class _Catalog:
    root: Path
    data: Path
    schedule: DataManager
    rooms: DataManagerSaleOperatorie
    books: DataManagerLibretto

    def patient(self, patient_id: str) -> dict:
        return _read(self.data / "pazienti" / f"{patient_id}.json")

    def add_week(self, monday: date) -> None:
        for offset in range(5):
            day = (monday + timedelta(days=offset)).isoformat()
            self.schedule.set_valore_cella(day, "Sala Op. I", "Alpha T.")
            self.schedule.set_valore_cella(day, "Sala Op. II", "Beta T.")
            self.rooms.set_specializzandi(day, "Alpha T.", "Beta T.")

    def confirm_schedule(self) -> None:
        for year, month in self.schedule.get_mesi_disponibili():
            self.schedule.convalida_mese(year, month)


@pytest.fixture
def catalog(tmp_path: Path) -> _Catalog:
    root = tmp_path / "synthetic-platform"
    data = root / "mock_data"
    for patient_id in ("P1", "P2"):
        _write(
            data / "pazienti" / f"{patient_id}.json",
            {
                "id": patient_id,
                "nome": patient_id,
                "cognome": "Synthetic",
                "diagnosi": "Synthetic diagnosis",
                "codice_intervento": "SYN-A",
                "descrizione_intervento": "Synthetic procedure",
                "interventi": [],
                "durata_intervento": 60,
                "tipo_chirurgia": "Aperta",
                "complessita": "Media",
                "urgenza": "Media",
                "stato": "In Attesa",
                "data_inserimento": "01/01/2026",
                OPTIMIZATION_KEY: {
                    "versione_schema": 1,
                    "categoria_paper": "I'",
                    "attesa_massima_giorni": 365,
                },
            },
        )
    for resident_id, surname in (("R1", "Alpha"), ("R2", "Beta")):
        _write(
            data / "libretti" / f"{resident_id}.json",
            {
                "id": resident_id,
                "nome": "Test",
                "cognome": surname,
                "livello": "Junior",
                "stato": "Molinette",
            },
        )
    return _Catalog(
        root,
        data,
        DataManager(data / "scadenzario", dir_libretti=data / "libretti"),
        DataManagerSaleOperatorie(data / "sale_operatorie", dir_pazienti=data / "pazienti"),
        DataManagerLibretto(data / "libretti"),
    )


@pytest.mark.parametrize("monday", WEEKS, ids=("same-month", "cross-month", "cross-year"))
def test_confirmations_complete_only_actual_operations(catalog: _Catalog, monday: date) -> None:
    catalog.add_week(monday)
    friday = monday + timedelta(days=4)
    catalog.rooms.set_operazioni(monday.isoformat(), [_operation("P2")])
    catalog.rooms.set_operazioni(friday.isoformat(), [_operation()])
    patient_before = catalog.patient("P1")
    books_before = _snapshot(catalog.data / "libretti")

    catalog.confirm_schedule()
    assert catalog.patient("P1") == patient_before
    assert _snapshot(catalog.data / "libretti") == books_before
    catalog.rooms.convalida_settimana(monday)

    actual = catalog.rooms.for_version(CalendarVersion.EFFETTIVO)
    frozen = {
        path: path.read_bytes() for path in (catalog.data / "sale_operatorie").glob("*.json")
    }
    assert catalog.rooms.get_stato_settimana(monday) == "CONVALIDATO"
    assert actual.get_stato_settimana(monday) == "BOZZA"
    assert actual.get_operazioni(friday.isoformat()) == [_operation()]
    assert catalog.patient("P1")["stato"] == "Pianificato"
    assert catalog.patient("P2")["stato"] == "Pianificato"
    assert _snapshot(catalog.data / "libretti") == books_before

    actual.set_operazioni(monday.isoformat(), [])
    actual.set_operazioni(friday.isoformat(), [_operation(resident_id="R2")])
    assert catalog.patient("P2")["stato"] == "In Attesa"
    assert catalog.rooms.get_pianificazioni_pazienti() == {"P1": (friday,)}
    assert _snapshot(catalog.data / "libretti") == books_before

    # A fresh manager must observe the same copy and confirmation state after restart.
    actual = DataManagerSaleOperatorie(
        catalog.data / "sale_operatorie", version=CalendarVersion.EFFETTIVO
    )
    actual.convalida_settimana(monday)
    assert catalog.patient("P1") == {**patient_before, "stato": "Completato"}
    assert catalog.patient("P2")["stato"] == "In Attesa"
    assert actual.get_stato_settimana(monday) == "CONVALIDATO"
    assert catalog.books.get_attivita("R1") == []
    activities = catalog.books.get_attivita("R2")
    assert [(item["id_paziente"], item["data"]) for item in activities] == [
        ("P1", friday.isoformat())
    ]
    assert catalog.rooms.get_pianificazioni_pazienti() == {}
    assert {path: path.read_bytes() for path in frozen} == frozen
    final = _snapshot(catalog.data)
    with pytest.raises(CalendarVersionError):
        actual.convalida_settimana(monday)
    with pytest.raises(CalendarVersionError):
        actual.set_operazioni(friday.isoformat(), [])
    assert _snapshot(catalog.data) == final


@pytest.mark.parametrize("monday", WEEKS, ids=("same-month", "cross-month", "cross-year"))
def test_actual_reservations_exclude_solver_candidates_and_removal_releases_them(
    catalog: _Catalog, monday: date
) -> None:
    target_week = monday + timedelta(days=7)
    friday = monday + timedelta(days=4)
    catalog.add_week(monday)
    catalog.add_week(target_week)
    catalog.confirm_schedule()
    catalog.rooms.set_operazioni(friday.isoformat(), [_operation()])
    catalog.rooms.convalida_settimana(monday)
    actual = catalog.rooms.for_version(CalendarVersion.EFFETTIVO)
    frozen = catalog.rooms.get_operazioni(friday.isoformat())

    before_reads = _snapshot(catalog.data)
    context = load_platform_context(catalog.root, target_week, data_directory=catalog.data)
    assert set(context.patient_records) == {"P2"}
    assert context.excluded_other_draft_count == 1
    for manager in (catalog.rooms, actual):
        assert manager.get_pazienti_pianificati_ids() == {"P1"}
        assert manager.get_pazienti_pianificati_ids(exclude_lun_date=monday) == set()
    assert _snapshot(catalog.data) == before_reads

    actual.set_operazioni(friday.isoformat(), [])
    context = load_platform_context(catalog.root, target_week, data_directory=catalog.data)
    assert set(context.patient_records) == {"P1", "P2"}
    assert context.excluded_other_draft_count == 0
    assert catalog.patient("P1")["stato"] == "In Attesa"
    assert catalog.rooms.get_operazioni(friday.isoformat()) == frozen
    operational = read_operational_plan_months(catalog.data / "sale_operatorie")
    assert operational[friday.strftime("%Y-%m")]["turni"][friday.isoformat()]["operazioni"] == []


def test_removal_from_actual_keeps_a_reservation_in_an_uninitialized_planned_week(
    catalog: _Catalog,
) -> None:
    monday = WEEKS[1]
    next_week = monday + timedelta(days=7)
    catalog.add_week(monday)
    catalog.add_week(next_week)
    catalog.rooms.set_operazioni(monday.isoformat(), [_operation()])
    catalog.rooms.set_operazioni(next_week.isoformat(), [_operation()])
    catalog.rooms.convalida_settimana(monday)
    actual = catalog.rooms.for_version(CalendarVersion.EFFETTIVO)

    actual.set_operazioni(monday.isoformat(), [])
    assert not actual.has_settimana(next_week)
    assert catalog.patient("P1")["stato"] == "Pianificato"
    assert actual.get_pianificazioni_pazienti() == {"P1": (next_week,)}
    catalog.rooms.set_operazioni(next_week.isoformat(), [])
    assert catalog.patient("P1")["stato"] == "In Attesa"


@pytest.mark.parametrize("monday", WEEKS, ids=("same-month", "cross-month", "cross-year"))
def test_solver_input_stays_planned_after_actual_schedule_correction(
    catalog: _Catalog, monday: date
) -> None:
    catalog.add_week(monday)
    catalog.confirm_schedule()
    original = load_platform_context(catalog.root, monday, data_directory=catalog.data)
    planned_before = {
        path: path.read_bytes() for path in (catalog.data / "scadenzario").glob("*.json")
    }
    actual = catalog.schedule.for_version(CalendarVersion.EFFETTIVO)
    friday = monday + timedelta(days=4)
    actual.set_valore_cella(friday.isoformat(), "Sala Op. I", "Beta T.")
    actual.set_valore_cella(friday.isoformat(), "Sala Op. II", "Alpha T.")
    month = actual.load_mese(friday.year, friday.month)
    month[OPTIMIZATION_KEY]["capacita_sessioni"] = {friday.isoformat(): {"OR-1": 120}}
    actual.save_mese(friday.year, friday.month, month)
    before_read = _snapshot(catalog.data)

    corrected = load_platform_context(catalog.root, monday, data_directory=catalog.data)
    assert corrected.scheduling_input == original.scheduling_input
    assert corrected.roster_by_day == original.roster_by_day
    assert {path: path.read_bytes() for path in planned_before} == planned_before
    assert _snapshot(catalog.data) == before_read


@pytest.mark.skipif(not HighsSolver.is_available(), reason="highspy is unavailable")
def test_highs_persists_only_planned_then_actual_confirmation_records_once(
    catalog: _Catalog, tmp_path: Path
) -> None:
    monday = WEEKS[2]
    other_week = monday + timedelta(days=7)
    catalog.add_week(monday)
    catalog.add_week(other_week)
    catalog.confirm_schedule()
    catalog.rooms.set_operazioni(other_week.isoformat(), [_operation("P2")])
    catalog.rooms.convalida_settimana(other_week)
    actual_before = _snapshot(catalog.data / "sale_operatorie" / "effettivo")
    books_before = _snapshot(catalog.data / "libretti")
    schedule_before = _snapshot(catalog.data / "scadenzario")

    run = plan_platform_week(
        catalog.root,
        monday,
        persist=True,
        data_directory=catalog.data,
        backup_directory=tmp_path / "synthetic-backup",
        solver_config=HighsConfig(time_limit_seconds=300, validate_solution=True),
    )

    assert run.result.status is SolveStatus.OPTIMAL
    assert run.result.termination_condition == "TerminationCondition.optimal"
    assert [item.patient_id for item in run.result.schedule] == ["P1"]
    assert run.context.excluded_other_draft_count == 1
    assert run.result.objective is not None
    objective = run.result.objective
    data = run.context.scheduling_input
    assert objective.weighted_total == pytest.approx(
        data.efficiency_scale * objective.treatment_efficiency
        + data.objective_weights.fairness * objective.fairness_floor
        - data.objective_weights.unassigned_penalty * objective.unassigned_count,
        abs=1e-8,
    )
    assert run.result.best_objective_bound == pytest.approx(objective.weighted_total, abs=1e-8)
    assert run.write_receipt is not None
    assert all("effettivo" not in path.parts for path in run.write_receipt.updated_paths)
    assert _snapshot(catalog.data / "sale_operatorie" / "effettivo") == actual_before
    assert _snapshot(catalog.data / "libretti") == books_before
    assert _snapshot(catalog.data / "scadenzario") == schedule_before
    assert catalog.patient("P1")["stato"] == "Pianificato"
    assert catalog.patient("P2")["stato"] == "Pianificato"

    catalog.rooms.convalida_settimana(monday)
    assert _snapshot(catalog.data / "libretti") == books_before
    actual = catalog.rooms.for_version(CalendarVersion.EFFETTIVO)
    actual.convalida_settimana(monday)
    assert catalog.patient("P1")["stato"] == "Completato"
    assert catalog.patient("P2")["stato"] == "Pianificato"
    assert sum(len(catalog.books.get_attivita(identifier)) for identifier in ("R1", "R2")) == 1
    final = _snapshot(catalog.data)
    with pytest.raises(PlatformPersistenceError, match="già convalidata"):
        persist_platform_week_plan(
            catalog.root,
            run.plan,
            overwrite=True,
            backup_directory=tmp_path / "synthetic-backup",
            data_directory=catalog.data,
        )
    assert _snapshot(catalog.data) == final


def test_writer_preserves_actual_weeks_in_the_same_month(catalog: _Catalog, tmp_path: Path) -> None:
    monday = WEEKS[0]
    other_week = monday + timedelta(days=7)
    catalog.add_week(monday)
    catalog.add_week(other_week)
    catalog.confirm_schedule()
    catalog.rooms.convalida_settimana(other_week)
    context = load_platform_context(catalog.root, monday, data_directory=catalog.data)
    plan = PlatformWeekPlan(
        monday,
        tuple(
            PlatformDayPlan(day, (_operation(),) if day == monday else (), roster)
            for day, roster in context.roster_by_day.items()
        ),
    )
    before = _snapshot(catalog.data / "sale_operatorie" / "effettivo")
    receipt = persist_platform_week_plan(
        catalog.root,
        plan,
        overwrite=False,
        backup_directory=tmp_path / "synthetic-backup",
        data_directory=catalog.data,
    )
    assert _snapshot(catalog.data / "sale_operatorie" / "effettivo") == before
    assert catalog.rooms.get_operazioni(monday.isoformat()) == [_operation()]
    assert catalog.patient("P1")["stato"] == "Pianificato"
    assert {path.parent for path in receipt.updated_paths} == {
        catalog.data / "sale_operatorie", catalog.data / "pazienti"
    }


@pytest.mark.parametrize("selected_version", tuple(CalendarVersion))
def test_libretto_uses_actual_assignments_independently_of_selected_calendars(
    catalog: _Catalog, selected_version: CalendarVersion
) -> None:
    monday = WEEKS[1]
    friday = monday + timedelta(days=4)
    catalog.add_week(monday)
    catalog.schedule.set_valore_cella(friday.isoformat(), "Reparto I", "Alpha T.")
    catalog.rooms.set_operazioni(friday.isoformat(), [_operation()])
    catalog.confirm_schedule()
    catalog.rooms.convalida_settimana(monday)
    actual_rooms = catalog.rooms.for_version(CalendarVersion.EFFETTIVO)
    actual_schedule = catalog.schedule.for_version(CalendarVersion.EFFETTIVO)
    actual_rooms.set_specializzandi(friday.isoformat(), "Beta T.", "")
    actual_rooms.set_operazioni(friday.isoformat(), [_operation(resident_id="R2")])
    actual_schedule.set_valore_cella(friday.isoformat(), "Reparto I", "Beta T.")
    controller = ControllerLibretto.__new__(ControllerLibretto)
    controller.model = catalog.books
    controller.model_scad = catalog.schedule.for_version(selected_version)
    controller.model_sale_op = catalog.rooms.for_version(selected_version)
    alpha = catalog.books.get_specializzando_by_id("R1")
    beta = catalog.books.get_specializzando_by_id("R2")
    before = _snapshot(catalog.data)

    assert not any(
        item["data"] == friday.isoformat() for item in controller._get_pianificate(alpha)
    )
    beta_friday = [
        item for item in controller._get_pianificate(beta) if item["data"] == friday.isoformat()
    ]
    assert {item["sede"] for item in beta_friday} == {"Reparto", "Sala Operatoria"}
    assert controller._get_completate(beta) == []
    assert _snapshot(catalog.data) == before

    actual_rooms.convalida_settimana(monday)
    completed = controller._get_completate(beta)
    planned = controller._get_pianificate(beta)
    assert len(completed) == 1
    assert completed[0]["id_paziente"] == "P1"
    assert not any(
        item["data"] == friday.isoformat() and item["sede"] == "Sala Operatoria"
        for item in planned
    )
    assert any(
        item["data"] == friday.isoformat() and item["sede"] == "Reparto" for item in planned
    )


@pytest.mark.parametrize("surgery", (True, False), ids=("surgery", "manual-non-surgery"))
def test_manual_libretto_confirmation_is_restricted_to_non_surgical_activities(
    catalog: _Catalog, surgery: bool
) -> None:
    monday = WEEKS[0]
    catalog.add_week(monday)
    catalog.schedule.set_valore_cella(monday.isoformat(), "Reparto I", "Alpha T.")
    catalog.rooms.set_operazioni(monday.isoformat(), [_operation()])
    catalog.confirm_schedule()
    catalog.rooms.convalida_settimana(monday)
    callbacks = {}

    def populate(*_args: object, **kwargs: object) -> None:
        callbacks.update(kwargs)

    controller = ControllerLibretto.__new__(ControllerLibretto)
    controller.model = catalog.books
    controller.model_scad = catalog.schedule
    controller.model_sale_op = catalog.rooms
    controller._spec_corrente = catalog.books.get_specializzando_by_id("R1")
    controller._categoria_corrente = "pianificate"
    controller._popola_lista_attivita = lambda _category: None
    controller.view = SimpleNamespace(
        popola_dettaglio_giorno=populate,
        stacked_widget=SimpleNamespace(setCurrentIndex=lambda _index: None),
    )
    source = next(
        item
        for item in controller._get_pianificate(controller._spec_corrente)
        if item["data"] == monday.isoformat()
        and item["sede"] == ("Sala Operatoria" if surgery else "Reparto")
    )
    controller.apri_dettaglio_giorno(monday.isoformat(), [source])
    callbacks["on_save"](
        {
            "data": source["data"],
            "sede": source["sede"],
            "attivita": source["attivita"],
            "ruolo": source["ruolo"],
            "ora_inizio": "08:00",
            "ora_fine": "18:00",
            "note": "Synthetic manual confirmation",
            "tipo": "extra",
        }
    )

    assert catalog.patient("P1")["stato"] == "Pianificato"
    count_before_actual = len(controller._get_completate(controller._spec_corrente))
    catalog.rooms.for_version(CalendarVersion.EFFETTIVO).convalida_settimana(monday)
    count_after_actual = len(controller._get_completate(controller._spec_corrente))
    assert (count_before_actual, count_after_actual) == ((0, 1) if surgery else (1, 2))


def test_actual_confirmation_resolves_a_valid_compound_surname(catalog: _Catalog) -> None:
    monday = WEEKS[0]
    resident_path = catalog.data / "libretti" / "R1.json"
    _write(resident_path, {**_read(resident_path), "cognome": "De Synthetic"})
    catalog.add_week(monday)
    for offset in range(5):
        day = (monday + timedelta(days=offset)).isoformat()
        catalog.schedule.set_valore_cella(day, "Sala Op. I", "De Synthetic T.")
        catalog.rooms.set_specializzandi(day, "De Synthetic T.", "Beta T.")
    catalog.rooms.set_operazioni(
        monday.isoformat(), [{**_operation(), "specializzando": "De Synthetic T."}]
    )
    catalog.confirm_schedule()
    context = load_platform_context(catalog.root, monday, data_directory=catalog.data)
    assert context.roster_by_day[monday][0].resident_id == "R1"
    catalog.rooms.convalida_settimana(monday)

    catalog.rooms.for_version(CalendarVersion.EFFETTIVO).convalida_settimana(monday)

    assert catalog.patient("P1")["stato"] == "Completato"
    assert len(catalog.books.get_attivita("R1")) == 1
    assert catalog.books.get_attivita("R1")[0]["id_paziente"] == "P1"


def test_editing_one_actual_room_cannot_overwrite_the_other_assigned_room(
    catalog: _Catalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    monday = WEEKS[0]
    day = monday.isoformat()
    catalog.add_week(monday)
    for identifier, surname in (("R3", "Gamma"), ("R4", "Delta")):
        _write(
            catalog.data / "libretti" / f"{identifier}.json",
            {"id": identifier, "nome": "Test", "cognome": surname, "livello": "Junior"},
        )
    operation = {
        **_operation(resident_id="R2"),
        "sala_operatoria": "OR-2",
        "ruolo_specializzando": "OR II",
    }
    catalog.rooms.set_operazioni(day, [operation])
    catalog.confirm_schedule()
    actual_rooms = catalog.rooms.for_version(CalendarVersion.EFFETTIVO)
    actual_schedule = catalog.schedule.for_version(CalendarVersion.EFFETTIVO)
    warnings = []
    monkeypatch.setattr(
        messages, "show_message", lambda _parent, title, _text, **_kwargs: warnings.append(title)
    )
    controller = ControllerScadenzario.__new__(ControllerScadenzario)
    controller.model = actual_schedule
    controller.model_sale_op = actual_rooms
    controller.versione_corrente = CalendarVersion.EFFETTIVO
    controller.modalita_corrente = "STORICO"
    controller.anno_corrente, controller.mese_corrente = monday.year, monday.month
    controller.aggiorna_tabella = lambda: None
    controller.view = SimpleNamespace(
        row_labels=["Giorno", "Tipo Guardia", "Sala Op. I", "Sala Op. II"],
    )

    # This edit is allowed while there is no actual room week to synchronize.
    controller.assegna(3, monday.day - 1, "Gamma T.")
    assert actual_schedule.get_valore_cella(day, "Sala Op. II") == "Gamma T."
    assert not actual_rooms.has_settimana(monday)
    catalog.rooms.convalida_settimana(monday)
    assert actual_rooms.load_mese(monday.year, monday.month)["turni"][day]["specializzandi"][
        "OR II"
    ] == "Beta T."

    # Editing room I must not overwrite room II's independently assigned operation.
    controller.assegna(2, monday.day - 1, "Delta T.")

    assert actual_rooms.load_mese(monday.year, monday.month)["turni"][day]["specializzandi"][
        "OR II"
    ] == "Beta T."
    assert actual_rooms.get_operazioni(day) == [operation]
    actual_rooms.convalida_settimana(monday)
    assert len(catalog.books.get_attivita("R2")) == 1
    assert catalog.books.get_attivita("R3") == []
