"""Percorso completo tra le sezioni, con la finestra principale e il solver veri.

Libretto (nuovo specializzando) -> Scadenzario (lo assegna in Sala Op. I e convalida il
mese) -> Sale operatorie (pianifica e, la settimana dopo, convalida il Previsto e poi
l'Effettivo) -> Libretto (interventi completati) e Lista pazienti (pazienti operati).
"""

from __future__ import annotations

import tempfile
import time
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from main import MainWindow
from scripts.reset_demo_data import reset_demo_data
from src.calendar_versions import CalendarVersion
from src.optimization import HighsSolver
from src.views.components import messages
from src.views.dialog_assegnazione_turno import DialogAssegnazioneSpecializzando
from src.views.view_nuovo_specializzando import DialogNuovoSpecializzando

pytestmark = pytest.mark.skipif(not HighsSolver.is_available(), reason="HiGHS non disponibile")

# Dati demo generati al 16/10/2026: lo scadenzario di novembre è in bozza e la settimana
# 9-13 novembre non ha ancora interventi.
_REFERENCE = date(2026, 10, 16)
_MONDAY = date(2026, 11, 9)
_WEEK = tuple(_MONDAY + timedelta(days=offset) for offset in range(5))
_NEW_RESIDENT = {"matricola": "FLUSSO-1", "nome": "Test", "cognome": "Flusso"}
_NEW_LABEL = "Flusso T."
_LIBRETTO, _SCADENZARIO, _SALE = 1, 0, 2


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def notices(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Conferma ogni richiesta e registra i messaggi mostrati come ``titolo: testo``."""

    shown: list[str] = []

    def show_message(_parent, title: str, text: str, **_kwargs: str) -> None:
        shown.append(f"{title}: {text}")

    monkeypatch.setattr(messages, "show_message", show_message)
    monkeypatch.setattr(messages, "ask_confirmation", lambda *_args, **_kwargs: True)
    return shown


@pytest.fixture
def window(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[MainWindow]:
    # I backup del planner finiscono nella cartella temporanea di sistema: la isoliamo.
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    reset_demo_data(tmp_path, _REFERENCE)
    main_window = MainWindow(data_directory=tmp_path / "mock_data")
    yield main_window
    main_window.close()
    main_window.deleteLater()
    qt_app.processEvents()


def _wait_until(app: QApplication, condition: Callable[[], bool], timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        app.processEvents()
        if time.monotonic() > deadline:
            pytest.fail("il planner non ha terminato in tempo")
        time.sleep(0.01)
    app.processEvents()


def _create_resident_in_libretto(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> str:
    def fill_and_save(dialog: DialogNuovoSpecializzando) -> int:
        dialog.input_matricola.setText(_NEW_RESIDENT["matricola"])
        dialog.input_nome.setText(_NEW_RESIDENT["nome"])
        dialog.input_cognome.setText(_NEW_RESIDENT["cognome"])
        dialog.combo_livello.setCurrentText("Junior")
        dialog.combo_stato.setCurrentText("Molinette")
        dialog.btn_salva.click()
        return dialog.result()

    monkeypatch.setattr(DialogNuovoSpecializzando, "exec", fill_and_save)
    window.sidebar.setCurrentRow(_LIBRETTO)
    window.view_libretto.btn_aggiungi.click()

    created = [
        record
        for record in window.data_manager_libretto.get_tutti_specializzandi()
        if record["cognome"] == _NEW_RESIDENT["cognome"]
    ]
    assert len(created) == 1
    return created[0]["id"]


def _assign_week_in_roster(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    offered: list[bool] = []

    def pick_new_resident(dialog: DialogAssegnazioneSpecializzando) -> int:
        for index in range(dialog.lista.count()):
            item = dialog.lista.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == _NEW_LABEL:
                offered.append(bool(item.flags() & Qt.ItemFlag.ItemIsEnabled))
                dialog.lista.setCurrentItem(item)
        dialog.btn_assegna.click()
        return dialog.result()

    monkeypatch.setattr(DialogAssegnazioneSpecializzando, "exec", pick_new_resident)
    controller, view = window.controller_scad, window.view_scad
    controller.real_anno, controller.real_mese = _REFERENCE.year, _REFERENCE.month
    window.sidebar.setCurrentRow(_SCADENZARIO)
    view.btn_pianificazione.click()
    assert view.btn_mese_anno.text() == "NOVEMBRE 2026"

    row = view.row_labels.index("Sala Op. I")
    for day in _WEEK:
        view.tabella.clicked.emit(view.tabella.model().index(row, day.day - 1))
    assert offered == [True] * len(_WEEK)

    view.btn_convalida.click()
    assert window.data_manager.get_stato_mese(2026, 11) == "CONVALIDATO"


def _plan_week(window: MainWindow, qt_app: QApplication, notices: list[str]) -> list[dict]:
    controller, view = window.controller_sale_operatorie, window.view_sale_operatorie
    controller.settimana_corrente = _MONDAY - timedelta(weeks=1)
    window.sidebar.setCurrentRow(_SALE)
    view.btn_pianificazione.click()
    assert controller.settimana_display == _MONDAY

    view.btn_pianifica.click()
    _wait_until(qt_app, lambda: controller._planning_worker is None)

    assert any(notice.startswith("Pianificazione completata") for notice in notices), notices
    rooms = window.data_manager_sale_operatorie
    return [op for day in _WEEK for op in rooms.get_operazioni(day.isoformat())]


def _validate_week_a_week_later(window: MainWindow) -> None:
    """Convalida il Previsto (che crea l'Effettivo) e poi l'Effettivo della settimana."""

    controller, view = window.controller_sale_operatorie, window.view_sale_operatorie
    view.btn_indietro.click()
    controller.settimana_corrente = _MONDAY
    view.btn_consultazione.click()
    assert controller.settimana_display == _MONDAY
    assert not view.btn_convalida.isHidden()
    view.btn_convalida.click()
    assert window.data_manager_sale_operatorie.get_stato_settimana(_MONDAY) == "CONVALIDATO"

    view.combo_versione.setCurrentIndex(view.combo_versione.findData(CalendarVersion.EFFETTIVO))
    assert controller.model.version == CalendarVersion.EFFETTIVO
    assert controller.model.get_stato_settimana(_MONDAY) == "BOZZA"
    assert not view.btn_convalida.isHidden()
    view.btn_convalida.click()
    assert controller.model.get_stato_settimana(_MONDAY) == "CONVALIDATO"


def _libretto_activities(window: MainWindow, resident_id: str, tab: str) -> list[dict]:
    """Attività mostrate nel libretto (tab ``completate`` o ``pianificate``)."""

    view = window.view_libretto
    window.sidebar.setCurrentRow(_LIBRETTO)
    for index in range(view.lista_risultati.count()):
        item = view.lista_risultati.item(index)
        if item.data(Qt.ItemDataRole.UserRole) == resident_id:
            view.lista_risultati.setCurrentItem(item)
    view.btn_apri.click()
    getattr(view, f"btn_tab_{tab}").click()
    activities: list[dict] = []
    for index in range(view.lista_attivita.count()):
        day = view.lista_attivita.item(index).data(Qt.ItemDataRole.UserRole)
        if day is not None:
            activities.extend(day["attivita"])
    return activities


def test_a_new_resident_goes_from_libretto_to_roster_to_surgery_and_back(
    qt_app: QApplication,
    window: MainWindow,
    notices: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resident_id = _create_resident_in_libretto(window, monkeypatch)

    _assign_week_in_roster(window, monkeypatch)
    for day in _WEEK:
        assert window.data_manager.get_valore_cella(day.isoformat(), "Sala Op. I") == _NEW_LABEL
        rooms = window.data_manager_sale_operatorie.get_specializzandi(day.isoformat())
        assert rooms.splitlines()[0] == _NEW_LABEL

    operations = _plan_week(window, qt_app, notices)
    first_operator = [op for op in operations if op.get("ruolo_specializzando") == "OR I"]
    assert first_operator, "nessun intervento assegnato al primo operatore"
    assert {op["specializzando"] for op in first_operator} == {_NEW_LABEL}
    assert {op["id_specializzando"] for op in first_operator} == {resident_id}

    _validate_week_a_week_later(window)

    completed = _libretto_activities(window, resident_id, "completate")
    assert sorted((a["data"], a["nome_paziente"], a["attivita"]) for a in completed) == sorted(
        (op_day, op["nome_paziente"], "Intervento Chirurgico (I op.)")
        for op_day, op in (
            (day.isoformat(), op)
            for day in _WEEK
            for op in window.data_manager_sale_operatorie.get_operazioni(day.isoformat())
            if op.get("ruolo_specializzando") == "OR I"
        )
    )
    planned = _libretto_activities(window, resident_id, "pianificate")
    validated_days = {op_day["data"] for op_day in completed}
    assert not [
        activity
        for activity in planned
        if activity["data"] in validated_days and activity["ruolo"] == "Sala Op. I"
    ]

    patients = window.data_manager_pazienti
    assert {patients.get_paziente_by_id(op["id_paziente"])["stato"] for op in operations} == {
        "Completato"
    }
    assert not [notice for notice in notices if "Impossibile" in notice]
