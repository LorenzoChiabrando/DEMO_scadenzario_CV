from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QApplication, QDialog

from src.controllers.controller_scadenzario import ControllerScadenzario
from src.models.data_manager import DataManager
from src.views.dialog_assegnazione_turno import DialogAssegnazioneSpecializzando, DialogTipoGuardia
from src.views.view_scadenzario import ViewScadenzario

# Settembre 2026: martedì 15 è la colonna 14, sabato 19 la colonna 18.
_TUESDAY_15 = 14
_SATURDAY_19 = 18


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _write_residents(directory: Path) -> None:
    directory.mkdir(parents=True)
    for index, (name, surname) in enumerate([("Ada", "Demo"), ("Bruno", "Prova")], 1):
        payload = {
            "id": f"SP{index:03d}",
            "nome": name,
            "cognome": surname,
            "livello": "Junior",
            "stato": "Molinette",
        }
        (directory / f"SP{index:03d}.json").write_text(json.dumps(payload), encoding="utf-8")


def _roster(tmp_path: Path) -> tuple[ViewScadenzario, ControllerScadenzario, DataManager]:
    _write_residents(tmp_path / "libretti")
    model = DataManager(str(tmp_path / "scadenzario"), str(tmp_path / "libretti"))
    view = ViewScadenzario()
    controller = ControllerScadenzario(view, model)
    controller.anno_corrente, controller.mese_corrente = 2026, 9
    controller.modalita_corrente = "CORRENTE"
    view.stacked_widget.setCurrentIndex(1)
    controller.aggiorna_tabella()
    return view, controller, model


def _intercept(
    monkeypatch: pytest.MonkeyPatch,
    dialog_class: type[QDialog],
    choose: Callable[[QDialog], None] = lambda dialog: None,
) -> list[QDialog]:
    """Sostituisce exec(): registra il dialog e simula la scelta dell'utente."""

    opened: list[QDialog] = []

    def fake_exec(dialog: QDialog) -> int:
        opened.append(dialog)
        choose(dialog)
        return dialog.result()

    monkeypatch.setattr(dialog_class, "exec", fake_exec)
    return opened


def _pick(label: str) -> Callable[[DialogAssegnazioneSpecializzando], None]:
    def choose(dialog: DialogAssegnazioneSpecializzando) -> None:
        for index in range(dialog.lista.count()):
            item = dialog.lista.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == label:
                dialog.lista.setCurrentItem(item)
        dialog.btn_assegna.click()

    return choose



def _click(view: ViewScadenzario, row: int, column: int) -> None:
    view.tabella.clicked.emit(view.tabella.model().index(row, column))

def _is_selectable(dialog: DialogAssegnazioneSpecializzando, label: str) -> bool:
    for index in range(dialog.lista.count()):
        item = dialog.lista.item(index)
        if item.data(Qt.ItemDataRole.UserRole) == label:
            return bool(item.flags() & Qt.ItemFlag.ItemIsEnabled)
    raise AssertionError(f"{label} non presente nel dialog")


def test_roster_has_no_inline_editors(qt_app: QApplication, tmp_path: Path) -> None:
    view, _controller, _model = _roster(tmp_path)

    assert view.tabella.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    view.deleteLater()


