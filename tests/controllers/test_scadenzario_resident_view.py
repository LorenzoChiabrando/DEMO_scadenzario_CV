from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.controllers.controller_scadenzario import ControllerScadenzario
from src.models.data_manager import DataManager
from src.views.view_scadenzario import ViewScadenzario


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _roster(tmp_path: Path):
    libretti = tmp_path / "libretti"
    libretti.mkdir()
    for index, (name, surname) in enumerate([("Ada", "Demo"), ("Bruno", "Prova")], 1):
        payload = {"id": f"SP{index:03d}", "nome": name, "cognome": surname, "stato": "Molinette"}
        (libretti / f"SP{index:03d}.json").write_text(json.dumps(payload), encoding="utf-8")
    model = DataManager(str(tmp_path / "scadenzario"), str(libretti))
    model.set_valore_cella("2026-09-15", "Sala Op. I", "Demo A.")
    model.set_valore_cella("2026-09-16", "Sala Op. I", "Demo A.")
    view = ViewScadenzario()
    controller = ControllerScadenzario(view, model)
    controller.anno_corrente, controller.mese_corrente = 2026, 9
    controller.modalita_corrente = "PIANIFICAZIONE"
    view.stacked_widget.setCurrentIndex(1)
    controller.aggiorna_tabella()
    return view, controller


def test_resident_view_lists_people_with_codes_and_totals(
    qt_app: QApplication, tmp_path: Path
) -> None:
    view, _controller = _roster(tmp_path)

    view.btn_per_specializzando.click()

    model = view.tabella_specializzandi.model()
    assert view.stack_tabelle.currentWidget() is view.tabella_specializzandi
    assert view.btn_per_specializzando.isChecked() and not view.btn_per_attivita.isChecked()
    assert view.btn_vista_dettaglio.isEnabled() and view.btn_vista_mese.isEnabled()
    vertical = Qt.Orientation.Vertical
    assert [model.headerData(r, vertical) for r in range(model.rowCount())] == [
        "Demo A.",
        "Prova B.",
    ]
    assert model.index(0, 15).data() == "S1"
    assert model.index(0, model.total_column()).data() == "2"

    view.btn_per_attivita.click()
    assert view.stack_tabelle.currentWidget() is view.tabella
    assert view.btn_vista_dettaglio.isEnabled()


def test_both_views_follow_month_navigation(qt_app: QApplication, tmp_path: Path) -> None:
    view, controller = _roster(tmp_path)

    controller.mese_successivo()

    assert view.tabella.model().columnCount() == 31
    assert view.tabella_specializzandi.model().columnCount() == 32


def test_resident_view_is_readable_in_the_startup_window(
    qt_app: QApplication, tmp_path: Path
) -> None:
    view, _controller = _roster(tmp_path)
    view.resize(900, 600)
    view.show()
    view.mostra_vista_specializzandi(True)
    qt_app.processEvents()
    table = view.tabella_specializzandi
    total = table.model().total_column()

    assert table.textElideMode() == Qt.TextElideMode.ElideNone
    assert table.columnWidth(total) >= 60
    assert table.columnWidth(total) > table.columnWidth(1)
    used_height = sum(table.rowHeight(row) for row in range(table.model().rowCount()))
    assert used_height >= table.viewport().height() - 4
    view.close()


def test_total_column_stays_wide_after_changing_month(qt_app: QApplication, tmp_path: Path) -> None:
    view, controller = _roster(tmp_path)
    view.resize(900, 600)
    view.show()
    view.mostra_vista_specializzandi(True)
    controller.mese_successivo()
    qt_app.processEvents()
    table = view.tabella_specializzandi

    assert table.columnWidth(table.model().total_column()) >= 60
    view.close()


def _show_resident_view(qt_app: QApplication, tmp_path: Path, *, compact: bool):
    view, controller = _roster(tmp_path)
    view.resize(900, 600)
    view.show()
    controller.imposta_vista_compatta(compact)
    view.btn_per_specializzando.click()
    qt_app.processEvents()
    return view, controller, view.tabella_specializzandi


def test_resident_detail_view_scrolls_with_wide_day_columns(
    qt_app: QApplication, tmp_path: Path
) -> None:
    view, _controller, table = _show_resident_view(qt_app, tmp_path, compact=False)

    assert all(table.columnWidth(column) == 48 for column in range(1, 31))
    assert table.columnWidth(0) >= 60
    assert table.horizontalScrollBar().maximum() > 0
    view.close()


def test_resident_full_month_view_fits_without_scrolling(
    qt_app: QApplication, tmp_path: Path
) -> None:
    view, _controller, table = _show_resident_view(qt_app, tmp_path, compact=True)

    last = table.model().columnCount() - 1
    assert table.columnViewportPosition(last) + table.columnWidth(last) <= table.viewport().width()
    assert table.columnWidth(1) < 48
    view.close()


def test_resident_detail_columns_survive_month_changes(
    qt_app: QApplication, tmp_path: Path
) -> None:
    view, controller, table = _show_resident_view(qt_app, tmp_path, compact=False)

    controller.mese_successivo()
    qt_app.processEvents()

    assert table.columnWidth(1) == 48
    assert table.columnWidth(31) == 48
    assert table.columnWidth(0) >= 60
    view.close()
