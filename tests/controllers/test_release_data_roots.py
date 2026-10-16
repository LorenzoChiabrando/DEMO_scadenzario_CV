from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from main import MainWindow
from scripts.verify_synthetic_planning import build_synthetic_catalog
from src import data_paths
from src.models.data_manager import DataManager
from src.models.data_manager_libretto import DataManagerLibretto
from src.models.data_manager_pazienti import DataManagerPazienti
from src.models.data_manager_sale_operatorie import DataManagerSaleOperatorie
from src.optimization import HighsSolver


def test_launching_from_another_directory_should_keep_one_data_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    monkeypatch.delenv("MMSD_DATA_DIR", raising=False)
    monkeypatch.setattr(data_paths, "PROJECT_ROOT", tmp_path / "project")
    monkeypatch.chdir(tmp_path)
    window = MainWindow()
    try:
        gui_directory = Path(window.data_manager_sale_operatorie.dir_sale_operatorie).resolve()
        solver_directory = (
            window.controller_sale_operatorie._data_directory / "sale_operatorie"
        )
        assert gui_directory == solver_directory
        assert not (tmp_path / "mock_data").exists()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


@pytest.mark.skipif(not HighsSolver.is_available(), reason="highspy is unavailable")
@pytest.mark.parametrize("configuration", ["explicit", "environment"])
def test_gui_worker_reads_and_writes_the_selected_catalog_from_another_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configuration: str,
) -> None:
    app = QApplication.instance() or QApplication([])
    monday = date(2026, 11, 30)
    directory = tmp_path / "catalogo dati"
    build_synthetic_catalog(directory, monday, 24)
    cwd = tmp_path / "unrelated"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("MMSD_DATA_DIR", str(
        directory if configuration == "environment" else tmp_path / "ignored"
    ))
    window = MainWindow(directory if configuration == "explicit" else None)
    controller = window.controller_sale_operatorie
    notices = []
    controller._avviso = lambda *args, **kwargs: notices.append(args)
    controller.settimana_display = monday
    controller.modalita_corrente = "PIANIFICAZIONE"
    results = []
    try:
        assert Path(window.data_manager.dir_scadenzario) == directory / "scadenzario"
        assert Path(window.data_manager_libretto.dir_libretti) == directory / "libretti"
        assert Path(window.data_manager_pazienti.dir_pazienti) == directory / "pazienti"
        assert Path(window.data_manager_sale_operatorie.dir_sale_operatorie) == (
            directory / "sale_operatorie"
        )
        assert controller._data_directory == directory
        assert len(window.data_manager_pazienti.get_tutti_pazienti()) == 32
        assert window.sidebar.styleSheet()
        monkeypatch.setenv("MMSD_DATA_DIR", str(tmp_path / "changed-after-launch"))
        controller.pianifica_settimana()
        controller._planning_worker.succeeded.connect(results.append)
        deadline = time.monotonic() + 30
        while controller._planning_worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()
        assert controller._planning_worker is None
        assert results and results[0].result.has_solution, notices
        assert results[0].write_receipt is not None
        assert all(
            path.is_relative_to(directory) for path in results[0].write_receipt.updated_paths
        )
        for operation in results[0].result.schedule:
            patient = window.data_manager_pazienti.get_paziente_by_id(operation.patient_id)
            assert patient["stato"] == "Pianificato"
        assert not list(cwd.iterdir())
        assert not (tmp_path / "ignored").exists()
        assert not (tmp_path / "changed-after-launch").exists()
    finally:
        controller.shutdown_planning()
        app.processEvents()
        window.close()
        window.deleteLater()
        app.processEvents()


def test_standalone_managers_share_the_configured_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("MMSD_DATA_DIR", str(tmp_path / "dati"))
    root = tmp_path / "dati"
    assert Path(DataManager().dir_scadenzario) == root / "scadenzario"
    assert Path(DataManager().dir_libretti) == root / "libretti"
    assert Path(DataManagerLibretto().dir_libretti) == root / "libretti"
    assert Path(DataManagerPazienti().dir_pazienti) == root / "pazienti"
    assert Path(DataManagerSaleOperatorie().dir_sale_operatorie) == root / "sale_operatorie"
    assert DataManagerSaleOperatorie().dir_pazienti == root / "pazienti"
