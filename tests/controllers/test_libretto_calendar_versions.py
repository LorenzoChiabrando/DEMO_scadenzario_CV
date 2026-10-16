from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.calendar_versions import CalendarVersion
from src.controllers.controller_libretto import ControllerLibretto
from src.models.data_manager import DataManager
from src.models.data_manager_libretto import DataManagerLibretto
from src.models.data_manager_sale_operatorie import DataManagerSaleOperatorie

MONDAY = date(2026, 11, 2)
ALPHA = {"id": "R1", "nome": "Resident", "cognome": "Alpha", "stato": "Molinette"}
BETA = {"id": "R2", "nome": "Resident", "cognome": "Beta", "stato": "Molinette"}


@pytest.fixture
def controller(tmp_path: Path) -> ControllerLibretto:
    libretti = DataManagerLibretto(tmp_path / "libretti")
    for resident in (ALPHA, BETA):
        (tmp_path / "libretti" / f"{resident['id']}.json").write_text(
            json.dumps(resident), encoding="utf-8",
        )
    result = ControllerLibretto.__new__(ControllerLibretto)
    result.model = libretti
    result.model_scad = DataManager(tmp_path / "scadenzario")
    result.model_sale_op = DataManagerSaleOperatorie(tmp_path / "sale_operatorie")
    return result


def test_actual_roster_replaces_planned_without_confirming_non_or_activities(controller):
    planned = controller.model_scad
    planned.set_valore_cella(MONDAY.isoformat(), "Day Hospital", "Alpha R.")
    assert len(controller._get_pianificate(ALPHA)) == 1
    planned.convalida_mese(2026, 11)
    actual = planned.for_version(CalendarVersion.EFFETTIVO)
    actual.set_valore_cella(MONDAY.isoformat(), "Day Hospital", "Beta R.")

    assert controller._get_pianificate(ALPHA) == []
    assert len(controller._get_pianificate(BETA)) == 1
    actual.convalida_mese(2026, 11)
    assert controller._get_completate(BETA) == []
    assert len(controller._get_pianificate(BETA)) == 1
    assert planned.get_valore_cella(MONDAY.isoformat(), "Day Hospital") == "Alpha R."


def test_libretto_reads_fresh_actual_operations_and_assignees(controller):
    day = MONDAY.isoformat()
    controller.model_scad.set_valore_cella(day, "Sala Op. I", "Alpha R.")
    planned = controller.model_sale_op
    planned.set_specializzandi(day, "Alpha R.", "")
    planned.set_operazioni(day, [{"nome_paziente": "Synthetic Patient", "intervento": "Before"}])
    planned.convalida_settimana(MONDAY)
    actual = planned.for_version(CalendarVersion.EFFETTIVO)
    actual.set_specializzandi(day, "Beta R.", "")
    actual.set_operazioni(day, [{"nome_paziente": "Synthetic Patient", "intervento": "After"}])

    assert controller._get_pianificate(ALPHA) == []
    pending = controller._get_pianificate(BETA)
    assert len(pending) == 1
    assert pending[0]["slots"][0]["intervento"] == "After"
    assert controller._get_completate(BETA) == []
    assert planned.get_operazioni(day)[0]["intervento"] == "Before"

    actual.set_operazioni(day, [])
    assert controller._get_pianificate(BETA)[0]["slots"] == []


def test_libretto_version_resolution_does_not_depend_on_bound_manager(controller):
    controller.model_scad.set_valore_cella(MONDAY.isoformat(), "Day Hospital", "Alpha R.")
    controller.model_scad = controller.model_scad.for_version(CalendarVersion.EFFETTIVO)
    controller.model_sale_op = controller.model_sale_op.for_version(CalendarVersion.EFFETTIVO)

    pending = controller._get_pianificate(ALPHA)
    assert len(pending) == 1
    assert pending[0]["attivita"] == "Day Hospital"
    assert not controller.model_scad.has_mese(2026, 11)


def test_libretto_reads_each_room_month_once_per_refresh(controller, monkeypatch):
    for offset in range(5):
        day = (MONDAY + timedelta(days=offset)).isoformat()
        controller.model_scad.set_valore_cella(day, "Sala Op. I", "Alpha R.")
        controller.model_sale_op.set_specializzandi(day, "Alpha R.", "")
    controller.model_sale_op.convalida_settimana(MONDAY)
    original_load = DataManagerSaleOperatorie.load_mese
    calls = []

    def counted_load(manager, year, month):
        calls.append((manager.version, year, month))
        return original_load(manager, year, month)

    monkeypatch.setattr(DataManagerSaleOperatorie, "load_mese", counted_load)
    pending = controller._get_pianificate(ALPHA)

    assert len(pending) == 5
    assert calls == [(CalendarVersion.EFFETTIVO, 2026, 11)]


def test_surgical_card_cannot_confirm_an_activity():
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton

    from src.views.view_libretto import ViewLibretto

    app = QApplication.instance() or QApplication([])
    view = ViewLibretto()
    card = view._crea_card_or_pianificata(
        {"data": MONDAY.isoformat(), "sede": "Sala Operatoria", "attivita": "Intervento"},
        {}, lambda _record: pytest.fail("Surgical activity cannot be confirmed manually"),
    )
    assert not card.findChildren(QPushButton)
    assert any("convalida dell'Effettivo" in label.text() for label in card.findChildren(QLabel))
    card.deleteLater()
    view.deleteLater()
    app.processEvents()
