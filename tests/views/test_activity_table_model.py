from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.roster_month import RosterMonth
from src.views.models.activity_table_model import ROW_KEYS, ActivityTableModel

_TUESDAY_15 = 14
_SATURDAY_19 = 18


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _model() -> ActivityTableModel:
    roster = RosterMonth(
        2026,
        9,
        "BOZZA",
        {
            (date(2026, 9, 15), "Sala Op. I"): "Rossi M.",
            (date(2026, 9, 15), "Tipo Guardia"): "118",
        },
    )
    model = ActivityTableModel()
    model.set_roster(roster, [{"nome": "Mario", "cognome": "Rossi"}])
    return model


def _text(model, row_key, column, role=Qt.ItemDataRole.DisplayRole):
    return model.index(ROW_KEYS.index(row_key), column).data(role)


def test_shape_follows_roles_and_days(qt_app: QApplication) -> None:
    model = _model()

    assert model.rowCount() == 9
    assert model.columnCount() == 30
    assert model.headerData(_TUESDAY_15, Qt.Orientation.Horizontal) == "15"


def test_detail_and_full_month_texts(qt_app: QApplication) -> None:
    model = _model()
    assert _text(model, "Sala Op. I", _TUESDAY_15) == "Rossi M."
    assert _text(model, "Giorno", _TUESDAY_15) == "MAR"
    assert _text(model, "Sala Op. I", _SATURDAY_19) == "-"
    assert model.headerData(2, Qt.Orientation.Vertical) == "I Reperibilità"

    model.set_compact(True)

    assert _text(model, "Sala Op. I", _TUESDAY_15) == "RM"
    assert _text(model, "Tipo Guardia", _TUESDAY_15) == "118"
    assert _text(model, "Giorno", _TUESDAY_15) == "M"
    assert model.headerData(2, Qt.Orientation.Vertical) == "I Rep"


def test_colors_follow_role_rest_days_and_today(qt_app: QApplication) -> None:
    model = _model()
    background = Qt.ItemDataRole.BackgroundRole

    assert _text(model, "Sala Op. I", 0, background).name() == "#dcfce7"
    assert _text(model, "Giro Visite", 0, background).name() == "#fef9c3"
    assert _text(model, "Sala Op. I", _SATURDAY_19, background).name() == "#e2e8f0"
    assert _text(model, "Tipo Guardia", _TUESDAY_15, Qt.ItemDataRole.ForegroundRole).name() == (
        "#b91c1c"
    )

    model.set_today(date(2026, 9, 15))

    assert _text(model, "Sala Op. I", _TUESDAY_15, background).name() == "#fef3c7"
    assert _text(model, "Giorno", _TUESDAY_15, background).name() == "#f59e0b"


def test_tooltip_shows_the_full_name_and_cells_are_read_only(qt_app: QApplication) -> None:
    model = _model()

    assert _text(model, "Sala Op. I", _TUESDAY_15, Qt.ItemDataRole.ToolTipRole) == "Rossi Mario"
    index = model.index(ROW_KEYS.index("Sala Op. I"), _TUESDAY_15)
    assert not model.flags(index) & Qt.ItemFlag.ItemIsEditable
    assert model.value_at(ROW_KEYS.index("Sala Op. I"), _TUESDAY_15) == "Rossi M."
    assert model.value_at(0, _TUESDAY_15) == ""
    assert model.role_at(ROW_KEYS.index("Giro Visite")) == "Giro Visite"
    assert model.date_at(_TUESDAY_15) == date(2026, 9, 15)
