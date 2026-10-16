from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from src.calendar_versions import CalendarVersion
from src.controllers.controller_sale_operatorie import ControllerSaleOperatorie
from src.models.data_manager import DataManager
from src.models.data_manager_libretto import DataManagerLibretto
from src.models.data_manager_pazienti import DataManagerPazienti
from src.models.data_manager_sale_operatorie import DataManagerSaleOperatorie
from src.planning_schema import OPTIMIZATION_KEY
from src.views.view_sale_operatorie import ViewSaleOperatorie

MONDAY = date(2026, 9, 28)
FRIDAY = MONDAY + timedelta(days=4)


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*.json")}


@pytest.fixture
def calendar(tmp_path: Path, qt_app: QApplication):
    _write_json(tmp_path / "pazienti/PZ001.json", {
        "id": "PZ001", "nome": "Synthetic", "cognome": "Case", "stato": "In Attesa",
        "data_inserimento": "01/01/2024", "durata_intervento": 60, "urgenza": "Media",
    })
    _write_json(tmp_path / "libretti/SP001.json", {
        "id": "SP001", "nome": "Resident", "cognome": "Test", "attivita": [],
    })
    plans = DataManagerSaleOperatorie(tmp_path / "sale_operatorie")
    plans.set_operazioni(MONDAY.isoformat(), [{
        "id_paziente": "PZ001", "nome_paziente": "Case Synthetic", "durata": 60,
        "ora_inizio": "08:00", "ora_fine": "09:00", "sala_operatoria": "OR-1",
        "id_specializzando": "SP001", "specializzando": "Test R.",
        "ruolo_specializzando": "OR I", "intervento": "Synthetic procedure",
    }])
    view = ViewSaleOperatorie()
    controller = ControllerSaleOperatorie(
        view, plans, DataManager(tmp_path / "scadenzario"),
        DataManagerPazienti(tmp_path / "pazienti"), DataManagerLibretto(tmp_path / "libretti"),
        data_directory=tmp_path,
    )
    controller.modalita_corrente = "CONSULTAZIONE"
    controller.settimana_display = MONDAY
    controller.mese_display = MONDAY.replace(day=1)
    controller._conferma = lambda *_args, **_kwargs: True
    notices = []
    controller._avviso = lambda *args, **kwargs: notices.append((args, kwargs))
    controller.aggiorna_tabella()
    yield controller, plans, tmp_path, notices
    assert controller.shutdown_planning()
    view.close()
    view.deleteLater()
    qt_app.processEvents()


def test_switch_preserves_period_and_zoom_without_copying(calendar) -> None:
    controller, plans, root, _ = calendar
    before = _snapshot(root)
    controller.imposta_visualizzazione("MESE")
    displayed = controller._display_dates
    controller.imposta_versione(CalendarVersion.EFFETTIVO)
    assert controller.visualizzazione == "MESE"
    assert controller.settimana_display == MONDAY
    assert controller._display_dates == displayed
    assert controller.model is not plans
    assert controller.model.version == CalendarVersion.EFFETTIVO
    assert plans.version == CalendarVersion.PREVISTO
    assert "manca" in controller.view.lbl_versione_status.text()
    controller.imposta_versione(CalendarVersion.PREVISTO)
    controller.imposta_visualizzazione("SETTIMANA")
    controller.imposta_versione(CalendarVersion.EFFETTIVO)
    assert controller._stato_corrente == "ASSENTE"
    assert controller.view.btn_crea_effettivo.isHidden()
    assert not controller.view.tabella._drop_targets
    assert _snapshot(root) == before
    assert not (root / "sale_operatorie/effettivo").exists()


def test_forecast_confirmation_copies_without_completing_patients(calendar) -> None:
    controller, plans, _, notices = calendar
    controller._registra_in_libretti = lambda: pytest.fail("legacy registration called")
    controller._segna_pazienti_completati = lambda: pytest.fail("legacy completion called")
    controller.convalida_settimana()
    actual = plans.for_version(CalendarVersion.EFFETTIVO)
    assert plans.get_stato_settimana(MONDAY) == "CONVALIDATO"
    assert actual.has_settimana(MONDAY)
    assert actual.get_stato_settimana(MONDAY) == "BOZZA"
    assert actual.get_operazioni(MONDAY.isoformat()) == plans.get_operazioni(MONDAY.isoformat())
    assert controller.model_paz.get_paziente_by_id("PZ001")["stato"] == "Pianificato"
    assert controller.model_lib.get_attivita("SP001") == []
    assert notices[-1][0][0] == "Convalida effettuata"


