from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtCore import QByteArray, QMimeData, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QWidget,
)

from src.controllers.controller_sale_operatorie import ControllerSaleOperatorie
from src.views.dialog_bulk_pazienti import _COL_DUR, DialogBulkPazienti
from src.views.view_libretto import ViewLibretto
from src.views.view_nuovo_paziente import DialogNuovoPaziente
from src.views.view_nuovo_specializzando import DialogNuovoSpecializzando
from src.views.view_sale_operatorie import (
    _OPERATION_MIME_TYPE,
    TabellaOperatorie,
    ViewSaleOperatorie,
)
from src.views.view_scadenzario import ViewScadenzario


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    return app


class _MimeEvent:
    def __init__(self, mime: QMimeData):
        self._mime = mime

    def mimeData(self) -> QMimeData:
        return self._mime


def test_operation_drag_accepts_only_valid_internal_payload(qt_app: QApplication) -> None:
    table = TabellaOperatorie()
    table.setColumnCount(5)
    table.setRowCount(8)
    table.set_drop_targets({0: 4, 1: 3})

    valid_mime = QMimeData()
    valid_mime.setData(_OPERATION_MIME_TYPE, QByteArray(b"0:1"))
    text_mime = QMimeData()
    text_mime.setText("0:1")
    negative_mime = QMimeData()
    negative_mime.setData(_OPERATION_MIME_TYPE, QByteArray(b"0:-1"))

    assert table._decode_drag_payload(_MimeEvent(valid_mime)) == (0, 1)
    assert table._decode_drag_payload(_MimeEvent(text_mime)) is None
    assert table._decode_drag_payload(_MimeEvent(negative_mime)) is None
    table.deleteLater()


def test_operation_card_displays_the_physical_room(qt_app: QApplication) -> None:
    view = ViewSaleOperatorie()
    card = view.crea_widget_operazione(
        {
            "nome_paziente": "Synthetic",
            "id_paziente": "PZ-SYN",
            "codice_intervento": "00.00",
            "ora_inizio": "08:00",
            "ora_fine": "09:00",
            "durata": 60,
            "sala_operatoria": "OR-2",
        }
    )

    badge = card.findChild(QLabel, "BadgeSalaOp")
    reference = card.findChild(QLabel, "LblSubOp")
    assert badge is not None
    assert badge.text() == "OR-2"
    assert reference is not None
    assert reference.text() == "ICD-9: 00.00"
    assert all("PZ-SYN" not in label.text() for label in card.findChildren(QLabel))
    view.deleteLater()


def _card_in_day_column(view: ViewSaleOperatorie, width: int, **fields: object) -> QWidget:
    """Show an operation card in a weekly-table day column ``width`` px wide."""
    view.stacked_widget.setCurrentIndex(1)
    view.resize(1600, 900)
    view.show()
    view.tabella.setColumnCount(5)  # Monday to Friday, as the controller lays out a week
    view.tabella.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
    view.tabella.setColumnWidth(0, width)
    card = view.crea_widget_operazione(
        {
            "nome_paziente": "Synthetic",
            "codice_intervento": "00.00",
            "ora_inizio": "08:00",
            "ora_fine": "12:45",
            "durata": 285,
            "sala_operatoria": "OR-1",
            "complessita": "Media",
            **fields,
        }
    )
    view.tabella.setCellWidget(2, 0, card)
    return card


def _fits(label: QLabel) -> bool:
    return label.fontMetrics().horizontalAdvance(label.text()) <= label.contentsRect().width()


def _first_row(card: QWidget) -> tuple[QLabel, QLabel, QLabel]:
    room, time, duration = (
        card.findChild(QLabel, name) for name in ("BadgeSalaOp", "LblOraOp", "BadgeDurataOp")
    )
    return room, time, duration


# Day column width of the weekly table for each window width, measured in the full app.
@pytest.mark.parametrize(
    "width", [159, 176, 191, 210, 287], ids=["1280", "1366", "1440", "1536", "1920"]
)
def test_operation_card_never_cuts_room_and_time(qt_app: QApplication, width: int) -> None:
    view = ViewSaleOperatorie()
    card = _card_in_day_column(view, width)
    qt_app.processEvents()

    room, time, duration = _first_row(card)
    assert room.isVisible() and time.isVisible()
    for label in (room, time, duration):
        if label.isVisible():
            assert label.width() >= label.sizeHint().width(), f"{label.text()!r} is squeezed"
            assert label.geometry().right() < card.width(), f"{label.text()!r} overflows"
    # The time range already gives the duration: its badge only goes when there is no room.
    assert duration.isVisible() or width < 287
    view.close()
    view.deleteLater()


