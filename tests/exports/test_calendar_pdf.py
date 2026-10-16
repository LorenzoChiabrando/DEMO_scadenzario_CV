from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QPalette
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication

from src.calendar_presentation import month_dates
from src.controllers.controller_sale_operatorie import build_sale_operatorie_pdf_document
from src.controllers.controller_scadenzario import build_scadenzario_pdf_document
from src.exports.calendar_pdf import (
    CalendarPdfDocument,
    CalendarPdfRow,
    column_fractions,
    fit_font_size,
    name_lines,
    write_calendar_pdf,
)
from src.roster_month import ROLE_KEYS, RosterMonth


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


_MM_PER_POINT = 25.4 / 72


def _content_margins_mm(pdf: Path) -> dict[str, float]:
    """Margini effettivi del contenuto della prima pagina, misurati sui pixel (72 dpi)."""

    document = QPdfDocument()
    document.load(str(pdf))
    size = document.pagePointSize(0).toSize()
    image = document.render(0, QSize(size.width(), size.height()))
    document.close()

    def dark(x: int, y: int) -> bool:
        color = image.pixelColor(x, y)  # lo sfondo della pagina renderizzata è trasparente
        return color.alpha() > 128 and color.lightness() < 245

    width, height = image.width(), image.height()
    columns = [x for x in range(width) if any(dark(x, y) for y in range(0, height, 2))]
    rows = [y for y in range(height) if any(dark(x, y) for x in range(0, width, 2))]
    return {
        "left": columns[0] * _MM_PER_POINT,
        "right": (width - 1 - columns[-1]) * _MM_PER_POINT,
        "top": rows[0] * _MM_PER_POINT,
        "bottom": (height - 1 - rows[-1]) * _MM_PER_POINT,
    }


def _pdf_pages(pdf: Path) -> list[tuple[str, str]]:
    """Per ogni pagina: orientamento ("verticale"/"orizzontale") e testo estratto."""

    document = QPdfDocument()
    document.load(str(pdf))
    pages = []
    for page in range(document.pageCount()):
        size = document.pagePointSize(page)
        orientation = "verticale" if size.height() > size.width() else "orizzontale"
        pages.append((orientation, document.getAllText(page).text()))
    document.close()
    return pages


@pytest.mark.parametrize("days", [7, 31], ids=["settimana", "mese"])
def test_pdf_content_respects_symmetric_page_margins(
    qt_app: QApplication, tmp_path: Path, days: int
) -> None:
    document = CalendarPdfDocument(
        title="Calendario sintetico",
        period="periodo di prova",
        column_headers=tuple(f"{day} L" for day in range(1, days + 1)),
        rows=(CalendarPdfRow("Sala Op. I", tuple("Rossi G." for _ in range(days)), "#dcfce7"),),
    )

    margins = _content_margins_mm(write_calendar_pdf(tmp_path / "margini.pdf", document))

    assert margins["left"] == pytest.approx(8, abs=2)
    assert margins["right"] == pytest.approx(8, abs=2)
    assert margins["top"] == pytest.approx(8, abs=3)


_RESIDENTS = [{"nome": "Giulia", "cognome": "Rossi"}]


def test_month_roster_pdf_is_one_full_landscape_page_with_whole_names(
    qt_app: QApplication, tmp_path: Path
) -> None:
    document = build_scadenzario_pdf_document(
        _roster_month(2026, 5), month_dates(2026, 5), _RESIDENTS
    )

    pdf = write_calendar_pdf(tmp_path / "mese.pdf", document)
    pages = _pdf_pages(pdf)

    assert [orientation for orientation, _ in pages] == ["orizzontale"]
    text = pages[0][1]
    assert "Scadenzario mensile" in text
    assert "Rossi" in text and "G." in text
    assert "Legenda" not in text
    assert _content_margins_mm(pdf)["bottom"] == pytest.approx(8, abs=3)


def test_week_roster_pdf_is_landscape_with_full_names(qt_app: QApplication, tmp_path: Path) -> None:
    week = tuple(date(2026, 5, 4) + timedelta(days=offset) for offset in range(7))
    document = build_scadenzario_pdf_document(_roster_month(2026, 5), week, _RESIDENTS)

    pages = _pdf_pages(write_calendar_pdf(tmp_path / "settimana.pdf", document))

    assert [orientation for orientation, _ in pages] == ["orizzontale"]
    assert "Scadenzario settimanale" in pages[0][1]
    assert "Rossi Giulia" in pages[0][1]


def test_long_calendars_continue_on_a_new_page_with_the_header_repeated(
    qt_app: QApplication, tmp_path: Path
) -> None:
    document = CalendarPdfDocument(
        title="Calendario lungo",
        period="maggio 2026",
        column_headers=tuple(f"{day} Lun" for day in range(1, 32)),
        rows=tuple(
            CalendarPdfRow(f"Attività {index}", tuple("Rossi G." for _ in range(31)))
            for index in range(1, 61)
        ),
    )

    pages = _pdf_pages(write_calendar_pdf(tmp_path / "lungo.pdf", document))

    assert len(pages) > 1
    assert all("31" in text and "Attività" in text for _, text in pages)
    assert "Attività 60" in pages[-1][1]
    assert f"Pagina {len(pages)} di {len(pages)}" in pages[-1][1]


def test_cell_text_is_printed_literally(qt_app: QApplication, tmp_path: Path) -> None:
    document = CalendarPdfDocument(
        title="Prova <b>",
        period="maggio 2026",
        column_headers=("1 Ven",),
        rows=(CalendarPdfRow("Sala Op. I", ("Rossi & <i>Figli</i>",), "#dcfce7"),),
    )

    text = _pdf_pages(write_calendar_pdf(tmp_path / "testo.pdf", document))[0][1]
    # L'estrazione di QtPdf può spezzare le righe tra i caratteri: si confronta senza spazi.
    compact = "".join(text.split())

    assert "Rossi&<i>Figli</i>" in compact
    assert "Prova<b>" in compact


