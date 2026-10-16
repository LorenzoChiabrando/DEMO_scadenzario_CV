from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QWidget,
)

from src.views.components.modal_dialog import ModalDialog
from tests.views.dialog_helpers import (
    ERROR_ACCENT,
    SECTION_ACCENTS,
    WARNING_ACCENT,
    accent_of,
    rendered_color,
)


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_frame_shows_accent_bar_title_subtitle_and_separator(qt_app: QApplication) -> None:
    dialog = ModalDialog("Titolo prova", "Sottotitolo prova", section="pazienti")

    assert dialog.isModal()
    assert dialog.windowTitle() == "Titolo prova"
    assert dialog.findChild(QFrame, "AccentBarDialog") is not None
    assert dialog.findChild(QLabel, "TitoloDialog").text() == "Titolo prova"
    assert dialog.findChild(QLabel, "SottoTitoloDialog").text() == "Sottotitolo prova"
    assert dialog.findChild(QFrame, "SeparatoreDialog") is not None
    assert dialog.property("sezione") == "pazienti"
    dialog.deleteLater()


def test_empty_subtitle_is_hidden(qt_app: QApplication) -> None:
    dialog = ModalDialog("Titolo", section="libretto")

    assert not dialog.findChild(QLabel, "SottoTitoloDialog").isVisibleTo(dialog)
    dialog.deleteLater()


def test_unknown_section_is_rejected(qt_app: QApplication) -> None:
    with pytest.raises(ValueError, match="sezione"):
        ModalDialog("Titolo", section="cucina")


def test_unknown_tone_is_rejected(qt_app: QApplication) -> None:
    with pytest.raises(ValueError, match="tono"):
        ModalDialog("Titolo", section="pazienti", tone="urlato")


@pytest.mark.parametrize(("section", "color"), SECTION_ACCENTS.items())
def test_accent_bar_uses_the_section_color(qt_app: QApplication, section: str, color: str) -> None:
    dialog = ModalDialog("Titolo", section=section)

    assert accent_of(dialog) == color
    dialog.deleteLater()


def test_warning_tone_overrides_the_section_color(qt_app: QApplication) -> None:
    dialog = ModalDialog("Attenzione", section="sale_operatorie", tone="avviso")

    assert accent_of(dialog) == WARNING_ACCENT
    dialog.deleteLater()


@pytest.mark.parametrize(("section", "color"), SECTION_ACCENTS.items())
def test_primary_button_uses_the_section_color(
    qt_app: QApplication, section: str, color: str
) -> None:
    dialog = ModalDialog("Titolo", section=section)
    button = dialog.make_button("Salva", "primary")
    dialog.add_footer(button)
    dialog.ensurePolished()
    button.ensurePolished()
    button.resize(160, 44)

    assert rendered_color(button, 6, 22) == color
    dialog.deleteLater()


@pytest.mark.parametrize(
    ("role", "object_name"),
    [
        ("primary", "BtnSalvaDialog"),
        ("secondary", "BtnAnnullaDialog"),
        ("danger", "BtnPericoloDialog"),
    ],
)
def test_buttons_have_a_role_name_and_a_readable_size(
    qt_app: QApplication, role: str, object_name: str
) -> None:
    dialog = ModalDialog("Titolo", section="scadenzario")
    button = dialog.make_button("Rimuovi assegnazione", role)

    assert isinstance(button, QPushButton)
    assert button.objectName() == object_name
    assert button.height() == 44
    assert button.minimumWidth() >= 120
    dialog.deleteLater()


def test_unknown_button_role_is_rejected(qt_app: QApplication) -> None:
    dialog = ModalDialog("Titolo", section="scadenzario")

    with pytest.raises(ValueError, match="ruolo"):
        dialog.make_button("Boh", "fluo")
    dialog.deleteLater()


def test_footer_puts_danger_left_and_actions_right(qt_app: QApplication) -> None:
    dialog = ModalDialog("Titolo", section="sale_operatorie")
    remove = dialog.make_button("Rimuovi", "danger")
    cancel = dialog.make_button("Annulla", "secondary")
    confirm = dialog.make_button("Conferma", "primary")

    dialog.add_footer(cancel, confirm, leading=remove)
    dialog.resize(700, 300)
    dialog.show()
    qt_app.processEvents()

    assert remove.x() < cancel.x() < confirm.x()
    assert cancel.x() - remove.geometry().right() > 100
    assert dialog.width() - confirm.geometry().right() < 60
    dialog.close()
    dialog.deleteLater()


def test_body_receives_content_and_can_scroll(qt_app: QApplication) -> None:
    plain = ModalDialog("Titolo", section="pazienti")
    assert plain.findChild(QScrollArea) is None

    dialog = ModalDialog("Titolo", section="pazienti", scrollable=True)
    label = QLabel("contenuto")
    dialog.body.addWidget(label)

    scroll = dialog.findChild(QScrollArea)
    assert scroll is not None
    assert scroll.widget().isAncestorOf(label)
    plain.deleteLater()
    dialog.deleteLater()


def test_extra_section_styles_are_loaded_before_the_common_frame(qt_app: QApplication) -> None:
    dialog = ModalDialog("Titolo", section="pazienti", extra_styles=("pazienti.qss",))

    sheet = dialog.styleSheet()
    assert "ListaRisultati" in sheet
    assert sheet.index("ListaRisultati") < sheet.index("AccentBarDialog")
    assert accent_of(dialog) == SECTION_ACCENTS["pazienti"]
    dialog.deleteLater()


def _has_dark_pixels(widget: QWidget, from_x: int) -> bool:
    image = widget.grab().toImage()
    return any(
        image.pixelColor(x, y).lightness() < 160
        for x in range(from_x, image.width() - 5)
        for y in range(6, image.height() - 6)
    )


@pytest.mark.parametrize("make_field", [QComboBox, QSpinBox], ids=["combo", "spinbox"])
def test_field_arrows_are_actually_drawn(qt_app: QApplication, make_field) -> None:
    dialog = ModalDialog("Titolo", section="scadenzario")
    field = make_field()
    field.setObjectName("ComboDialog" if make_field is QComboBox else "InputDialog")
    field.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    if isinstance(field, QComboBox):
        field.addItem("")
    dialog.body.addWidget(field)
    dialog.show()
    field.setFixedSize(200, 44)
    qt_app.processEvents()

    assert _has_dark_pixels(field, from_x=200 - 26)
    assert "data:image" not in dialog.styleSheet()
    dialog.close()
    dialog.deleteLater()


def test_error_tone_overrides_the_section_color(qt_app: QApplication) -> None:
    dialog = ModalDialog("Errore", section="pazienti", tone="errore")

    assert accent_of(dialog) == ERROR_ACCENT
    dialog.deleteLater()
