from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

from src.controllers import controller_pazienti
from src.controllers.controller_pazienti import ControllerPazienti
from src.importers.patient_csv import read_patient_csv
from src.models.data_manager_pazienti import DataManagerPazienti
from src.patient_fields import normalize_diagnosis
from src.views.dialog_bulk_pazienti import DialogBulkPazienti
from src.views.view_nuovo_paziente import DialogNuovoPaziente


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    "diagnosis", ["Diagnosi di prova", "Diagnosi di prova (433.10)", "433.10", ""]
)
def test_manual_and_csv_accept_the_same_fields_and_defaults(
    qt_app: QApplication, tmp_path: Path, diagnosis: str
) -> None:
    csv_path = tmp_path / "trackcare.csv"
    csv_path.write_text(
        "Nome,Cognome,Diagnosi ICD9,codice intervento,Intervento/procedura ICD9,Priorità\n"
        f"Pippo,Test,{diagnosis},DEMO-01,Procedura di prova,Classe B\n",
        encoding="utf-8",
    )
    imported = read_patient_csv(csv_path).rows[0]
    manual = DialogNuovoPaziente()
    manual.input_nome.setText(imported["nome"])
    manual.input_cognome.setText(imported["cognome"])
    manual.input_descrizione_diagnosi.setText(diagnosis)
    manual._interventi_rows[0]["inp_codice"].setText(imported["codice_intervento"])
    manual._interventi_rows[0]["inp_desc"].setText(imported["descrizione_intervento"])
    manual.combo_urgenza.setCurrentText(imported["urgenza"])
    manual._valida_e_salva()
    assert manual.result() == QDialog.DialogCode.Accepted
    bulk = DialogBulkPazienti()
    bulk._carica_csv(str(csv_path))
    manual_data, bulk_data = manual.get_dati(), bulk.get_pazienti()[0]
    for field in (
        "nome",
        "cognome",
        "codice_diagnosi",
        "descrizione_diagnosi",
        "interventi",
        "durata_intervento",
        "tipo_chirurgia",
        "complessita",
        "urgenza",
        "stato",
    ):
        assert manual_data[field] == bulk_data[field], field
    manual.deleteLater()
    bulk.deleteLater()


def test_manual_form_requires_only_names_and_hides_optional_fields(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[2]))
    dialog = DialogNuovoPaziente()
    assert dialog.dati_aggiuntivi.isHidden()
    assert dialog._interventi_rows[0]["input_durata"].isHidden()
    dialog._valida_e_salva()
    assert len(messages) == 1
    dialog.input_nome.setText("Pippo")
    dialog._valida_e_salva()
    assert len(messages) == 2
    dialog.input_cognome.setText("Test")
    dialog._valida_e_salva()
    assert dialog.result() == QDialog.DialogCode.Accepted
    data = dialog.get_dati()
    assert data["tipo_chirurgia"] == data["complessita"] == data["urgenza"] == "Da classificare"
    assert data["stato"] == "In Attesa"
    assert data["durata_intervento"] == 90
    dialog.btn_dati_aggiuntivi.click()
    assert not dialog.dati_aggiuntivi.isHidden()
    duration = dialog._interventi_rows[0]["input_durata"]
    assert not duration.isHidden()
    duration.setValue(47)
    dialog.btn_dati_aggiuntivi.click()
    assert dialog.get_dati()["durata_intervento"] == 47
    dialog.deleteLater()


def test_multiple_manual_procedures_share_the_default_csv_total(qt_app: QApplication) -> None:
    dialog = DialogNuovoPaziente()
    dialog.btn_aggiungi_int.click()
    assert [item["durata"] for item in dialog.get_dati()["interventi"]] == [45, 45]
    dialog.btn_aggiungi_int.click()
    assert [item["durata"] for item in dialog.get_dati()["interventi"]] == [30, 30, 30]
    dialog._rimuovi_riga_intervento(dialog._interventi_rows[-1])
    assert dialog.get_dati()["durata_intervento"] == 90
    dialog._interventi_rows[0]["input_durata"].setValue(47)
    dialog.btn_aggiungi_int.click()
    assert [item["durata"] for item in dialog.get_dati()["interventi"]] == [47, 45, 90]
    dialog.deleteLater()


def test_manual_controller_persists_incomplete_patient_and_edit_preserves_diagnosis(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dialog = DialogNuovoPaziente()
    dialog.input_nome.setText("Pippo")
    dialog.input_cognome.setText("Test")
    dialog.input_descrizione_diagnosi.setText("433.10")
    monkeypatch.setattr(controller_pazienti, "DialogNuovoPaziente", lambda _parent: dialog)
    monkeypatch.setattr(QDialog, "exec", lambda self: self._valida_e_salva() or self.result())
    controller = ControllerPazienti.__new__(ControllerPazienti)
    controller.view = QWidget()
    controller.model = DataManagerPazienti(str(tmp_path / "pazienti"))
    controller.aggiorna_lista = lambda: None
    controller.apri_form_aggiunta()
    patients = controller.model.get_tutti_pazienti()
    assert len(patients) == 1
    patient = patients[0]
    assert patient["stato"] == "In Attesa"
    assert patient["modello_ottimizzazione"]["attesa_massima_giorni"] is None
    for _ in range(3):
        edit = DialogNuovoPaziente(paziente_dati=patient)
        assert not edit.dati_aggiuntivi.isHidden()
        assert edit.input_descrizione_diagnosi.text() == ""
        edit._valida_e_salva()
        assert edit.result() == QDialog.DialogCode.Accepted
        patient = controller.model.aggiorna_paziente(patient["id"], edit.get_dati())
        assert patient["codice_diagnosi"] == "433.10"
        assert patient["descrizione_diagnosi"] == ""
        assert patient["diagnosi"] == "[433.10]"
        edit.deleteLater()
    controller.view.deleteLater()
    dialog.deleteLater()


@pytest.mark.parametrize(
    ("code", "description", "expected"),
    [
        ("", "Test (433.10)", ("433.10", "Test", "[433.10] Test")),
        ("", "433.10", ("433.10", "", "[433.10]")),
        ("433.10", "[433.10]", ("433.10", "", "[433.10]")),
        ("", "[433.10] Test", ("433.10", "Test", "[433.10] Test")),
        ("433.10", "Test (111.1)", ("433.10", "Test (111.1)", "[433.10] Test (111.1)")),
        ("", "Test", ("", "Test", "Test")),
        ("", "", ("", "", "")),
    ],
)
def test_shared_diagnosis_normalization(
    code: str, description: str, expected: tuple[str, str, str]
) -> None:
    assert normalize_diagnosis(code, description) == expected
