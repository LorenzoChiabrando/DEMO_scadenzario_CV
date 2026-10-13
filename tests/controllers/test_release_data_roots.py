from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from main import MainWindow


@pytest.mark.xfail(strict=True, reason="R4: GUI and planner resolve different data roots")
def test_launching_from_another_directory_should_keep_one_data_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.chdir(tmp_path)
    window = MainWindow()
    try:
        gui_directory = Path(window.data_manager_sale_operatorie.dir_sale_operatorie).resolve()
        solver_directory = (
            window.controller_sale_operatorie._project_root / "mock_data/sale_operatorie"
        )
        assert gui_directory == solver_directory
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