def test_operation_card_duration_badge_returns_when_the_column_widens(
    qt_app: QApplication,
) -> None:
    view = ViewSaleOperatorie()
    card = _card_in_day_column(view, 159)
    qt_app.processEvents()
    duration = _first_row(card)[2]
    assert not duration.isVisible()

    view.tabella.setColumnWidth(0, 287)
    qt_app.processEvents()

    assert duration.isVisible()
    assert duration.width() >= duration.sizeHint().width()
    view.close()
    view.deleteLater()


@pytest.mark.parametrize("width", [159, 191, 287], ids=["1280", "1440", "1920"])
def test_operation_card_shows_only_whole_icd_codes(qt_app: QApplication, width: int) -> None:
    view = ViewSaleOperatorie()
    card = _card_in_day_column(
        view, width, interventi=[{"codice": "39.50"}, {"codice": "39.90"}]
    )
    qt_app.processEvents()

    codes = card.findChild(QLabel, "LblSubOp")
    assert _fits(codes), f"{codes.text()!r} is cut"
    # A cut "39.90" reads as "39.9", another valid code: hidden codes are counted instead.
    shown = re.findall(r"\d+\.\d+", codes.text())
    assert shown == ["39.50", "39.90"][: len(shown)] and shown
    assert len(shown) == 2 or codes.text().endswith("+1")
    if width == 287:
        assert codes.text() == "ICD-9: 39.50  ·  39.90"
    view.close()
    view.deleteLater()


@pytest.mark.parametrize("width", [159, 287], ids=["1280", "1920"])
def test_operation_card_elides_a_long_patient_name(qt_app: QApplication, width: int) -> None:
    view = ViewSaleOperatorie()
    name = "Synthetic Patient Longname"
    card = _card_in_day_column(view, width, nome_paziente=name)
    qt_app.processEvents()

    label = card.findChild(QLabel, "LblNomePazOp")
    assert _fits(label), f"{label.text()!r} is cut"
    assert label.text() == name if width == 287 else label.text().endswith("…")
    view.close()
    view.deleteLater()


