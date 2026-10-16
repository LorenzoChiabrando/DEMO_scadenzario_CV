from __future__ import annotations

import calendar
import json
from datetime import date
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox, QTableWidget

from src.calendar_versions import CalendarVersion
from src.controllers.controller_scadenzario import (
    ControllerScadenzario,
    _duplicate_operating_room_assignments,
    _missing_operating_room_assignments,
)
from src.models.data_manager import DataManager
from src.views.view_scadenzario import ViewScadenzario


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


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("version", list(CalendarVersion))
def test_gui_confirmation_freezes_only_selected_version_and_creates_actual_from_planned(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    version: CalendarVersion,
) -> None:
    model = DataManager(tmp_path / "scadenzario", tmp_path / "libretti")
    planned = _complete_month(2026, 6)
    planned["metadata"] = {"stato": "BOZZA"}
    model.save_mese(2026, 6, planned)
    if version == CalendarVersion.EFFETTIVO:
        model.convalida_mese(2026, 6)
    planned_path = tmp_path / "scadenzario/2026-06.json"
    actual_path = tmp_path / "scadenzario/effettivo/2026-06.json"
    planned_before = planned_path.read_bytes()
    messages = []

    def confirm(*args):
        messages.append((args[1], args[2]))
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", confirm)
    view = ViewScadenzario()
    controller = ControllerScadenzario(view, model)
    controller.anno_corrente, controller.mese_corrente = 2026, 6
    controller.modalita_corrente = "STORICO" if version == CalendarVersion.EFFETTIVO else "CORRENTE"
    view.combo_versione.setCurrentIndex(view.combo_versione.findData(version.value))
    controller.aggiorna_tabella()
    try:
        controller.convalida_mese()

        assert messages[0][0] == f"Convalida {version.value.capitalize()}"
        assert "06/2026" in messages[0][1]
        assert controller.model.get_stato_mese(2026, 6) == "CONVALIDATO"
        assert view.tabella.editTriggers() == QTableWidget.EditTrigger.NoEditTriggers
        assert view.btn_convalida.isHidden()
        assert not (tmp_path / "pazienti").exists()
        assert not (tmp_path / "libretti").exists()
        if version == CalendarVersion.PREVISTO:
            assert json.loads(actual_path.read_text())["metadata"]["stato"] == "BOZZA"
            assert json.loads(actual_path.read_text())["turni"] == planned["turni"]
        else:
            assert planned_path.read_bytes() == planned_before
        snapshot = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
        controller.convalida_mese()
        assert len(messages) == 1
        assert all(path.read_bytes() == content for path, content in snapshot.items())
    finally:
        view.close()
        view.deleteLater()
        qt_app.processEvents()


def test_gui_confirmation_of_incomplete_planned_does_not_create_actual(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = DataManager(tmp_path / "scadenzario", tmp_path / "libretti")
    planned = _complete_month(2026, 6)
    planned["metadata"] = {"stato": "BOZZA"}
    planned["turni"]["2026-06-01"].pop("Sala Op. I")
    model.save_mese(2026, 6, planned)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[1]))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: pytest.fail("Unexpected confirmation"),
    )
    view = ViewScadenzario()
    controller = ControllerScadenzario(view, model)
    controller.anno_corrente, controller.mese_corrente = 2026, 6
    controller.modalita_corrente = "CORRENTE"
    try:
        controller.convalida_mese()

        assert warnings == ["Scadenzario Previsto incompleto"]
        assert controller.model.get_stato_mese(2026, 6) == "BOZZA"
        assert not (tmp_path / "scadenzario/effettivo").exists()
    finally:
        view.close()
        view.deleteLater()
        qt_app.processEvents()
