from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from src.models.json_files import CorruptedDataError
from src.views.components import error_handler
from src.views.components.error_handler import UnexpectedErrorHandler, install_exception_hook

_LOG_FILE = Path("logs") / "mmsd-cv.log"


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def shown(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """Registra i dialog di errore invece di aprirli."""

    dialogs: list[dict[str, str]] = []

    def fake_show_message(_parent, title: str, text: str, *, section: str, kind: str) -> None:
        dialogs.append({"title": title, "text": text, "section": section, "kind": kind})

    monkeypatch.setattr(error_handler.messages, "show_message", fake_show_message)
    return dialogs


@pytest.fixture
def restore_excepthook() -> Iterator[None]:
    previous = sys.excepthook
    yield
    sys.excepthook = previous


def _click_raising(error: Exception) -> None:
    button = QPushButton()

    def fail() -> None:
        raise error

    button.clicked.connect(fail)
    button.click()
    button.deleteLater()


def test_an_error_in_a_click_is_logged_and_shown(
    qt_app: QApplication,
    shown: list[dict[str, str]],
    caplog: pytest.LogCaptureFixture,
    restore_excepthook: None,
) -> None:
    install_exception_hook(_LOG_FILE)

    with caplog.at_level(logging.ERROR):
        _click_raising(CorruptedDataError(Path("scadenzario") / "2026-09.json"))

    assert len(shown) == 1
    assert shown[0]["kind"] == "error"
    assert shown[0]["section"] == "generale"
    assert "scadenzario/2026-09.json" in shown[0]["text"]
    assert str(_LOG_FILE) in shown[0]["text"]
    assert "CorruptedDataError" in caplog.text
    assert "Traceback" in caplog.text


def test_python_errors_show_a_generic_italian_message(
    qt_app: QApplication, shown: list[dict[str, str]], restore_excepthook: None
) -> None:
    install_exception_hook(_LOG_FILE)

    _click_raising(KeyError("turni"))

    assert "errore imprevisto" in shown[0]["text"]
    assert "turni" not in shown[0]["text"]


def test_system_errors_are_described_in_italian(
    qt_app: QApplication, shown: list[dict[str, str]], restore_excepthook: None
) -> None:
    install_exception_hook(_LOG_FILE)

    _click_raising(PermissionError(13, "Permission denied", "dati.json"))

    assert "Permesso negato: dati.json" in shown[0]["text"]


def test_without_a_log_file_the_message_does_not_mention_one(
    qt_app: QApplication, shown: list[dict[str, str]]
) -> None:
    handler = UnexpectedErrorHandler(None, fallback=lambda *_args: None)

    handler(RuntimeError, RuntimeError("x"), None)

    assert "log" not in shown[0]["text"].casefold()


def test_errors_raised_while_the_dialog_is_open_are_only_logged(
    qt_app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    handler = UnexpectedErrorHandler(_LOG_FILE, fallback=lambda *_args: None)
    dialogs: list[str] = []

    def nested_failure(_parent, title: str, _text: str, **_kwargs: str) -> None:
        dialogs.append(title)
        handler(ValueError, ValueError("dentro il dialog"), None)

    monkeypatch.setattr(error_handler.messages, "show_message", nested_failure)

    with caplog.at_level(logging.ERROR):
        handler(RuntimeError, RuntimeError("primo"), None)

    assert dialogs == ["Errore imprevisto"]
    assert "primo" in caplog.text
    assert "dentro il dialog" in caplog.text


def test_a_dialog_that_cannot_open_does_not_hide_the_original_error(
    qt_app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    handler = UnexpectedErrorHandler(_LOG_FILE, fallback=lambda *_args: None)

    def broken_dialog(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("dialog rotto")

    monkeypatch.setattr(error_handler.messages, "show_message", broken_dialog)

    with caplog.at_level(logging.ERROR):
        handler(ValueError, ValueError("originale"), None)

    assert "originale" in caplog.text
    assert "dialog rotto" in caplog.text


def test_ctrl_c_keeps_the_default_behaviour(
    qt_app: QApplication, shown: list[dict[str, str]]
) -> None:
    forwarded: list[type[BaseException]] = []
    handler = UnexpectedErrorHandler(
        _LOG_FILE, fallback=lambda kind, *_args: forwarded.append(kind)
    )

    handler(KeyboardInterrupt, KeyboardInterrupt(), None)

    assert forwarded == [KeyboardInterrupt]
    assert shown == []
