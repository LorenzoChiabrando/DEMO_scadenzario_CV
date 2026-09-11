from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

from src.controllers import controller_pazienti
from src.controllers.controller_pazienti import ControllerPazienti
from src.models import data_manager_pazienti
from src.models.data_manager import DataManager
from src.models.data_manager_pazienti import DataManagerPazienti
from src.optimization import HighsSolver
from src.optimization.exceptions import PlatformDataError
from src.optimization.platform_io import load_platform_context
from src.optimization.platform_service import plan_platform_week
from src.planning_schema import OPTIMIZATION_KEY
from src.views.dialog_bulk_pazienti import _COL_CPX, _COL_DUR, DialogBulkPazienti


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_bulk_preview_storage_classification_and_solver(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 8)

    monkeypatch.setattr(data_manager_pazienti, "datetime", _Clock)
    residents = tmp_path / "mock_data" / "libretti"
    residents.mkdir(parents=True)
    for identifier, surname, level in [("SP001", "Alpha", "Junior"), ("SP002", "Beta", "Senior")]:
        (residents / f"{identifier}.json").write_text(
            json.dumps(
                {
                    "id": identifier,
                    "nome": "Demo",
                    "cognome": surname,
                    "stato": "Molinette",
                    "livello": level,
                }
            ),
            encoding="utf-8",
        )
    manager = DataManagerPazienti(str(tmp_path / "mock_data" / "pazienti"), str(residents))
    csv_path = tmp_path / "trackcare.csv"
    csv_path.write_text(
        "Nome,Cognome,Diagnosi ICD9,codice intervento,Intervento/procedura ICD9,Prioritï¿½\n"
        'Uno,Demo,"Diagnosi (433.10)","38.12;39.1","Prima;Seconda",Classe B\n'
        "Due,Demo,Diagnosi sintetica,38.12,Procedura demo,Classe A\n",
        encoding="utf-8",
    )
    preview = DialogBulkPazienti()
    preview._carica_csv(str(csv_path))
    assert preview.btn_importa.isEnabled()
    assert preview.tabella.cellWidget(0, _COL_CPX).currentText() == "Da classificare"
    preview.tabella.cellWidget(0, _COL_DUR).setText("127")
    monkeypatch.setattr(controller_pazienti, "DialogBulkPazienti", lambda _parent: preview)
    monkeypatch.setattr(
        QDialog, "exec", lambda self: self._conferma_importazione() or self.result()
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    controller = ControllerPazienti.__new__(ControllerPazienti)
    controller.view = QWidget()
    controller.model = manager
    controller.aggiorna_lista = lambda: None
    controller.apri_form_bulk()
    patients = manager.get_tutti_pazienti()
    assert len(patients) == 2
    assert len({patient["id"] for patient in patients}) == 2
    assert all(patient["stato"] == "In Attesa" for patient in patients)
    assert all(patient["tipo_chirurgia"] == "Da classificare" for patient in patients)
    first = next(patient for patient in patients if patient["nome"] == "Uno")
    assert first["codice_diagnosi"] == "433.10"
    assert first["descrizione_diagnosi"] == "Diagnosi"
    assert first[OPTIMIZATION_KEY]["attesa_massima_giorni"] == 60
    assert [item["codice"] for item in first["interventi"]] == ["38.12", "39.1"]
    assert first["durata_intervento"] == 127
    assert [item["durata"] for item in first["interventi"]] == [64, 63]
    monday = date(2026, 9, 14)
    roster = DataManager(str(tmp_path / "mock_data" / "scadenzario"), str(residents))
    for offset in range(5):
        day = (monday + timedelta(days=offset)).isoformat()
        roster.set_valore_cella(day, "Sala Op. I", "Alpha D.")
        roster.set_valore_cella(day, "Sala Op. II", "Beta D.")
    roster.set_stato_mese(2026, 9, "CONVALIDATO")
    with pytest.raises(PlatformDataError, match="Complessità"):
        load_platform_context(tmp_path, monday)
    for patient in patients:
        updated = dict(patient, complessita="Alta", urgenza="Alta")
        manager.aggiorna_paziente(patient["id"], updated_without_config(updated))
    first = manager.get_paziente_by_id(first["id"])
    assert first[OPTIMIZATION_KEY]["attesa_massima_giorni"] == 30
    context = load_platform_context(tmp_path, monday)
    assert all(patient.max_wait_days == 30 for patient in context.scheduling_input.patients)
    if not HighsSolver.is_available():
        pytest.skip("HiGHS unavailable")
    run = plan_platform_week(tmp_path, monday, persist=True)
    assert run.result.has_solution
    assert run.result.objective is not None
    operations = [operation for day in run.plan.days for operation in day.operations]
    assert {op["id_paziente"] for op in operations} == {patient["id"] for patient in patients}
    first_operation = next(op for op in operations if op["id_paziente"] == first["id"])
    assert first_operation["codice_diagnosi"] == "433.10"
    assert first_operation["descrizione_diagnosi"] == "Diagnosi"
    assert len(first_operation["interventi"]) == 2
    assert run.write_receipt is not None
    preview.deleteLater()
    controller.view.deleteLater()


def updated_without_config(patient: dict) -> dict:
    return {key: value for key, value in patient.items() if key != OPTIMIZATION_KEY}


def test_bulk_blocks_invalid_rows_and_clears_old_preview_on_load_failure(
    qt_app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: None)
    path = tmp_path / "rows.csv"
    path.write_text("nome,cognome,durata\nUno,Demo,0\nDue,Demo,90\n", encoding="utf-8")
    dialog = DialogBulkPazienti()
    dialog._carica_csv(str(path))
    assert not dialog.btn_importa.isEnabled()
    dialog.tabella.cellWidget(0, _COL_DUR).setText("47")
    assert dialog.btn_importa.isEnabled()
    assert dialog.get_pazienti()[0]["durata_intervento"] == 47
    dialog._carica_csv(str(tmp_path / "missing.csv"))
    assert dialog.tabella.rowCount() == 0
    assert not dialog.btn_importa.isEnabled()
    dialog.deleteLater()


def test_unknown_urgency_can_be_saved_and_classified_later(tmp_path: Path) -> None:
    manager = DataManagerPazienti(str(tmp_path / "pazienti"))
    patient = manager.crea_nuovo_paziente(
        {
            "nome": "Demo",
            "cognome": "Uno",
            "urgenza": "Da classificare",
            "complessita": "Da classificare",
        }
    )
    assert patient[OPTIMIZATION_KEY]["attesa_massima_giorni"] is None
    patient["urgenza"] = "Media"
    saved = manager.aggiorna_paziente(patient["id"], updated_without_config(patient))
    assert saved[OPTIMIZATION_KEY]["attesa_massima_giorni"] == 60
    custom = dict(saved[OPTIMIZATION_KEY], attesa_massima_giorni=42)
    saved[OPTIMIZATION_KEY] = custom
    manager.aggiorna_paziente(saved["id"], saved)
    saved["urgenza"] = "Alta"
    updated = manager.aggiorna_paziente(saved["id"], updated_without_config(saved))
    assert updated[OPTIMIZATION_KEY]["attesa_massima_giorni"] == 42
