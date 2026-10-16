from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.roster_month import RosterMonth, resident_rows
from src.views.models.resident_table_model import ResidentTableModel

_RESIDENTS = [{"id": "SP001", "nome": "Mario", "cognome": "Rossi", "stato": "Molinette"}]


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _model() -> ResidentTableModel:
    roster = RosterMonth(2026, 9, "BOZZA", {(date(2026, 9, 15), "Sala Op. I"): "Rossi M."})
    model = ResidentTableModel()
    model.set_rows(roster, resident_rows(roster, _RESIDENTS))
    return model


def test_rows_are_residents_and_first_column_is_the_total(qt_app: QApplication) -> None:
    model = _model()

    assert model.rowCount() == 1
    assert model.columnCount() == 31
    assert model.total_column() == 0
    assert model.headerData(0, Qt.Orientation.Vertical) == "Rossi M."
    assert model.headerData(0, Qt.Orientation.Vertical, Qt.ItemDataRole.ToolTipRole) == (
        "Rossi Mario"
    )
    assert model.headerData(0, Qt.Orientation.Horizontal) == "Totale"
    assert model.headerData(15, Qt.Orientation.Horizontal) == "15"
    assert model.index(0, 0).data() == "1"


def test_cells_show_role_codes_with_role_colors(qt_app: QApplication) -> None:
    model = _model()
    background = Qt.ItemDataRole.BackgroundRole

    assert model.index(0, 15).data() == "S1"
    assert model.index(0, 15).data(background).name() == "#bbf7d0"
    assert model.index(0, 15).data(Qt.ItemDataRole.ToolTipRole) == "Sala Op. I"
    assert model.index(0, 19).data(background).name() == "#e2e8f0"
    assert model.index(0, 17).data() == ""
    assert not model.flags(model.index(0, 15)) & Qt.ItemFlag.ItemIsEditable
