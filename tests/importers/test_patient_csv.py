from __future__ import annotations

from pathlib import Path

import pytest

from src.importers.patient_csv import PatientCsvError, read_patient_csv


def test_trackcare_semicolon_export_is_normalized(tmp_path: Path) -> None:
    source = tmp_path / "trackcare.csv"
    source.write_text(
        "Nome;Cognome;Priorit�;Diagnosi ICD9;codice diagnosi;"
        "Intervento/procedura ICD9; codice intervento\n"
        "Ada;Test;Classe A;Descrizione sintetica (433.10);433.10;"
        "Procedura sintetica (38.12);38.12\n",
        encoding="utf-8",
    )

    result = read_patient_csv(source)

    assert result.source_format == "TrackCare"
    assert result.delimiter == ";"
    assert len(result.rows) == 1
    assert result.rows[0] == {
        "nome": "Ada",
        "cognome": "Test",
        "codice_diagnosi": "433.10",
        "descrizione_diagnosi": "Descrizione sintetica",
        "codice_intervento": "38.12",
        "descrizione_intervento": "Procedura sintetica",
        "tipo_chirurgia": "Da classificare",
        "complessita": "Da classificare",
        "urgenza": "Alta",
        "durata_intervento": "90",
    }
    assert len(result.warnings) == 3


def test_native_csv_keeps_explicit_values_and_multiple_interventions(
    tmp_path: Path,
) -> None:
    source = tmp_path / "native.csv"
    source.write_text(
        "nome,cognome,diagnosi,codice_intervento,descrizione_intervento,"
        "tipo_chirurgia,complessita,urgenza,durata_intervento\n"
        'Ada,Test,Diagnosi sintetica,"11.1;22.2","Prima;Seconda",'
        'Aperta,Media,Bassa,"30;45"\n',
        encoding="utf-8",
    )

    result = read_patient_csv(source)

    assert result.source_format == "Scadenziario"
    assert result.delimiter == ","
    assert result.rows[0]["descrizione_diagnosi"] == "Diagnosi sintetica"
    assert result.rows[0]["durata_intervento"] == "30;45"
    assert result.warnings == ()


def test_unstructured_text_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "invalid.csv"
    source.write_text("testo senza separatore", encoding="utf-8")

    with pytest.raises(PatientCsvError, match="separatore"):
        read_patient_csv(source)
