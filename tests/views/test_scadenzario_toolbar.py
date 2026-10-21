from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QFrame, QLabel

from src.roster_month import RosterMonth
from src.views.view_scadenzario import ViewScadenzario


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _center_y(widget, root) -> int:
    return widget.mapTo(root, QPoint(0, widget.height() // 2)).y()


def test_guard_legend_is_compact_and_shares_the_tools_row(qt_app: QApplication) -> None:
    view = ViewScadenzario()
    view.stacked_widget.setCurrentIndex(1)
    view.resize(860, 700)
    view.show()
    qt_app.processEvents()

    chips = view.findChildren(QLabel, "LegendaGuardia")
    assert [chip.text() for chip in chips] == ["118", "PI", "L"]
    assert [chip.toolTip() for chip in chips] == [
        "Emergenza territoriale",
        "Pronto Intervento",
        "Liscia (routinaria)",
    ]
    row_y = _center_y(view.btn_vista_dettaglio, view)
    assert all(abs(_center_y(chip, view) - row_y) <= 4 for chip in chips)
    export_right = view.btn_esporta_pdf.mapTo(view, QPoint(view.btn_esporta_pdf.width(), 0)).x()
    assert export_right <= view.width()
    assert view.findChild(QFrame, "PannelloTurni") is None
    view.close()


def test_version_selector_shows_its_drop_down_arrow(qt_app: QApplication) -> None:
    view = ViewScadenzario()
    view.stacked_widget.setCurrentIndex(1)
    view.resize(860, 700)
    view.show()
    qt_app.processEvents()

    image = view.combo_versione.grab().toImage()
    drop_down = [
        QColor(image.pixel(x, y)).lightness()
        for x in range(image.width() - 30, image.width())
        for y in range(image.height())
    ]
    view.close()

    assert min(drop_down) >= 90, "native drop-down frame drawn instead of the QSS one"
    assert min(drop_down) < 200, "drop-down arrow missing"


def test_full_month_view_shows_every_day_without_scrolling(qt_app: QApplication) -> None:
    view = ViewScadenzario()
    view.stacked_widget.setCurrentIndex(1)
    view.modello_attivita.set_roster(RosterMonth(2026, 10, "BOZZA"))
    view.resize(900, 700)
    view.show()
    view.set_compact_mode(True)
    qt_app.processEvents()

    last = view.tabella.model().columnCount() - 1
    right_edge = view.tabella.columnViewportPosition(last) + view.tabella.columnWidth(last)
    assert right_edge <= view.tabella.viewport().width()
    view.close()


def test_narrow_columns_never_replace_initials_with_an_ellipsis(qt_app: QApplication) -> None:
    from PySide6.QtCore import Qt

    view = ViewScadenzario()

    assert view.tabella.textElideMode() == Qt.TextElideMode.ElideNone
    view.deleteLater()
