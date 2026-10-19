from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QLabel,
    QPushButton,
)

from src.calendar_versions import CalendarVersion
from src.controllers import controller_sale_operatorie as sale_module
from src.controllers.controller_sale_operatorie import ControllerSaleOperatorie
from src.exports.calendar_pdf import CalendarPdfDocument
from src.models.data_manager_sale_operatorie import DataManagerSaleOperatorie
from src.views.view_sale_operatorie import ViewSaleOperatorie

MONDAY = date(2026, 9, 14)
PATIENT_NAMES = {
    CalendarVersion.PREVISTO: "Paziente Sintetico Previsto",
    CalendarVersion.EFFETTIVO: "Paziente Sintetico Effettivo",
}


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def sale_view(qt_app: QApplication) -> Iterator[ViewSaleOperatorie]:
    view = ViewSaleOperatorie()
    view.resize(1300, 850)
    view.show()
    qt_app.processEvents()
    try:
        yield view
    finally:
        view.close()
        view.deleteLater()
        qt_app.processEvents()


def _controller(
    view: ViewSaleOperatorie,
    directory: Path,
    *,
    actual_exists: bool = True,
) -> ControllerSaleOperatorie:
    """Build an isolated legacy forecast and, optionally, an editable actual week."""
    versions = list(CalendarVersion) if actual_exists else [CalendarVersion.PREVISTO]
    for version in versions:
        target = directory / "sale_operatorie"
        if version == CalendarVersion.EFFETTIVO:
            target /= "effettivo"
        target.mkdir(parents=True, exist_ok=True)
        state = "BOZZA" if version == CalendarVersion.EFFETTIVO else "CONVALIDATO"
        payload = {
            "metadata": {"stato": "BOZZA", "settimane": {MONDAY.isoformat(): state}},
            "turni": {
                MONDAY.isoformat(): {
                    "specializzandi": {},
                    "operazioni": [
                        {
                            "id_paziente": "PZ-SYN-001",
                            "nome_paziente": PATIENT_NAMES[version],
                            "ora_inizio": "08:00",
                            "ora_fine": "09:00",
                            "durata": 60,
                            "sala_operatoria": "OR-1",
                            "intervento": "Procedura sintetica",
                        }
                    ],
                }
            },
        }
        (target / "2026-09.json").write_text(json.dumps(payload), encoding="utf-8")
    manager = DataManagerSaleOperatorie(
        directory / "sale_operatorie",
        directory / "anagrafica-assente.json",
        directory / "pazienti",
    )
    controller = ControllerSaleOperatorie(view, manager, data_directory=directory)
    controller.apri_vista("STORICO")
    return controller


@pytest.mark.parametrize("page", [0, 1])
def test_version_selector_is_visible_on_dashboard_and_calendar(
    sale_view: ViewSaleOperatorie,
    qt_app: QApplication,
    page: int,
) -> None:
    sale_view.stacked_widget.setCurrentIndex(page)
    qt_app.processEvents()
    selector = sale_view.combo_versione

    assert selector.isVisible()
    assert selector.count() == 2
    assert [(selector.itemText(index), selector.itemData(index)) for index in range(2)] == [
        ("Previsto", CalendarVersion.PREVISTO),
        ("Effettivo", CalendarVersion.EFFETTIVO),
    ]
    assert selector.currentData() == CalendarVersion.PREVISTO


