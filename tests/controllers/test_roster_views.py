from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from src.controllers.controller_libretto import ControllerLibretto
from src.controllers.controller_sale_operatorie import ControllerSaleOperatorie
from src.controllers.controller_scadenzario import ControllerScadenzario
from src.models.data_manager import DataManager
from src.models.data_manager_libretto import DataManagerLibretto
from src.models.data_manager_sale_operatorie import DataManagerSaleOperatorie
from src.views.view_sale_operatorie import ViewSaleOperatorie
from src.views.view_scadenzario import ViewScadenzario


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _roster(tmp_path: Path) -> tuple[ViewScadenzario, ControllerScadenzario, DataManager]:
    model = DataManager(str(tmp_path / "scadenzario"), str(tmp_path / "libretti"))
    view = ViewScadenzario()
    controller = ControllerScadenzario(view, model)
    controller.anno_corrente, controller.mese_corrente = 2026, 9
    controller.modalita_corrente = "CORRENTE"
    view.stacked_widget.setCurrentIndex(1)
    view.resize(1300, 850)
    controller.aggiorna_tabella()
    return view, controller, model


@pytest.mark.parametrize("mode", ["CORRENTE", "STORICO", "PIANIFICAZIONE"])
def test_roster_returns_to_wide_columns_after_repeated_toggles(
    qt_app: QApplication,
    tmp_path: Path,
    mode: str,
) -> None:
    view, controller, _model = _roster(tmp_path)
    controller.modalita_corrente = mode
    view.show()
    qt_app.processEvents()
    for _ in range(3):
        view.btn_vista_mese.click()
        qt_app.processEvents()
        assert view.tabella.columnWidth(10) < 150
        view.btn_vista_dettaglio.click()
        qt_app.processEvents()
        assert not view._compact
        assert all(view.tabella.columnWidth(index) == 150 for index in range(30))
        assert view.tabella.horizontalScrollBar().maximum() > 0
    view.close()
    view.deleteLater()


@pytest.mark.parametrize("mode", ["CONSULTAZIONE", "PIANIFICAZIONE", "STORICO"])
def test_operating_rooms_return_to_the_week_after_month_view(
    qt_app: QApplication,
    tmp_path: Path,
    mode: str,
) -> None:
    model = DataManagerSaleOperatorie(str(tmp_path / "sale"), str(tmp_path / "missing.json"))
    view = ViewSaleOperatorie()
    controller = ControllerSaleOperatorie(view, model)
    controller.modalita_corrente = mode
    controller.settimana_display = date(2026, 9, 14)
    controller._settimane_convalidate = [date(2026, 9, 14)]
    controller.aggiorna_tabella()
    view.stacked_widget.setCurrentIndex(1)
    view.resize(1300, 850)
    view.show()
    qt_app.processEvents()
    for _ in range(3):
        view.btn_vista_mese.click()
        qt_app.processEvents()
        month_width = view.tabella.columnWidth(1)
        assert view.tabella.columnCount() == 30
        view.btn_vista_settimana.click()
        qt_app.processEvents()
        assert controller.visualizzazione == "SETTIMANA"
        assert view.tabella.columnCount() == 5
        assert view.tabella.columnWidth(1) > month_width
        assert controller.settimana_display == date(2026, 9, 14)
    view.close()
    view.deleteLater()


def test_ward_round_updates_five_cells_and_confirmed_replacement(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    view, controller, model = _roster(tmp_path)
    row = view.row_labels.index("Giro Visite")
    view.tabella.item(row, 8).setText("Demo A.")
    assert [view.tabella.item(row, col).text() for col in range(6, 11)] == ["Demo A."] * 5
    assert all(view.tabella.columnSpan(row, col) == 1 for col in range(30))
    assert view.tabella.item(row, 11).text() == "-"
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.No)
    view.tabella.item(row, 10).setText("Demo B.")
    assert view.tabella.item(row, 10).text() == "Demo A."
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    view.tabella.item(row, 9).setText("Demo B.")
    assert [view.tabella.item(row, col).text() for col in range(6, 11)] == ["Demo B."] * 5
    assert model.get_giro_visite_settimana("2026-09-07", 2026, 9) == "Demo B."
    view.tabella.item(row, 7).setText("")
    assert all(view.tabella.item(row, col).text() == "" for col in range(6, 11))
    view.deleteLater()


def test_ward_round_rejects_a_conflict_on_another_day_and_reciprocal_assignment(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    view, controller, model = _roster(tmp_path)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    model.set_valore_cella("2026-09-11", "Sala Op. I", "Demo A.")
    view.tabella.item(6, 6).setText("Demo A.")
    assert "11/09/2026" in warnings[0]
    assert model.get_giro_visite_settimana("2026-09-07", 2026, 9) == ""
    view.tabella.item(6, 6).setText("Demo B.")
    view.tabella.item(4, 8).setText("Demo B.")
    assert len(warnings) == 2
    assert model.get_valore_cella("2026-09-09", "Sala Op. I") == ""
    view.deleteLater()


def test_ward_round_crosses_months_and_preserves_convalidated_days(tmp_path: Path) -> None:
    manager = DataManager(str(tmp_path / "scadenzario"), str(tmp_path / "libretti"))
    manager.set_giro_visite_settimana("2026-09-28", 2026, 9, "Demo A.")
    assert manager.load_mese(2026, 10)["giro_visite"]["2026-09-28"] == "Demo A."
    manager.set_valore_cella("2026-10-02", "Sala Op. I", "Demo B.")
    with pytest.raises(ValueError, match="02/10/2026"):
        manager.set_giro_visite_settimana("2026-09-28", 2026, 9, "Demo B.")
    manager.set_stato_mese(2026, 9, "CONVALIDATO")
    with pytest.raises(ValueError, match="convalidato"):
        manager.set_giro_visite_settimana("2026-09-28", 2026, 10, "Demo C.")
    assert manager.get_giro_visite_settimana("2026-09-28", 2026, 10) == "Demo A."


def test_ward_round_week_is_listed_once_in_the_libretto_across_months(tmp_path: Path) -> None:
    roster = DataManager(str(tmp_path / "scadenzario"), str(tmp_path / "libretti"))
    roster.set_giro_visite_settimana("2026-09-28", 2026, 9, "Demo A.")
    controller = ControllerLibretto.__new__(ControllerLibretto)
    controller.model_scad = roster
    controller.model = DataManagerLibretto(str(tmp_path / "libretti"))
    controller.model_sale_op = None
    activities = controller._get_pianificate({"id": "SP001", "nome": "Ada", "cognome": "Demo"})
    assert len(activities) == 5
    assert {activity["data"] for activity in activities} == {
        "2026-09-28",
        "2026-09-29",
        "2026-09-30",
        "2026-10-01",
        "2026-10-02",
    }
