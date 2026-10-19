"""Tutti i dialog custom usano la stessa cornice con il colore della propria sezione."""

from __future__ import annotations

import datetime
from collections.abc import Callable

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QWidget

from src.controllers.controller_sale_operatorie import ROOM_IDS, ControllerSaleOperatorie
from src.roster_assignment import ResidentOption
from src.views.components.modal_dialog import ModalDialog
from src.views.dialog_assegnazione_turno import DialogAssegnazioneSpecializzando, DialogTipoGuardia
from src.views.dialog_bulk_pazienti import DialogBulkPazienti
from src.views.dialog_mese_anno import DialogMeseAnno
from src.views.view_nuovo_paziente import DialogNuovoPaziente
from src.views.view_nuovo_specializzando import DialogNuovoSpecializzando
from tests.views.dialog_helpers import SECTION_ACCENTS, WARNING_ACCENT, accent_of

_MESI = [
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
]  # fmt: skip


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    ("factory", "section"),
    [
        (lambda: DialogNuovoPaziente(), "pazienti"),
        (lambda: DialogNuovoPaziente(paziente_dati={"nome": "Ada", "cognome": "Demo"}), "pazienti"),
        (lambda: DialogBulkPazienti(), "pazienti"),
        (lambda: DialogNuovoSpecializzando(), "libretto"),
        (lambda: DialogNuovoSpecializzando(spec_dati={"nome": "Ada"}), "libretto"),
        (lambda: DialogMeseAnno(_MESI, 10, 2026), "scadenzario"),
        (
            lambda: DialogAssegnazioneSpecializzando(
                (ResidentOption("Demo A.", "Demo Ada", "Junior"),), "Mar 15/09/2026"
            ),
            "scadenzario",
        ),
        (lambda: DialogTipoGuardia("Mar 15/09/2026"), "scadenzario"),
    ],
    ids=[
        "nuovo-paziente",
        "modifica-paziente",
        "bulk",
        "nuovo-specializzando",
        "modifica-specializzando",
        "mese-anno",
        "assegna-specializzando",
        "tipo-guardia",
    ],
)
def test_dialogs_share_the_frame_with_their_section_color(
    qt_app: QApplication, factory: Callable[[], QDialog], section: str
) -> None:
    dialog = factory()

    assert isinstance(dialog, ModalDialog)
    assert dialog.property("sezione") == section
    assert accent_of(dialog) == SECTION_ACCENTS[section]
    assert dialog.findChildren(QPushButton, "BtnSalvaDialog") or isinstance(
        dialog, DialogTipoGuardia
    )
    dialog.deleteLater()


def test_month_picker_keeps_its_selection_api(qt_app: QApplication) -> None:
    dialog = DialogMeseAnno(_MESI, 10, 2026)

    assert dialog.get_selezione() == (10, 2026)
    dialog.combo_mesi.setCurrentIndex(1)
    dialog.spin_anno.setValue(2027)
    dialog.findChild(QPushButton, "BtnSalvaDialog").click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.get_selezione() == (2, 2027)
    dialog.deleteLater()


class _Rooms:
    def get_pazienti_pianificati_ids(self) -> set[str]:
        return set()

    def get_specializzandi(self, _day: str) -> str:
        return ""

    def get_stato_settimana(self, _monday: datetime.date) -> str:
        return "BOZZA"


class _Waiting:
    def get_pazienti_in_attesa(self) -> list[dict]:
        return [
            {
                "id": "PZ-SYN",
                "nome": "Paziente",
                "cognome": "Sintetico",
                "urgenza": "Media",
                "durata_intervento": 60,
                "data_inserimento": "01/01/2026",
            }
        ]


def _rooms_controller() -> ControllerSaleOperatorie:
    controller = ControllerSaleOperatorie.__new__(ControllerSaleOperatorie)
    controller.view = QWidget()
    controller.model = _Rooms()
    controller.model_paz = _Waiting()
    controller.modalita_corrente = "PIANIFICAZIONE"
    controller._stato_corrente = "BOZZA"
    controller.settimana_display = datetime.date(2026, 9, 14)
    return controller


def _capture(monkeypatch: pytest.MonkeyPatch, answer: int = 0) -> list[QDialog]:
    opened: list[QDialog] = []

    def fake_exec(dialog: QDialog) -> int:
        opened.append(dialog)
        return answer

    monkeypatch.setattr(QDialog, "exec", fake_exec)
    return opened


@pytest.mark.parametrize(
    ("open_dialog", "accent"),
    [
        (lambda c: c._avviso("Info", "Messaggio informativo"), "sale_operatorie"),
        (lambda c: c._avviso("Attenzione", "Messaggio", tipo="warning"), "avviso"),
        (lambda c: c._conferma("Pulisci settimana", "Confermi?"), "sale_operatorie"),
        (
            lambda c: c._mostra_dialog_inserimento_manuale(
                "2026-09-15", datetime.date(2026, 9, 15), dict.fromkeys(ROOM_IDS, 480)
            ),
            "sale_operatorie",
        ),
        (
            lambda c: c._mostra_popup_paziente(
                {"nome_paziente": "Paziente Sintetico", "sala_operatoria": "OR-1"},
                None,
                data_str="2026-09-15",
                op_idx=0,
            ),
            "sale_operatorie",
        ),
    ],
    ids=["avviso-info", "avviso-warning", "conferma", "inserimento-manuale", "scheda-paziente"],
)
def test_operating_room_dialogs_use_the_frame(
    qt_app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    open_dialog: Callable[[ControllerSaleOperatorie], object],
    accent: str,
) -> None:
    controller = _rooms_controller()
    opened = _capture(monkeypatch)

    open_dialog(controller)

    assert len(opened) == 1
    dialog = opened[0]
    assert isinstance(dialog, ModalDialog)
    assert dialog.property("sezione") == "sale_operatorie"
    expected = WARNING_ACCENT if accent == "avviso" else SECTION_ACCENTS[accent]
    assert accent_of(dialog) == expected
    controller.view.deleteLater()


def test_operating_room_confirmation_still_returns_the_answer(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = _rooms_controller()

    _capture(monkeypatch, answer=QDialog.DialogCode.Accepted)
    assert controller._conferma("Titolo", "Messaggio") is True
    _capture(monkeypatch, answer=QDialog.DialogCode.Rejected)
    assert controller._conferma("Titolo", "Messaggio") is False
    controller.view.deleteLater()


def test_patient_sheet_offers_removal_as_a_danger_action(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = _rooms_controller()
    opened = _capture(monkeypatch)

    controller._mostra_popup_paziente(
        {"nome_paziente": "Paziente Sintetico", "sala_operatoria": "OR-1"},
        None,
        data_str="2026-09-15",
        op_idx=0,
    )

    danger = opened[0].findChildren(QPushButton, "BtnPericoloDialog")
    assert [button.text() for button in danger] == ["Rimuovi dal piano"]
    controller.view.deleteLater()