@pytest.mark.parametrize("actual_exists", [True, False], ids=["draft", "missing"])
def test_actual_history_shows_version_and_state_without_creating_files(
    sale_view: ViewSaleOperatorie,
    tmp_path: Path,
    actual_exists: bool,
) -> None:
    controller = _controller(sale_view, tmp_path, actual_exists=actual_exists)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    sale_view.combo_versione.setCurrentIndex(
        sale_view.combo_versione.findData(CalendarVersion.EFFETTIVO)
    )

    assert controller.settimana_display == MONDAY
    assert controller.modalita_corrente == "STORICO"
    assert "STORICO" in sale_view.lbl_modalita.text()
    assert "EFFETTIVO" in sale_view.lbl_modalita.text()
    assert sale_view.lbl_stato.isVisible()
    assert sale_view.lbl_stato.text().strip() == ("BOZZA" if actual_exists else "ASSENTE")
    assert sale_view.lbl_versione_status.isVisible() is not actual_exists
    assert sale_view.btn_crea_effettivo.isVisible() is not actual_exists
    assert sale_view.btn_convalida.isVisible() is actual_exists
    assert not sale_view.btn_pianifica.isVisible()
    if not actual_exists:
        labels = [
            label.text()
            for row in range(2, sale_view.tabella.rowCount())
            for column in range(sale_view.tabella.columnCount())
            if (widget := sale_view.tabella.cellWidget(row, column)) is not None
            for label in widget.findChildren(QLabel)
        ]
        assert not any("Paziente Sintetico" in label for label in labels)
        assert "non ancora creato" in sale_view.lbl_versione_status.text()
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.json")} == before


@pytest.mark.parametrize("version", list(CalendarVersion))
@pytest.mark.parametrize("month_mode", [False, True], ids=["week", "month"])
def test_patient_popup_uses_selected_version_and_month_summary_cannot_remove(
    sale_view: ViewSaleOperatorie,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    version: CalendarVersion,
    month_mode: bool,
) -> None:
    controller = _controller(sale_view, tmp_path)
    controller.imposta_versione(version)
    if month_mode:
        controller.imposta_visualizzazione("MESE")
    captured: list[tuple[str, list[str], list[str]]] = []

    def capture_dialog(dialog: QDialog) -> int:
        captured.append(
            (
                dialog.windowTitle(),
                [label.text() for label in dialog.findChildren(QLabel)],
                [button.text() for button in dialog.findChildren(QPushButton)],
            )
        )
        return 0

    monkeypatch.setattr(QDialog, "exec", capture_dialog)
    column = MONDAY.day - 1 if month_mode else 0
    controller._on_cella_cliccata(2, column)

    assert len(captured) == 1
    title, labels, buttons = captured[0]
    assert version.value.capitalize() in title
    assert PATIENT_NAMES[version] in labels
    other_version = (
        CalendarVersion.PREVISTO
        if version == CalendarVersion.EFFETTIVO
        else CalendarVersion.EFFETTIVO
    )
    assert PATIENT_NAMES[other_version] not in labels
    assert f"Scheda paziente · {version.value.capitalize()}" in labels
    expected_remove = version == CalendarVersion.EFFETTIVO and not month_mode
    assert ("Rimuovi dal piano" in buttons) is expected_remove


@pytest.mark.parametrize("version", list(CalendarVersion))
def test_pdf_export_identifies_version_and_uses_its_operations(
    sale_view: ViewSaleOperatorie,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    version: CalendarVersion,
) -> None:
    controller = _controller(sale_view, tmp_path)
    controller.imposta_versione(version)
    output = tmp_path / "export.pdf"
    suggested_paths: list[str] = []
    documents: list[CalendarPdfDocument] = []

    def choose_week(_parent, _title, _label, choices, **_kwargs):
        return next(choice for choice in choices if "14/09" in choice)

    def choose_path(_parent, _title, suggested, _filter):
        suggested_paths.append(suggested)
        return str(output), "Documento PDF (*.pdf)"

    def capture_document(path: str, document: CalendarPdfDocument) -> Path:
        assert Path(path) == output
        documents.append(document)
        return output

    monkeypatch.setattr(sale_module.messages, "choose_option", choose_week)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", choose_path)
    monkeypatch.setattr(sale_module, "write_calendar_pdf", capture_document)
    monkeypatch.setattr(sale_module.messages, "show_message", lambda *_args, **_kwargs: None)

    controller.esporta_pdf()

    assert len(documents) == 1
    assert len(suggested_paths) == 1
    assert f"sale-operatorie-{version.value}-" in Path(suggested_paths[0]).name
    document = documents[0]
    assert document.title == f"Programmazione sale operatorie · {version.value.capitalize()}"
    values = "\n".join(value for row in document.rows for value in row.values)
    assert PATIENT_NAMES[version] in values
    assert all(name not in values for key, name in PATIENT_NAMES.items() if key != version)
    assert not output.exists()
