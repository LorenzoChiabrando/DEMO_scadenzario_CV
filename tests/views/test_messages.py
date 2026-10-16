from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton

from src.data_paths import PROJECT_ROOT
from src.views.components import messages
from src.views.components.modal_dialog import ModalDialog
from tests.views.dialog_helpers import ERROR_ACCENT, SECTION_ACCENTS, WARNING_ACCENT, accent_of


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _intercept(
    monkeypatch: pytest.MonkeyPatch, act: Callable[[ModalDialog], None] = lambda dialog: None
) -> list[ModalDialog]:
    """Sostituisce exec(): registra il dialog e simula l'azione dell'utente."""

    opened: list[ModalDialog] = []

    def fake_exec(dialog: ModalDialog) -> int:
        opened.append(dialog)
        act(dialog)
        return dialog.result()

    monkeypatch.setattr(ModalDialog, "exec", fake_exec)
    return opened


def _button(dialog: QDialog, text: str) -> QPushButton:
    for button in dialog.findChildren(QPushButton):
        if button.text() == text:
            return button
    raise AssertionError(f"pulsante {text!r} non trovato")


@pytest.mark.parametrize(
    ("kind", "accent"),
    [
        ("info", SECTION_ACCENTS["pazienti"]),
        ("warning", WARNING_ACCENT),
        ("error", ERROR_ACCENT),
    ],
)
def test_message_tone_follows_its_kind(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch, kind: str, accent: str
) -> None:
    opened = _intercept(monkeypatch)

    messages.show_message(None, "Titolo", "Testo del messaggio", section="pazienti", kind=kind)

    dialog = opened[0]
    assert dialog.windowTitle() == "Titolo"
    assert dialog.findChild(QLabel, "LblMessaggioDialog").text() == "Testo del messaggio"
    assert _button(dialog, "OK").objectName() == "BtnSalvaDialog"
    assert accent_of(dialog) == accent
    dialog.deleteLater()


def test_unknown_message_kind_is_rejected(qt_app: QApplication) -> None:
    with pytest.raises(ValueError, match="kind"):
        messages.show_message(None, "Titolo", "Testo", section="pazienti", kind="boh")


def test_confirmation_returns_true_only_when_confirmed(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    _intercept(monkeypatch, lambda dialog: _button(dialog, "Convalida").click())
    assert messages.ask_confirmation(
        None, "Titolo", "Testo", section="scadenzario", confirm_text="Convalida"
    )

    _intercept(monkeypatch, lambda dialog: _button(dialog, "Annulla").click())
    assert not messages.ask_confirmation(None, "Titolo", "Testo", section="scadenzario")

    _intercept(monkeypatch, lambda dialog: dialog.reject())
    assert not messages.ask_confirmation(None, "Titolo", "Testo", section="scadenzario")


def test_plain_confirmation_defaults_to_the_primary_action(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = _intercept(monkeypatch)

    messages.ask_confirmation(None, "Titolo", "Testo", section="libretto")

    confirm = _button(opened[0], "Conferma")
    assert confirm.objectName() == "BtnSalvaDialog"
    assert confirm.isDefault()
    assert not _button(opened[0], "Annulla").isDefault()


def test_destructive_confirmation_is_red_and_defaults_to_cancel(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = _intercept(monkeypatch)

    messages.ask_confirmation(
        None, "Elimina", "Testo", section="libretto", confirm_text="Elimina", destructive=True
    )

    confirm = _button(opened[0], "Elimina")
    assert confirm.objectName() == "BtnPericoloDialog"
    assert not confirm.isDefault()
    assert _button(opened[0], "Annulla").isDefault()


def test_option_choice_returns_the_clicked_option(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    options = ["Mese intero", "Settimana 1: 01/10 - 02/10", "Settimana 2: 05/10 - 09/10"]
    opened = _intercept(monkeypatch, lambda dialog: _button(dialog, options[2]).click())

    choice = messages.choose_option(
        None, "Esporta scadenzario", "Intervallo da esportare:", options, section="scadenzario"
    )

    assert choice == options[2]
    option_buttons = opened[0].findChildren(QPushButton, "BtnOpzioneDialog")
    assert [button.text() for button in option_buttons] == options


def test_option_choice_returns_none_when_cancelled(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    _intercept(monkeypatch, lambda dialog: _button(dialog, "Annulla").click())

    choice = messages.choose_option(
        None, "Esporta", "Intervallo:", ["Mese intero"], section="sale_operatorie"
    )

    assert choice is None


def test_option_choice_requires_options(qt_app: QApplication) -> None:
    with pytest.raises(ValueError, match="opzion"):
        messages.choose_option(None, "Esporta", "Intervallo:", [], section="scadenzario")


_NATIVE_DIALOGS = {"QMessageBox", "QInputDialog"}


def _native_dialog_uses(path: Path) -> list[int]:
    """Righe in cui il codice importa o usa QMessageBox/QInputDialog (non i commenti)."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines = []
    for node in ast.walk(tree):
        names: set[str] = set()
        if isinstance(node, ast.ImportFrom | ast.Import):
            names = {alias.name for alias in node.names}
        elif isinstance(node, ast.Name):
            names = {node.id}
        elif isinstance(node, ast.Attribute):
            names = {node.attr}
        if names & _NATIVE_DIALOGS:
            lines.append(node.lineno)
    return sorted(set(lines))


def test_application_code_no_longer_uses_native_message_boxes() -> None:
    sources = sorted((PROJECT_ROOT / "src").rglob("*.py")) + [PROJECT_ROOT / "main.py"]
    offenders = [
        f"{path.relative_to(PROJECT_ROOT)}:{line}"
        for path in sources
        for line in _native_dialog_uses(path)
    ]
    assert offenders == [], "Usare src.views.components.messages"


_LONG_TEXT = (
    "Vuoi convalidare in via definitiva questo mese?\n\n"
    "Una volta convalidato, il mese passerà allo Storico e non sarà più modificabile.\n\n"
    "• 2026-10-05: Sala Op. II\n• 2026-10-06: Sala Op. I, Sala Op. II\n• 2026-10-07: Sala Op. I"
)


def test_long_wrapped_text_is_never_clipped(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown: list[tuple[int, int]] = []

    def show_and_measure(dialog: ModalDialog) -> None:
        dialog.show()
        qt_app.processEvents()
        label = dialog.findChild(QLabel, "LblMessaggioDialog")
        shown.append((label.height(), label.heightForWidth(label.width())))
        dialog.close()

    _intercept(monkeypatch, show_and_measure)
    messages.ask_confirmation(None, "Conferma Convalida", _LONG_TEXT, section="scadenzario")

    visible_height, needed_height = shown[0]
    assert visible_height >= needed_height