def test_operation_popup_clarifies_dates_identifier_and_residents(
    qt_app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Schedule:
        def get_specializzandi(self, _day: str) -> str:
            return "Rossi G.\nBianchi A."

    controller = ControllerSaleOperatorie.__new__(ControllerSaleOperatorie)
    controller.view = QWidget()
    controller.model = _Schedule()
    controller.modalita_corrente = "STORICO"
    controller._stato_corrente = "CONVALIDATO"
    captured: set[str] = set()

    def _capture(dialog: QDialog) -> int:
        captured.update(label.text() for label in dialog.findChildren(QLabel))
        return 0

    monkeypatch.setattr(QDialog, "exec", _capture)
    controller._mostra_popup_paziente(
        {
            "nome_paziente": "Paziente Sintetico",
            "id_paziente": "PZ-SYN",
            "ora_inizio": "08:00",
            "ora_fine": "09:00",
            "durata": 60,
            "sala_operatoria": "OR-2",
            "diagnosi": "Diagnosi sintetica",
            "codice_intervento": "00.00",
            "intervento": "Procedura sintetica",
            "chirurgo": "Chirurgo Sintetico",
        },
        {
            "tipo_chirurgia": "Aperta",
            "complessita": "Media",
            "urgenza": "Media",
            "data_inserimento": "01/05/2026",
        },
        data_str="2026-05-05",
        op_idx=0,
    )

    assert all("PZ-SYN" not in text for text in captured)
    assert "DATA OPERAZIONE" in captured
    assert "05/05/2026" in captured
    assert "SPECIALIZZANDI" in captured
    assert "Rossi G.\nBianchi A." in captured
    assert "DATA INSERIMENTO" in captured
    controller.view.deleteLater()


def test_bulk_duration_change_keeps_intervention_details_consistent(
    qt_app: QApplication,
) -> None:
    root = Path(__file__).resolve().parents[2]
    dialog = DialogBulkPazienti()
    dialog._carica_csv(str(root / "mock_data" / "template_bulk_pazienti_A.csv"))

    patients = dialog.get_pazienti()
    assert len(patients) == 8
    assert [item["durata"] for item in patients[1]["interventi"]] == [90, 60]

    duration_combo = dialog.tabella.cellWidget(1, _COL_DUR)
    duration_combo.setText("120")
    updated_patient = dialog.get_pazienti()[1]

    assert updated_patient["durata_intervento"] == 120
    assert sum(item["durata"] for item in updated_patient["interventi"]) == 120
    dialog.deleteLater()


def test_new_patient_uses_structured_diagnosis_and_numeric_duration(
    qt_app: QApplication,
) -> None:
    dialog = DialogNuovoPaziente()
    duration = dialog._interventi_rows[0]["input_durata"]

    assert isinstance(duration, QSpinBox)
    duration.setValue(47)
    dialog.input_nome.setText("Ada")
    dialog.input_cognome.setText("Test")
    dialog.input_codice_diagnosi.setText("433.10")
    dialog.input_descrizione_diagnosi.setText("Diagnosi sintetica")
    data = dialog.get_dati()

    assert data["codice_diagnosi"] == "433.10"
    assert data["descrizione_diagnosi"] == "Diagnosi sintetica"
    assert data["durata_intervento"] == 47
    dialog.deleteLater()


def test_imported_patient_can_remain_unclassified_while_being_edited(
    qt_app: QApplication,
) -> None:
    dialog = DialogNuovoPaziente(
        paziente_dati={
            "nome": "Ada",
            "cognome": "Test",
            "codice_diagnosi": "433.10",
            "descrizione_diagnosi": "Diagnosi sintetica",
            "interventi": [{"codice": "00.00", "descrizione": "Procedura sintetica", "durata": 90}],
            "tipo_chirurgia": "Da classificare",
            "complessita": "Da classificare",
            "urgenza": "Media",
            "stato": "In Attesa",
        }
    )

    assert dialog.combo_tipo.currentText() == "Da classificare"
    assert dialog.combo_complessita.currentText() == "Da classificare"
    dialog.deleteLater()


def test_libretto_shows_day_metadata_without_a_save_button(
    qt_app: QApplication,
) -> None:
    view = ViewLibretto()

    labels = {label.text() for label in view.findChildren(QLabel)}
    assert "TRAINING SCORE" not in labels
    assert not any("Salva orario" in button.text() for button in view.findChildren(QPushButton))
    assert view.inp_meta_ora_inizio.isReadOnly()
    assert view.inp_meta_ora_fine.isReadOnly()
    view.popola_dettaglio_giorno(
        "2026-09-08",
        [
            {
                "data": "2026-09-08",
                "ora_inizio": "09:00",
                "ora_fine": "12:00",
                "attivita": "Giro Visite",
                "sede": "Reparto",
                "tipo": "pianificata",
            }
        ],
        {},
        on_save=lambda _activity: None,
    )
    assert view.inp_meta_ora_inizio.text() == "09:00"
    assert view.inp_meta_ora_fine.text() == "12:00"
    view.deleteLater()


def test_intermediate_training_level_is_available(qt_app: QApplication) -> None:
    dialog = DialogNuovoSpecializzando()

    assert dialog.combo_livello.findText("Intermediate") >= 0
    dialog.deleteLater()


def test_month_roster_uses_new_labels_and_compact_controls(qt_app: QApplication) -> None:
    view = ViewScadenzario()
    view.resize(1200, 800)
    view.set_compact_mode(True)

    model = view.tabella.model()
    assert model.headerData(2, Qt.Orientation.Vertical) == "I Rep"
    assert model.headerData(3, Qt.Orientation.Vertical) == "II Rep"
    assert view.btn_vista_mese.isChecked()
    assert view.btn_esporta_pdf.text() == "Esporta PDF"
    view.deleteLater()

def test_operating_rooms_offer_read_only_month_overview(qt_app: QApplication) -> None:
    view = ViewSaleOperatorie()
    view.set_month_mode(True)

    assert view._month_mode is True
    assert view.btn_vista_mese.isChecked()
    assert view.tabella.verticalHeaderItem(1).text() == "Spec."
    view.deleteLater()