def test_click_on_a_resident_cell_saves_the_choice_from_the_modal(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view, _controller, model = _roster(tmp_path)
    opened = _intercept(monkeypatch, DialogAssegnazioneSpecializzando, _pick("Prova B."))
    row = view.row_labels.index("Sala Op. I")

    _click(view, row, _TUESDAY_15)

    assert len(opened) == 1
    assert model.get_valore_cella("2026-09-15", "Sala Op. I") == "Prova B."
    assert view.tabella.model().index(row, _TUESDAY_15).data() == "Prova B."
    view.deleteLater()


def test_cancelling_the_modal_leaves_the_cell_unchanged(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view, controller, model = _roster(tmp_path)
    model.set_valore_cella("2026-09-15", "Reparto II", "Demo A.")
    controller.aggiorna_tabella()
    _intercept(monkeypatch, DialogAssegnazioneSpecializzando, lambda dialog: dialog.reject())

    _click(view, view.row_labels.index("Reparto II"), _TUESDAY_15)

    assert model.get_valore_cella("2026-09-15", "Reparto II") == "Demo A."
    view.deleteLater()


def test_remove_in_the_modal_clears_the_assignment(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view, controller, model = _roster(tmp_path)
    model.set_valore_cella("2026-09-15", "Day Hospital", "Demo A.")
    controller.aggiorna_tabella()
    _intercept(
        monkeypatch, DialogAssegnazioneSpecializzando, lambda dialog: dialog.btn_rimuovi.click()
    )

    _click(view, view.row_labels.index("Day Hospital"), _TUESDAY_15)

    assert model.get_valore_cella("2026-09-15", "Day Hospital") == ""
    view.deleteLater()


def test_modal_disables_residents_busy_in_another_role_that_day(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view, controller, model = _roster(tmp_path)
    model.set_valore_cella("2026-09-15", "Reparto I", "Demo A.")
    model.set_giro_visite_settimana("2026-09-14", 2026, 9, "Prova B.")
    controller.aggiorna_tabella()
    opened = _intercept(monkeypatch, DialogAssegnazioneSpecializzando)

    _click(view, view.row_labels.index("Sala Op. II"), _TUESDAY_15)

    assert not _is_selectable(opened[0], "Demo A.")
    assert not _is_selectable(opened[0], "Prova B.")
    view.deleteLater()


def test_ward_round_modal_checks_every_day_of_the_week_across_months(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view, controller, model = _roster(tmp_path)
    model.set_valore_cella("2026-10-02", "Sala Op. I", "Demo A.")
    controller.aggiorna_tabella()
    opened = _intercept(monkeypatch, DialogAssegnazioneSpecializzando)

    # Martedì 29/09: la settimana del giro visite termina venerdì 02/10.
    _click(view, view.row_labels.index("Giro Visite"), 28)

    assert not _is_selectable(opened[0], "Demo A.")
    assert _is_selectable(opened[0], "Prova B.")
    view.deleteLater()


def test_guard_type_cell_opens_the_guard_dialog_and_saves_the_code(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view, _controller, model = _roster(tmp_path)
    opened = _intercept(
        monkeypatch, DialogTipoGuardia, lambda dialog: dialog.pulsanti_guardia["PI"].click()
    )
    residents = _intercept(monkeypatch, DialogAssegnazioneSpecializzando)

    _click(view, view.row_labels.index("Tipo Guardia"), _TUESDAY_15)

    assert len(opened) == 1
    assert residents == []
    assert model.get_valore_cella("2026-09-15", "Tipo Guardia") == "PI"
    view.deleteLater()


@pytest.mark.parametrize(
    ("scenario", "row_label", "column"),
    [
        ("storico", "Sala Op. I", _TUESDAY_15),
        ("convalidato", "Sala Op. I", _TUESDAY_15),
        ("weekend", "Sala Op. I", _SATURDAY_19),
        ("riga giorno", "Giorno", _TUESDAY_15),
        ("weekend", "Tipo Guardia", _SATURDAY_19),
    ],
)
def test_read_only_cells_never_open_a_modal(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    row_label: str,
    column: int,
) -> None:
    view, controller, model = _roster(tmp_path)
    if scenario == "storico":
        controller.modalita_corrente = "STORICO"
    if scenario == "convalidato":
        model.set_stato_mese(2026, 9, "CONVALIDATO")
    controller.aggiorna_tabella()
    opened = _intercept(monkeypatch, DialogAssegnazioneSpecializzando)
    opened += _intercept(monkeypatch, DialogTipoGuardia)

    _click(view, view.row_labels.index(row_label), column)

    assert opened == []
    view.deleteLater()
