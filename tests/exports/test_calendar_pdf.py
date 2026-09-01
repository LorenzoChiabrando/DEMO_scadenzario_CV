from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from src.calendar_presentation import month_dates
from src.controllers.controller_sale_operatorie import build_sale_operatorie_pdf_document
from src.controllers.controller_scadenzario import build_scadenzario_pdf_document
from src.exports.calendar_pdf import CalendarPdfDocument, CalendarPdfRow, write_calendar_pdf


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_calendar_pdf_is_written_as_a_single_printable_document(
    qt_app: QApplication,
    tmp_path: Path,
) -> None:
    document = CalendarPdfDocument(
        title="Calendario sintetico",
        period="01/05/2026 - 07/05/2026",
        column_headers=("1 Ven", "2 Sab"),
        rows=(
            CalendarPdfRow("I Reperibilità", ("AT", "-"), "#e0e7ff"),
            CalendarPdfRow("Sala Op. I", ("BT", "-"), "#dcfce7"),
        ),
        legend=(("AT", "Alpha Test"), ("BT", "Beta Test")),
    )

    output = write_calendar_pdf(tmp_path / "calendar", document)

    assert output.suffix == ".pdf"
    assert output.read_bytes().startswith(b"%PDF")
    assert output.stat().st_size > 1_000


class _RosterModel:
    def get_valore_cella(self, _day: str, row_key: str) -> str:
        return "118" if row_key == "Tipo Guardia" else "Rossi G."

    def get_giro_visite_settimana(self, _monday: str, _year: int, _month: int) -> str:
        return "Rossi G."


class _OperatingRoomModel:
    def get_specializzandi(self, _day: str) -> str:
        return "Rossi G.\nBianchi A."

    def get_operazioni(self, day: str) -> list[dict]:
        if date.fromisoformat(day).weekday() >= 5:
            return []
        return [
            {
                "nome_paziente": "Paziente Sintetico",
                "sala_operatoria": "OR-2",
                "ora_inizio": "08:00",
                "ora_fine": "09:00",
            }
        ]


def test_month_roster_pdf_uses_new_labels_initials_and_legend() -> None:
    document = build_scadenzario_pdf_document(
        _RosterModel(),
        month_dates(2026, 5),
        ["Giorno", "Tipo Guardia", "Reparto I", "Reparto II", "Giro Visite"],
        [
            {"nome": "Giulia", "cognome": "Rossi"},
        ],
    )

    rows = {row.label: row for row in document.rows}
    assert document.column_headers[:2] == ("1 V", "2 S")
    assert "I Reperibilità" in rows
    assert "II Reperibilità" in rows
    assert rows["I Reperibilità"].values[0] == "RG"
    assert document.legend == (("RG", "Rossi Giulia"),)


def test_month_operating_room_pdf_compacts_people_and_keeps_room() -> None:
    first_day = date(2026, 5, 1)
    dates = tuple(first_day + timedelta(days=offset) for offset in range(8))
    document = build_sale_operatorie_pdf_document(
        _OperatingRoomModel(),
        dates,
        [
            {"nome": "Giulia", "cognome": "Rossi"},
            {"nome": "Anna", "cognome": "Bianchi"},
        ],
    )

    assert document.rows[0].label == "Specializzandi"
    assert document.column_headers[0] == "1 V"
    assert document.rows[0].values[0] == "RG / BA"
    assert document.rows[1].values[0] == "PS 2"
