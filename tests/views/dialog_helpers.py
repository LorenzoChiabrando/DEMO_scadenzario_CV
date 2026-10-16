"""Helper condivisi dai test dei dialog modali."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QWidget

from src.views.components.modal_dialog import ModalDialog

SECTION_ACCENTS = {
    "pazienti": "#0369a1",
    "libretto": "#4338ca",
    "scadenzario": "#4338ca",
    "sale_operatorie": "#6f42c1",
    "generale": "#334155",
}
WARNING_ACCENT = "#d97706"
ERROR_ACCENT = "#b91c1c"


def rendered_color(widget: QWidget, x: int, y: int) -> str:
    """Colore effettivamente disegnato da Qt nel punto indicato."""

    return widget.grab().toImage().pixelColor(x, y).name()


def accent_of(dialog: ModalDialog) -> str:
    """Colore effettivamente disegnato nella barra in alto del dialog."""

    dialog.ensurePolished()
    bar = dialog.findChild(QFrame, "AccentBarDialog")
    assert bar is not None, "barra colorata mancante"
    bar.resize(40, bar.height())
    return rendered_color(bar, 20, 2)