def _roster_month(year: int, month: int) -> RosterMonth:
    values = {
        (day, role): "118" if role == "Tipo Guardia" else "Rossi G."
        for day in month_dates(year, month)
        if day.weekday() < 5
        for role in ROLE_KEYS
    }
    return RosterMonth(year, month, "BOZZA", values)


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


def test_month_roster_pdf_uses_new_labels_and_short_names_without_legend() -> None:
    document = build_scadenzario_pdf_document(
        _roster_month(2026, 5),
        month_dates(2026, 5),
        [{"nome": "Giulia", "cognome": "Rossi"}],
    )

    rows = {row.label: row for row in document.rows}
    assert document.column_headers[:2] == ("1 Ven", "2 Sab")
    assert "I Reperibilità" in rows
    assert "II Reperibilità" in rows
    assert rows["I Reperibilità"].values[0] == "Rossi G."
    assert rows["Tipo Guardia"].value_colors["118"] == "#b91c1c"
    assert document.legend == ()
    assert "118 = Emergenza territoriale" in document.footnote
    assert document.stacked_names
    assert 1 in document.rest_columns and 0 not in document.rest_columns


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


def _days_document(headers, rest_columns=frozenset(), values=None) -> CalendarPdfDocument:
    values = values or tuple("Rossi G." for _ in headers)
    return CalendarPdfDocument(
        title="Prova",
        period="maggio 2026",
        column_headers=tuple(headers),
        rows=(CalendarPdfRow("Sala Op. I", tuple(values)),),
        rest_columns=frozenset(rest_columns),
    )


def test_rest_day_columns_are_narrow_and_widths_fill_the_table() -> None:
    headers = [f"{day} X" for day in range(1, 32)]
    rest = {day - 1 for day in range(1, 32) if date(2026, 5, day).weekday() >= 5}

    fractions = column_fractions(_days_document(headers, rest))

    label, *days = fractions
    assert sum(fractions) == pytest.approx(1.0)
    assert all(days[index] < days[0] for index in rest)
    assert len({round(days[index], 9) for index in range(31) if index not in rest}) == 1
    assert label > max(days)


def test_weekdays_without_assignments_keep_normal_width() -> None:
    headers = [f"{day} X" for day in range(1, 6)]

    _label, *days = column_fractions(_days_document(headers, values=("-",) * 5))

    assert len({round(width, 9) for width in days}) == 1


def test_a_weekend_only_week_still_exports(qt_app: QApplication, tmp_path: Path) -> None:
    document = _days_document(["1 Sab", "2 Dom"], rest_columns={0, 1}, values=("-", "-"))

    _label, *days = column_fractions(document)
    pages = _pdf_pages(write_calendar_pdf(tmp_path / "weekend.pdf", document))

    assert days[0] == pytest.approx(days[1])
    assert len(pages) == 1


def _dark_pixels(pdf: Path) -> int:
    document = QPdfDocument()
    document.load(str(pdf))
    size = document.pagePointSize(0).toSize()
    image = document.render(0, QSize(size.width(), size.height()))
    document.close()
    return sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if (color := image.pixelColor(x, y)).alpha() > 128 and color.lightness() < 120
    )


def test_pdf_text_stays_dark_with_a_dark_desktop_theme(
    qt_app: QApplication, tmp_path: Path
) -> None:
    document = CalendarPdfDocument(
        title="T",
        period="p",
        column_headers=("1 Lun", "2 Mar"),
        rows=(CalendarPdfRow("Sala Op. I", ("Rossi G.", "Bianchi A.")),),
    )
    light_theme = _dark_pixels(write_calendar_pdf(tmp_path / "chiaro.pdf", document))
    original = qt_app.palette()
    dark_theme = QPalette(original)
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText):
        dark_theme.setColor(role, QColor("#f8fafc"))
    qt_app.setPalette(dark_theme)
    try:
        with_dark_theme = _dark_pixels(write_calendar_pdf(tmp_path / "scuro.pdf", document))
    finally:
        qt_app.setPalette(original)

    assert with_dark_theme >= light_theme * 0.95


def test_name_lines_put_surname_and_initial_on_two_lines() -> None:
    assert name_lines("Gasparri A.", stacked=True) == ("Gasparri", "A.")
    assert name_lines("De Luca M.", stacked=True) == ("De Luca", "M.")
    assert name_lines("Rossi Giulia", stacked=True) == ("Rossi Giulia",)
    assert name_lines("Gasparri A.", stacked=False) == ("Gasparri A.",)


def test_font_size_is_the_largest_that_fits_every_text() -> None:
    def measure(text: str, size: float) -> float:
        return len(text) * size

    assert fit_font_size(["abcd", "abcdefgh"], room=40, measure=measure) == 6.25
    assert fit_font_size(["abcd"], room=400, measure=measure) == 10.0
    assert fit_font_size(["abcdefgh" * 10], room=1, measure=measure) == 6.0


def test_a_very_long_surname_is_never_cut(qt_app: QApplication, tmp_path: Path) -> None:
    document = CalendarPdfDocument(
        title="Mese",
        period="maggio 2026",
        column_headers=tuple(f"{day} Lun" for day in range(1, 32)),
        rows=(CalendarPdfRow("Sala Op. I", tuple("Mastrolorenzo A." for _ in range(31))),),
        stacked_names=True,
    )

    text = _pdf_pages(write_calendar_pdf(tmp_path / "lungo.pdf", document))[0][1]

    assert "Mastrolorenzo" in text
