"""I data manager non lasciano file a metà e non scambiano un file danneggiato per dati vuoti."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from src.models.data_manager import DataManager
from src.models.data_manager_libretto import DataManagerLibretto
from src.models.data_manager_pazienti import DataManagerPazienti
from src.models.data_manager_sale_operatorie import DataManagerSaleOperatorie
from src.models.json_files import CorruptedDataError

_TRUNCATED = '{"metadata": {"stato": "BOZ'


class _Unserializable:
    """Valore che ``json`` non sa salvare: fa fallire il salvataggio a metà file."""


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    return path


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    resident = {"id": "SP001", "nome": "Ada", "cognome": "Demo", "stato": "Molinette"}
    _write(tmp_path / "libretti" / "SP001.json", resident)
    patient = {"id": "PZ0001", "nome": "Paziente", "cognome": "Uno", "urgenza": "Media"}
    _write(tmp_path / "pazienti" / "PZ0001.json", patient)
    month = {"metadata": {"stato": "BOZZA"}, "turni": {"2026-09-15": {"Sala Op. I": "Demo A."}}}
    _write(tmp_path / "scadenzario" / "2026-09.json", month)
    return tmp_path


def _roster(data_dir: Path) -> DataManager:
    return DataManager(data_dir / "scadenzario", data_dir / "libretti")


def _libretto(data_dir: Path) -> DataManagerLibretto:
    return DataManagerLibretto(data_dir / "libretti")


def _patients(data_dir: Path) -> DataManagerPazienti:
    return DataManagerPazienti(data_dir / "pazienti", data_dir / "libretti")


def _resident_form(name: object) -> dict[str, object]:
    return {
        "matricola": "M1",
        "nome": name,
        "cognome": "Demo",
        "livello": "Junior",
        "stato": "Molinette",
    }


_BROKEN_SAVES: dict[str, tuple[str, Callable[[Path], object]]] = {
    "scadenzario: cella": (
        "scadenzario/2026-09.json",
        lambda d: _roster(d).set_valore_cella("2026-09-15", "Reparto I", _Unserializable()),
    ),
    "libretto: anagrafica": (
        "libretti/SP001.json",
        lambda d: _libretto(d).aggiorna_specializzando("SP001", _resident_form(_Unserializable())),
    ),
    "libretto: attività della settimana": (
        "libretti/SP001.json",
        lambda d: _libretto(d).registra_attivita_settimana(
            {"Demo A.": [{"data": "2026-09-15", "slot": "S1", "extra": _Unserializable()}]}
        ),
    ),
    "libretto: attività extra": (
        "libretti/SP001.json",
        lambda d: _libretto(d).salva_attivita_extra(
            "SP001",
            {"data": "2026-09-15", "sede": "Altra", "attivita": "X", "extra": _Unserializable()},
        ),
    ),
    "libretto: note del giorno": (
        "libretti/SP001.json",
        lambda d: _libretto(d).salva_meta_giorno(
            "SP001", "2026-09-15", {"extra": _Unserializable()}
        ),
    ),
    "pazienti: scheda": (
        "pazienti/PZ0001.json",
        lambda d: _patients(d).aggiorna_paziente(
            "PZ0001", {"nome": _Unserializable(), "cognome": "Uno", "urgenza": "Media"}
        ),
    ),
    "pazienti: stato": (
        "pazienti/PZ0001.json",
        lambda d: _patients(d).aggiorna_stato_paziente("PZ0001", _Unserializable()),
    ),
}


@pytest.mark.parametrize("case", list(_BROKEN_SAVES), ids=list(_BROKEN_SAVES))
def test_a_save_failing_midway_leaves_the_previous_file_intact(
    data_dir: Path, case: str
) -> None:
    relative, save = _BROKEN_SAVES[case]
    before = (data_dir / relative).read_bytes()

    with pytest.raises(TypeError):
        save(data_dir)

    assert (data_dir / relative).read_bytes() == before
    assert sorted(path.name for path in (data_dir / relative).parent.iterdir()) == [
        Path(relative).name
    ]


def test_after_a_failed_save_the_roster_shows_what_is_on_disk(data_dir: Path) -> None:
    roster = _roster(data_dir)

    with pytest.raises(TypeError):
        roster.set_valore_cella("2026-09-15", "Sala Op. I", _Unserializable())

    assert roster.get_valore_cella("2026-09-15", "Sala Op. I") == "Demo A."


def test_a_corrupted_roster_month_is_never_read_as_empty_or_overwritten(data_dir: Path) -> None:
    month = data_dir / "scadenzario" / "2026-09.json"
    month.write_text(_TRUNCATED, encoding="utf-8")
    roster = _roster(data_dir)

    with pytest.raises(CorruptedDataError, match="scadenzario/2026-09.json"):
        roster.get_stato_mese(2026, 9)
    with pytest.raises(CorruptedDataError):
        roster.set_valore_cella("2026-09-16", "Reparto I", "Demo A.")

    assert month.read_text(encoding="utf-8") == _TRUNCATED


def test_a_corrupted_operating_room_month_raises_a_clear_error(data_dir: Path) -> None:
    month = data_dir / "sale_operatorie" / "2026-09.json"
    month.parent.mkdir()
    month.write_text(_TRUNCATED, encoding="utf-8")
    rooms = DataManagerSaleOperatorie(
        data_dir / "sale_operatorie", dir_pazienti=data_dir / "pazienti"
    )

    with pytest.raises(CorruptedDataError, match="sale_operatorie/2026-09.json"):
        rooms.load_mese(2026, 9)


@pytest.mark.parametrize(
    ("relative", "read_all"),
    [
        ("libretti/SP002.json", lambda d: _libretto(d).get_tutti_specializzandi()),
        ("libretti/SP002.json", lambda d: _roster(d).specializzandi),
        ("pazienti/PZ0002.json", lambda d: _patients(d).get_tutti_pazienti()),
    ],
    ids=["libretto", "anagrafica scadenzario", "pazienti"],
)
def test_a_corrupted_record_is_skipped_and_logged_by_file_name(
    data_dir: Path,
    caplog: pytest.LogCaptureFixture,
    relative: str,
    read_all: Callable[[Path], list[dict[str, object]]],
) -> None:
    (data_dir / relative).write_text(_TRUNCATED, encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        records = read_all(data_dir)

    assert [record["id"] for record in records] == [Path(relative).stem.replace("2", "1")]
    assert Path(relative).name in caplog.text
    assert str(data_dir) not in caplog.text


@pytest.mark.parametrize(
    ("relative", "read_one"),
    [
        ("libretti/SP001.json", lambda d: _libretto(d).get_specializzando_by_id("SP001")),
        ("pazienti/PZ0001.json", lambda d: _patients(d).get_paziente_by_id("PZ0001")),
        (
            "libretti/SP001.json",
            lambda d: _libretto(d).salva_meta_giorno("SP001", "2026-09-15", {"nota": "x"}),
        ),
    ],
    ids=["libretto", "paziente", "modifica libretto"],
)
def test_opening_a_corrupted_record_raises_a_clear_error(
    data_dir: Path, relative: str, read_one: Callable[[Path], object]
) -> None:
    (data_dir / relative).write_text(_TRUNCATED, encoding="utf-8")

    with pytest.raises(CorruptedDataError, match=Path(relative).name):
        read_one(data_dir)

    assert (data_dir / relative).read_text(encoding="utf-8") == _TRUNCATED
