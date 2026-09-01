from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


class PatientCsvError(ValueError):
    """Errore di lettura o formato del CSV."""


@dataclass(frozen=True, slots=True)
class PatientCsvResult:
    """Risultato dell'importazione CSV."""

    rows: tuple[dict[str, str], ...]
    delimiter: str
    source_format: str
    warnings: tuple[str, ...]


_ALIASES = {
    "nome": ("nome",),
    "cognome": ("cognome",),
    "codice_diagnosi": ("codice_diagnosi", "codice_diagnosi_icd9"),
    "descrizione_diagnosi": (
        "descrizione_diagnosi",
        "diagnosi_descrittiva",
        "diagnosi_icd9",
        "diagnosi",
    ),
    "codice_intervento": ("codice_intervento", "codice_procedura"),
    "descrizione_intervento": (
        "descrizione_intervento",
        "intervento_procedura_icd9",
        "procedura",
    ),
    "tipo_chirurgia": ("tipo_chirurgia", "tipo_chir"),
    "complessita": ("complessita",),
    "urgenza": ("urgenza", "priorita", "priorit", "classe_priorita"),
    "durata_intervento": ("durata_intervento", "durata", "durata_minuti"),
}

_TRACKCARE_MARKERS = {
    "idpaziente",
    "numero_in_lista_di_attesa",
    "diagnosi_icd9",
    "intervento_procedura_icd9",
    "stato_lista",
}


def normalize_header(value: str) -> str:
    """Normalizza un'intestazione CSV per il confronto."""

    without_replacement = value.replace("\ufffd", "")
    decomposed = unicodedata.normalize("NFKD", without_replacement)
    ascii_like = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", ascii_like.casefold()).strip("_")


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise PatientCsvError("Il file non è codificato in UTF-8 o Windows-1252.")


def _detect_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        counts = {delimiter: sample.count(delimiter) for delimiter in (",", ";", "\t", "|")}
        delimiter = max(counts, key=counts.get)
        if counts[delimiter] == 0:
            raise PatientCsvError(
                "Non è stato possibile riconoscere il separatore del CSV."
            ) from None
        return delimiter


def _first_value(row: dict[str, str], aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        value = row.get(alias, "").strip()
        if value:
            return value
    return ""


def _code_from_description(description: str) -> str:
    match = re.search(r"\(([A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*)\)\s*$", description)
    return match.group(1) if match else ""


def _remove_terminal_code(description: str, code: str) -> str:
    if not description or not code:
        return description
    return re.sub(rf"\s*\({re.escape(code)}\)\s*$", "", description).strip()


def _map_urgency(value: str) -> str:
    normalized = normalize_header(value)
    direct = {"alta": "Alta", "media": "Media", "bassa": "Bassa"}
    if normalized in direct:
        return direct[normalized]
    match = re.search(r"(?:classe_?)?([abcd])(?:_|$)", normalized)
    if not match:
        return value.strip()
    return {"a": "Alta", "b": "Media", "c": "Bassa", "d": "Bassa"}[match.group(1)]


def read_patient_csv(path: str | Path) -> PatientCsvResult:
    """Legge un CSV nativo o TrackCare e normalizza le righe importate."""

    csv_path = Path(path)
    try:
        text = _read_text(csv_path)
    except OSError as error:
        raise PatientCsvError(f"Impossibile leggere il file: {error}") from error

    delimiter = _detect_delimiter(text[:8192])
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    if not reader.fieldnames:
        raise PatientCsvError("Il file CSV non contiene una riga di intestazione.")

    normalized_headers = [normalize_header(header or "") for header in reader.fieldnames]
    if not any(normalized_headers):
        raise PatientCsvError("Le intestazioni del CSV non sono riconoscibili.")

    source_format = "TrackCare" if set(normalized_headers) & _TRACKCARE_MARKERS else "Scadenziario"
    normalized_rows: list[dict[str, str]] = []
    for source_row in reader:
        row = {
            normalize_header(header or ""): (value or "").strip()
            for header, value in source_row.items()
            if header is not None
        }
        if not any(row.values()):
            continue

        diagnosis_description = _first_value(row, _ALIASES["descrizione_diagnosi"])
        diagnosis_code = _first_value(row, _ALIASES["codice_diagnosi"])
        diagnosis_code = diagnosis_code or _code_from_description(diagnosis_description)
        diagnosis_description = _remove_terminal_code(diagnosis_description, diagnosis_code)

        intervention_description = _first_value(row, _ALIASES["descrizione_intervento"])
        intervention_code = _first_value(row, _ALIASES["codice_intervento"])
        intervention_code = intervention_code or _code_from_description(intervention_description)
        intervention_description = _remove_terminal_code(
            intervention_description, intervention_code
        )

        normalized_rows.append(
            {
                "nome": _first_value(row, _ALIASES["nome"]),
                "cognome": _first_value(row, _ALIASES["cognome"]),
                "codice_diagnosi": diagnosis_code,
                "descrizione_diagnosi": diagnosis_description,
                "codice_intervento": intervention_code,
                "descrizione_intervento": intervention_description,
                "tipo_chirurgia": _first_value(row, _ALIASES["tipo_chirurgia"])
                or "Da classificare",
                "complessita": _first_value(row, _ALIASES["complessita"]) or "Da classificare",
                "urgenza": _map_urgency(_first_value(row, _ALIASES["urgenza"])),
                "durata_intervento": _first_value(row, _ALIASES["durata_intervento"]) or "90",
            }
        )

    warnings: list[str] = []
    header_set = set(normalized_headers)
    if not header_set.intersection(_ALIASES["tipo_chirurgia"]):
        warnings.append("Tipo chirurgia assente: impostato su 'Da classificare'.")
    if not header_set.intersection(_ALIASES["complessita"]):
        warnings.append("Complessità assente: impostata su 'Da classificare'.")
    if not header_set.intersection(_ALIASES["durata_intervento"]):
        warnings.append("Durata assente: impostata a 90 minuti e modificabile in anteprima.")

    return PatientCsvResult(
        rows=tuple(normalized_rows),
        delimiter=delimiter,
        source_format=source_format,
        warnings=tuple(warnings),
    )