def test_actual_history_confirmation_updates_patient_and_booklet(calendar) -> None:
    controller, plans, root, _ = calendar
    plans.convalida_settimana(MONDAY)
    planned_before = (root / "sale_operatorie/2026-09.json").read_bytes()
    controller.imposta_versione(CalendarVersion.EFFETTIVO)
    controller.apri_vista("STORICO")
    assert controller.settimana_display == MONDAY
    assert controller._can_edit_week()
    assert not controller.view.btn_convalida.isHidden()
    controller.convalida_settimana()
    assert controller.model.get_stato_settimana(MONDAY) == "CONVALIDATO"
    assert controller.model_paz.get_paziente_by_id("PZ001")["stato"] == "Completato"
    assert len(controller.model_lib.get_attivita("SP001")) == 1
    assert (root / "sale_operatorie/2026-09.json").read_bytes() == planned_before
    assert not controller._can_edit_week()


def test_legacy_history_requires_explicit_actual_creation(calendar) -> None:
    controller, plans, root, _ = calendar
    path = root / "sale_operatorie/2026-09.json"
    data = json.loads(path.read_text())
    data["metadata"]["settimane"] = {MONDAY.isoformat(): "CONVALIDATO"}
    _write_json(path, data)
    controller.imposta_versione(CalendarVersion.EFFETTIVO)
    controller.apri_vista("STORICO")
    assert controller._stato_corrente == "ASSENTE"
    assert not controller.view.btn_crea_effettivo.isHidden()
    assert not plans.for_version(CalendarVersion.EFFETTIVO).has_settimana(MONDAY)
    controller.crea_effettivo_settimana()
    assert controller._stato_corrente == "BOZZA"
    assert controller.model.has_settimana(MONDAY)
    assert controller._can_edit_week()
    before = _snapshot(root)
    controller.crea_effettivo_settimana()
    assert _snapshot(root) == before


def test_actual_past_history_move_crosses_month_and_preserves_forecast(calendar) -> None:
    controller, plans, root, _ = calendar
    plans.convalida_settimana(MONDAY)
    planned_before = (root / "sale_operatorie/2026-09.json").read_bytes()
    controller.imposta_versione(CalendarVersion.EFFETTIVO)
    controller.apri_vista("STORICO")
    controller._sposta_operazione(0, 0, 4)
    assert controller.model.get_operazioni(MONDAY.isoformat()) == []
    assert controller.model.get_operazioni(FRIDAY.isoformat())[0]["id_paziente"] == "PZ001"
    assert (root / "sale_operatorie/2026-09.json").read_bytes() == planned_before
    assert controller.model_paz.get_paziente_by_id("PZ001")["stato"] == "Pianificato"


def test_removing_from_actual_releases_patient_but_keeps_forecast(calendar) -> None:
    controller, plans, _, _ = calendar
    plans.convalida_settimana(MONDAY)
    controller.imposta_versione(CalendarVersion.EFFETTIVO)
    controller.apri_vista("STORICO")
    controller._rimuovi_paziente_da_slot(
        SimpleNamespace(accept=lambda: None), MONDAY.isoformat(), 0,
    )
    assert controller.model.get_operazioni(MONDAY.isoformat()) == []
    assert len(plans.get_operazioni(MONDAY.isoformat())) == 1
    assert controller.model_paz.get_paziente_by_id("PZ001")["stato"] == "In Attesa"
    assert plans.get_pazienti_pianificati_ids() == set()


def test_confirmation_failure_keeps_actual_editable(calendar, monkeypatch) -> None:
    controller, plans, root, notices = calendar
    plans.convalida_settimana(MONDAY)
    controller.imposta_versione(CalendarVersion.EFFETTIVO)
    before = _snapshot(root)

    def fail_confirmation(*_args, **_kwargs):
        raise OSError("synthetic write failure")

    monkeypatch.setattr(controller.model, "convalida_settimana", fail_confirmation)
    controller.convalida_settimana()
    assert controller._can_edit_week()
    assert _snapshot(root) == before
    assert notices[-1][0][0] == "Convalida non riuscita"


