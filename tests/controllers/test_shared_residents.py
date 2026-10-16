"""Le modifiche all'anagrafica fatte dal Libretto arrivano subito allo scadenzario."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.controllers.controller_scadenzario import ControllerScadenzario
from src.models.data_manager import DataManager
from src.models.data_manager_libretto import DataManagerLibretto
from src.views.dialog_assegnazione_turno import DialogAssegnazioneSpecializzando
from src.views.view_scadenzario import ViewScadenzario

# Settembre 2026: martedì 15 è la colonna 14.
_TUESDAY_15 = 14


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _form(name: str, surname: str, stato: str = "Molinette") -> dict[str, str]:
    return {
        "matricola": "M000",
        "nome": name,
        "cognome": surname,
        "livello": "Junior",
        "stato": stato,
    }


def _sections(
    tmp_path: Path, *forms: dict[str, str]
) -> tuple[DataManagerLibretto, ViewScadenzario, ControllerScadenzario]:
    """Libretto e scadenzario aperti sulla stessa cartella dati, come in ``MainWindow``.

    Prima dell'apertura esistono "Demo A." e gli specializzandi di ``forms``.
    """

    libretto = DataManagerLibretto(tmp_path / "libretti")
    for form in (_form("Ada", "Demo"), *forms):
        libretto.crea_nuovo_specializzando(form)
    view = ViewScadenzario()
    controller = ControllerScadenzario(
        view, DataManager(tmp_path / "scadenzario", tmp_path / "libretti")
    )
    controller.anno_corrente, controller.mese_corrente = 2026, 9
    controller.modalita_corrente = "CORRENTE"
    view.stacked_widget.setCurrentIndex(1)
    controller.aggiorna_tabella()
    return libretto, view, controller


def _modal_labels(
    view: ViewScadenzario, monkeypatch: pytest.MonkeyPatch
) -> dict[str, bool]:
    """Apre il modal di Sala Op. I e restituisce ``{sigla: selezionabile}``."""

    opened: list[DialogAssegnazioneSpecializzando] = []

    def fake_exec(dialog: DialogAssegnazioneSpecializzando) -> int:
        opened.append(dialog)
        return dialog.result()

    monkeypatch.setattr(DialogAssegnazioneSpecializzando, "exec", fake_exec)
    row = view.row_labels.index("Sala Op. I")
    view.tabella.clicked.emit(view.tabella.model().index(row, _TUESDAY_15))
    labels: dict[str, bool] = {}
    for index in range(opened[0].lista.count()):
        item = opened[0].lista.item(index)
        enabled = bool(item.flags() & Qt.ItemFlag.ItemIsEnabled)
        labels[item.data(Qt.ItemDataRole.UserRole)] = enabled
    return labels


def test_resident_created_in_the_libretto_is_offered_without_restart(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    libretto, view, _controller = _sections(tmp_path)

    libretto.crea_nuovo_specializzando(_form("Bruno", "Nuovo"))

    assert _modal_labels(view, monkeypatch) == {"Demo A.": True, "Nuovo B.": True}
    view.deleteLater()


def test_resident_moved_to_another_site_is_no_longer_offered(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    libretto, view, _controller = _sections(tmp_path, _form("Bruno", "Nuovo"))

    libretto.aggiorna_specializzando("SP002", _form("Bruno", "Nuovo", "Altra Sede"))

    assert _modal_labels(view, monkeypatch) == {"Demo A.": True}
    view.deleteLater()


def test_resident_view_lists_a_resident_created_after_opening_the_month(
    qt_app: QApplication, tmp_path: Path
) -> None:
    libretto, view, controller = _sections(tmp_path)

    libretto.crea_nuovo_specializzando(_form("Bruno", "Nuovo"))
    controller.aggiorna_tabella()

    model = view.modello_specializzandi
    labels = [model.headerData(row, Qt.Orientation.Vertical) for row in range(model.rowCount())]
    assert labels == ["Demo A.", "Nuovo B."]
    view.deleteLater()
