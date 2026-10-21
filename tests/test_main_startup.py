"""Avvio dell'applicazione: dati danneggiati e log su file."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

import main


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def shown(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    dialogs: list[dict[str, str]] = []

    def fake_show_message(_parent, title: str, text: str, *, section: str, kind: str) -> None:
        dialogs.append({"title": title, "text": text, "section": section, "kind": kind})

    monkeypatch.setattr(main.messages, "show_message", fake_show_message)
    return dialogs


@pytest.fixture
def root_logger() -> Iterator[logging.Logger]:
    """Ripristina il root logger dopo ``configure_logging``."""

    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield root
    for handler in root.handlers:
        if handler not in handlers:
            handler.close()
    root.handlers[:], root.level = handlers, level


@pytest.mark.parametrize("section", ["scadenzario", "sale_operatorie"])
def test_a_corrupted_current_month_stops_startup_with_a_clear_message(
    qt_app: QApplication, tmp_path: Path, shown: list[dict[str, str]], section: str
) -> None:
    month = tmp_path / section / f"{date.today():%Y-%m}.json"
    month.parent.mkdir()
    month.write_text('{"metadata": {"stato": "BOZ', encoding="utf-8")

    window = main.open_main_window(lambda: main.MainWindow(data_directory=tmp_path))

    assert window is None
    assert len(shown) == 1
    assert shown[0]["kind"] == "error"
    assert shown[0]["section"] == "generale"
    assert f"{section}/{month.name}" in shown[0]["text"]
    assert month.read_text(encoding="utf-8") == '{"metadata": {"stato": "BOZ'


def test_healthy_data_opens_the_main_window(
    qt_app: QApplication, tmp_path: Path, shown: list[dict[str, str]]
) -> None:
    window = main.open_main_window(lambda: main.MainWindow(data_directory=tmp_path))

    assert isinstance(window, main.MainWindow)
    assert shown == []
    window.close()
    window.deleteLater()


def test_other_startup_errors_reach_the_global_handler(
    qt_app: QApplication, shown: list[dict[str, str]]
) -> None:
    def broken_window() -> main.MainWindow:
        raise RuntimeError("guasto")

    with pytest.raises(RuntimeError, match="guasto"):
        main.open_main_window(broken_window)
    assert shown == []


def test_logging_writes_to_a_rotating_file(tmp_path: Path, root_logger: logging.Logger) -> None:
    log_file = tmp_path / "logs" / "mmsd-cv.log"

    assert main.configure_logging(log_file) == log_file
    logging.getLogger("src.prova").warning("messaggio di prova")

    handlers = [h for h in root_logger.handlers if isinstance(h, RotatingFileHandler)]
    assert len(handlers) == 1
    handlers[0].flush()
    assert "messaggio di prova" in log_file.read_text(encoding="utf-8")


def test_the_executable_logs_in_the_user_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    assert main.default_log_file() == main.PROJECT_ROOT / "logs" / "mmsd-cv.log"

    monkeypatch.setattr(main.sys, "frozen", True, raising=False)

    assert main.default_log_file() == main.user_app_directory() / "logs" / "mmsd-cv.log"


def test_an_unwritable_log_folder_does_not_block_startup(
    tmp_path: Path, root_logger: logging.Logger
) -> None:
    blocker = tmp_path / "logs"
    blocker.write_text("non una cartella", encoding="utf-8")

    assert main.configure_logging(blocker / "mmsd-cv.log") is None
    assert not any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers)