@pytest.mark.parametrize("case", [
    "missing_actual", "confirmed_actual", "confirmed_forecast", "actual_month", "forecast_history",
])
def test_all_edit_handlers_reject_read_only_contexts(calendar, case: str) -> None:
    controller, plans, root, _ = calendar
    if case in {"confirmed_actual", "confirmed_forecast", "actual_month"}:
        plans.convalida_settimana(MONDAY)
    if case != "confirmed_forecast" and case != "forecast_history":
        controller.imposta_versione(CalendarVersion.EFFETTIVO)
    if case == "confirmed_actual":
        controller.convalida_settimana()
    elif case == "actual_month":
        controller.imposta_visualizzazione("MESE")
    elif case == "forecast_history":
        controller.modalita_corrente = "STORICO"
    controller.aggiorna_tabella()
    before = _snapshot(root)
    controller._conferma = lambda *_args, **_kwargs: pytest.fail("unexpected edit prompt")
    patient = controller.model_paz.get_paziente_by_id("PZ001")
    dialog = SimpleNamespace(accept=lambda: pytest.fail("unexpected edit"))
    controller.pulisci_settimana()
    controller._rimuovi_paziente_da_slot(dialog, MONDAY.isoformat(), 0)
    controller._inserisci_paziente_manuale(dialog, patient, MONDAY.isoformat(), 480, "OR-1")
    controller._scambia_operazioni(0, 0, 1)
    controller._sposta_operazione(0, 0, 4)
    controller._on_slot_vuoto_cliccato(2, 0)
    controller.pianifica_settimana()
    controller.convalida_settimana()
    assert _snapshot(root) == before


def test_actual_never_starts_solver(calendar) -> None:
    controller, plans, _, _ = calendar
    plans.convalida_settimana(MONDAY)
    controller.imposta_versione(CalendarVersion.EFFETTIVO)
    assert controller._can_edit_week()
    assert controller.view.btn_pianifica.isHidden()
    controller._start_planning_worker = lambda *_args, **_kwargs: pytest.fail("unexpected solve")
    controller.pianifica_settimana()


def test_capacity_uses_actual_month_with_forecast_fallback(calendar) -> None:
    controller, _, root, _ = calendar
    roster = controller.model_scad
    for month, capacity in ((9, 111), (10, 222)):
        data = roster.load_mese(2026, month)
        data[OPTIMIZATION_KEY]["sale_operatorie"]["OR-1"]["capacita_minuti"] = capacity
        roster.save_mese(2026, month, data)
    roster.convalida_mese(2026, 9)
    actual = roster.for_version(CalendarVersion.EFFETTIVO)
    data = actual.load_mese(2026, 9)
    data[OPTIMIZATION_KEY]["sale_operatorie"]["OR-1"]["capacita_minuti"] = 333
    actual.save_mese(2026, 9, data)
    controller.imposta_versione(CalendarVersion.EFFETTIVO)
    assert controller._capacity_for_room(MONDAY, "OR-1") == 333
    assert controller._capacity_for_room(FRIDAY, "OR-1") == 222
    assert not (root / "scadenzario/effettivo/2026-10.json").exists()
    controller.imposta_versione(CalendarVersion.PREVISTO)
    assert controller._capacity_for_room(MONDAY, "OR-1") == 111


def test_history_switch_preserves_unavailable_period_and_can_navigate_back(calendar) -> None:
    controller, plans, _, _ = calendar
    plans.convalida_settimana(MONDAY)
    controller.apri_vista("STORICO")
    selected = MONDAY + timedelta(weeks=2)
    controller.settimana_display = selected
    controller.imposta_versione(CalendarVersion.EFFETTIVO)
    assert controller.settimana_display == selected
    assert controller._stato_corrente == "ASSENTE"
    assert not controller.view.btn_prev.isHidden()
    controller.settimana_precedente()
    assert controller.settimana_display == MONDAY
    assert controller._stato_corrente == "BOZZA"
