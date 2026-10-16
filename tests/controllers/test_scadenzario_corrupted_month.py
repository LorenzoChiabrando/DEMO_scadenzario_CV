"""Navigare verso un mese con il file danneggiato lascia lo scadenzario dov'era."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from src.controllers import controller_scadenzario
from src.controllers.controller_scadenzario import ControllerScadenzario
from src.models.data_manager import DataManager
from src.models.json_files import CorruptedDataError
from src.views.view_scadenzario import ViewScadenzario

_CALENDAR_PAGE = 1
_DASHBOARD_PAGE = 0
# Febbraio 2026 va da domenica 1 a sabato 28: gennaio e marzo non condividono con lui
# settimane lavorative, quindi si aprono senza leggerlo (il giro visite legge la settimana).
_CORRUPTED = 2
_LABELS = {1: "GENNAIO 2026", 3: "MARZO 2026", 4: "APRILE 2026"}


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _controller(tmp_path: Path) -> tuple[ViewScadenzario, ControllerScadenzario]:
    """Scadenzario con gennaio e marzo 2026 integri e febbraio danneggiato.

    Febbraio si danneggia dopo l'avvio: il controller apre il mese della data reale.
    """

    resident = {"id": "SP001", "nome": "Ada", "cognome": "Demo", "stato": "Molinette"}
    (tmp_path / "libretti").mkdir()
    (tmp_path / "libretti" / "SP001.json").write_text(json.dumps(resident), encoding="utf-8")
    roster = tmp_path / "scadenzario"
    roster.mkdir()
    for month in ("2026-01", "2026-03"):
        payload = {"metadata": {"stato": "BOZZA"}, "turni": {}}
        (roster / f"{month}.json").write_text(json.dumps(payload), encoding="utf-8")

    view = ViewScadenzario()
    controller = ControllerScadenzario(view, DataManager(roster, tmp_path / "libretti"))
    controller.real_anno, controller.real_mese = 2026, _CORRUPTED - 1
    (roster / "2026-02.json").write_text('{"turni": {', encoding="utf-8")
    controller.model.invalidate_cache()
    return view, controller


def _show(controller: ControllerScadenzario, view: ViewScadenzario, month: int) -> None:
    controller.anno_corrente, controller.mese_corrente = 2026, month
    controller.modalita_corrente = "PIANIFICAZIONE"
    view.stacked_widget.setCurrentIndex(_CALENDAR_PAGE)
    controller.aggiorna_tabella()


def _assert_showing(controller: ControllerScadenzario, view: ViewScadenzario, month: int) -> None:
    assert (controller.anno_corrente, controller.mese_corrente) == (2026, month)
    assert view.btn_mese_anno.text() == _LABELS[month]
    assert view.modello_attivita.date_at(0) == date(2026, month, 1)


@pytest.mark.parametrize(
    ("start", "action"),
    [(_CORRUPTED - 1, "mese_successivo"), (_CORRUPTED + 1, "mese_precedente")],
)
def test_arrows_towards_a_corrupted_month_keep_the_current_month(
    qt_app: QApplication, tmp_path: Path, start: int, action: str
) -> None:
    view, controller = _controller(tmp_path)
    _show(controller, view, start)

    with pytest.raises(CorruptedDataError, match="2026-02.json"):
        getattr(controller, action)()

    _assert_showing(controller, view, start)
    assert controller.modalita_corrente == "PIANIFICAZIONE"
    view.deleteLater()


def test_month_picker_towards_a_corrupted_month_keeps_the_current_month(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view, controller = _controller(tmp_path)
    _show(controller, view, _CORRUPTED + 1)

    class PickFebruary:
        def __init__(self, *_args: object) -> None:
            pass

        def exec(self) -> int:
            return 1

        def get_selezione(self) -> tuple[int, int]:
            return _CORRUPTED, 2026

    monkeypatch.setattr(controller_scadenzario, "DialogMeseAnno", PickFebruary)

    with pytest.raises(CorruptedDataError):
        controller.scegli_mese_anno()

    _assert_showing(controller, view, _CORRUPTED + 1)
    view.deleteLater()


def test_opening_planning_on_a_corrupted_month_stays_on_the_dashboard(
    qt_app: QApplication, tmp_path: Path
) -> None:
    view, controller = _controller(tmp_path)
    controller.anno_corrente, controller.mese_corrente = 2026, _CORRUPTED - 1
    controller.torna_alla_dashboard()

    with pytest.raises(CorruptedDataError):
        controller.apri_calendario("PIANIFICAZIONE")

    assert view.stacked_widget.currentIndex() == _DASHBOARD_PAGE
    assert controller.modalita_corrente is None
    assert (controller.anno_corrente, controller.mese_corrente) == (2026, _CORRUPTED - 1)
    view.deleteLater()


def test_after_the_error_the_next_valid_month_opens_normally(
    qt_app: QApplication, tmp_path: Path
) -> None:
    view, controller = _controller(tmp_path)
    _show(controller, view, _CORRUPTED + 1)
    with pytest.raises(CorruptedDataError):
        controller.mese_precedente()

    controller.mese_successivo()

    _assert_showing(controller, view, _CORRUPTED + 2)
    view.deleteLater()
