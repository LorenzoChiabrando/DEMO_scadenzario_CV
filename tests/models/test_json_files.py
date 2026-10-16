from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.models.json_files import CorruptedDataError, read_json_object, write_json_atomic


def test_read_returns_the_stored_object(tmp_path: Path) -> None:
    path = tmp_path / "2026-09.json"
    path.write_text('{"metadata": {"stato": "BOZZA"}}', encoding="utf-8")

    assert read_json_object(path) == {"metadata": {"stato": "BOZZA"}}


@pytest.mark.parametrize(
    "content",
    [
        b'{"metadata": {"stato": "BOZ',
        b"",
        b'["non", "un", "oggetto"]',
        b'{"nome": "\xff\xfe"}',
    ],
    ids=["troncato", "vuoto", "lista", "non-utf8"],
)
def test_unreadable_files_raise_an_italian_error_naming_only_the_file(
    tmp_path: Path, content: bytes
) -> None:
    path = tmp_path / "scadenzario" / "2026-09.json"
    path.parent.mkdir()
    path.write_bytes(content)

    with pytest.raises(CorruptedDataError) as raised:
        read_json_object(path)

    assert raised.value.path == path
    assert "scadenzario/2026-09.json" in str(raised.value)
    assert "danneggiato" in str(raised.value)
    assert str(tmp_path) not in str(raised.value)


def test_corrupted_data_is_a_value_error_for_existing_handlers(tmp_path: Path) -> None:
    path = tmp_path / "SP001.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(ValueError):
        read_json_object(path)


def test_missing_file_is_not_reported_as_corrupted(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_json_object(tmp_path / "assente.json")


def test_write_keeps_the_existing_json_format(tmp_path: Path) -> None:
    path = tmp_path / "SP001.json"
    payload = {"id": "SP001", "nome": "Àda", "attivita": [{"data": "2026-09-15"}]}

    write_json_atomic(path, payload)

    assert path.read_text(encoding="utf-8") == json.dumps(payload, indent=4)


def test_failed_write_leaves_the_previous_file_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "SP001.json"
    path.write_text('{"id": "SP001"}', encoding="utf-8")

    def fail(*_args: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", fail)

    with pytest.raises(OSError):
        write_json_atomic(path, {"id": "SP001", "nome": "Nuovo"})

    assert path.read_text(encoding="utf-8") == '{"id": "SP001"}'
    assert [entry.name for entry in tmp_path.iterdir()] == ["SP001.json"]
