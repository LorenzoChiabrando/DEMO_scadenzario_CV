from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QFrame, QLabel, QListWidgetItem

from src.roster_assignment import ResidentOption
from src.views.dialog_assegnazione_turno import DialogAssegnazioneSpecializzando, DialogTipoGuardia

_OPTIONS = (
    ResidentOption("Bianchi A.", "Bianchi Anna", "Junior"),
    ResidentOption("Rossi M.", "Rossi Mario", "Senior", conflict="Già in Sala Op. II"),
    ResidentOption("Verdi L.", "Verdi Luca", "Intermediate"),
)


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _item(dialog: DialogAssegnazioneSpecializzando, label: str) -> QListWidgetItem:
    for row in range(dialog.lista.count()):
        item = dialog.lista.item(row)
        if item.data(Qt.ItemDataRole.UserRole) == label:
            return item
    raise AssertionError(f"{label} non trovato")


def _texts(dialog: DialogAssegnazioneSpecializzando, label: str) -> list[str]:
    widget = dialog.lista.itemWidget(_item(dialog, label))
    return [child.text() for child in widget.findChildren(QLabel)]


def test_busy_resident_is_disabled_and_shows_the_reason(qt_app: QApplication) -> None:
    dialog = DialogAssegnazioneSpecializzando(_OPTIONS, "Mar 15/09/2026 · Sala Op. I")

    assert not _item(dialog, "Rossi M.").flags() & Qt.ItemFlag.ItemIsEnabled
    assert "Già in Sala Op. II" in _texts(dialog, "Rossi M.")
    assert _item(dialog, "Bianchi A.").flags() & Qt.ItemFlag.ItemIsEnabled
    assert "Bianchi Anna" in _texts(dialog, "Bianchi A.")
    assert "Junior" in _texts(dialog, "Bianchi A.")
    dialog.deleteLater()


def test_assign_is_enabled_only_after_choosing_a_resident(qt_app: QApplication) -> None:
    dialog = DialogAssegnazioneSpecializzando(_OPTIONS, "Mar 15/09/2026 · Sala Op. I")

    assert not dialog.btn_assegna.isEnabled()
    dialog.lista.setCurrentItem(_item(dialog, "Verdi L."))
    assert dialog.btn_assegna.isEnabled()
    dialog.btn_assegna.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_value() == "Verdi L."
    dialog.deleteLater()


def test_current_assignment_is_preselected_and_can_be_removed(qt_app: QApplication) -> None:
    dialog = DialogAssegnazioneSpecializzando(
        _OPTIONS, "Mar 15/09/2026 · Sala Op. I", current="Bianchi A."
    )

    assert dialog.lista.currentItem().data(Qt.ItemDataRole.UserRole) == "Bianchi A."
    assert dialog.btn_rimuovi.isVisibleTo(dialog)
    dialog.btn_rimuovi.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_value() == ""
    dialog.deleteLater()


def test_remove_is_hidden_when_the_cell_is_empty(qt_app: QApplication) -> None:
    dialog = DialogAssegnazioneSpecializzando(_OPTIONS, "Mar 15/09/2026 · Sala Op. I")

    assert not dialog.btn_rimuovi.isVisibleTo(dialog)
    dialog.deleteLater()


def test_search_hides_non_matching_residents(qt_app: QApplication) -> None:
    dialog = DialogAssegnazioneSpecializzando(_OPTIONS, "Mar 15/09/2026 · Sala Op. I")

    dialog.search.setText("ros")
    assert _item(dialog, "Bianchi A.").isHidden()
    assert not _item(dialog, "Rossi M.").isHidden()
    assert not dialog.lbl_vuoto.isVisibleTo(dialog)

    dialog.search.setText("zzz")
    assert dialog.lbl_vuoto.isVisibleTo(dialog)
    dialog.deleteLater()


def test_double_click_assigns_only_available_residents(qt_app: QApplication) -> None:
    dialog = DialogAssegnazioneSpecializzando(_OPTIONS, "Mar 15/09/2026 · Sala Op. I")

    dialog.lista.itemDoubleClicked.emit(_item(dialog, "Rossi M."))
    assert dialog.result() != QDialog.DialogCode.Accepted

    dialog.lista.itemDoubleClicked.emit(_item(dialog, "Bianchi A."))
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_value() == "Bianchi A."
    dialog.deleteLater()


def test_guard_type_choice_confirms_immediately(qt_app: QApplication) -> None:
    dialog = DialogTipoGuardia("Mar 15/09/2026 · Tipo Guardia", current="L")

    assert list(dialog.pulsanti_guardia) == ["118", "PI", "L"]
    assert dialog.pulsanti_guardia["L"].isChecked()
    dialog.pulsanti_guardia["PI"].click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_value() == "PI"
    dialog.deleteLater()


def test_guard_type_can_be_removed_only_when_set(qt_app: QApplication) -> None:
    empty = DialogTipoGuardia("Mar 15/09/2026 · Tipo Guardia")
    assert not empty.btn_rimuovi.isVisibleTo(empty)
    empty.deleteLater()

    dialog = DialogTipoGuardia("Mar 15/09/2026 · Tipo Guardia", current="118")
    dialog.btn_rimuovi.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_value() == ""
    dialog.deleteLater()


@pytest.mark.parametrize(
    "factory",
    [
        lambda: DialogAssegnazioneSpecializzando(_OPTIONS, "Mar 15/09/2026 · Reparto I"),
        lambda: DialogTipoGuardia("Mar 15/09/2026 · Tipo Guardia"),
    ],
)
def test_dialogs_share_the_modal_frame_and_show_the_context(qt_app: QApplication, factory) -> None:
    dialog = factory()

    assert dialog.isModal()
    assert dialog.findChild(QFrame, "AccentBarDialog") is not None
    assert dialog.findChild(QLabel, "SottoTitoloDialog").text().startswith("Mar 15/09/2026")
    assert "AccentBarDialog" in dialog.styleSheet()
    dialog.deleteLater()
