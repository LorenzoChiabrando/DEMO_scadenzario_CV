from __future__ import annotations

import json
from pathlib import Path

from scripts.migrate_platform_json_v1 import migrate
from src.planning_schema import (
    DEFAULT_COMPLEXITIES_BY_TRAINING_LEVEL,
    OPTIMIZATION_KEY,
    default_patient_optimization,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_migration_removes_derived_resident_qualifications_idempotently(
    tmp_path: Path,
) -> None:
    resident_directory = tmp_path / "mock_data" / "libretti"
    first_path = resident_directory / "R1.json"
    second_path = resident_directory / "R2.json"
    _write_json(
        first_path,
        {
            "id": "R1",
            "livello": "Junior",
            OPTIMIZATION_KEY: {
                "versione_schema": 1,
                "complessita_abilitate": ["Bassa", "Media", "Alta"],
            },
        },
    )
    _write_json(
        second_path,
        {
            "id": "R2",
            "livello": "Senior",
            OPTIMIZATION_KEY: {
                "versione_schema": 1,
                "complessita_abilitate": ["Alta"],
                "campo_futuro": True,
            },
        },
    )

    assert migrate(tmp_path, write=True)["libretti"] == 2

    first = json.loads(first_path.read_text(encoding="utf-8"))
    second = json.loads(second_path.read_text(encoding="utf-8"))
    assert OPTIMIZATION_KEY not in first
    assert second[OPTIMIZATION_KEY] == {
        "versione_schema": 1,
        "campo_futuro": True,
    }
    assert migrate(tmp_path, write=True)["libretti"] == 0


def test_intermediate_level_has_an_explicit_planning_policy() -> None:
    assert DEFAULT_COMPLEXITIES_BY_TRAINING_LEVEL["Intermediate"] == (
        "Media",
        "Alta",
    )


def test_new_patient_configuration_has_no_patient_resident_parameter() -> None:
    assert default_patient_optimization("Alta") == {
        "versione_schema": 1,
        "categoria_paper": "I'",
        "attesa_massima_giorni": 30,
    }


def test_migration_removes_s_only_on_explicit_write_and_preserves_other_fields(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mock_data" / "pazienti" / "P1.json"
    current = {
        **default_patient_optimization("Alta"),
        "attesa_massima_giorni": 42,
        "campo_futuro": True,
    }
    _write_json(path, {
        "id": "P1",
        OPTIMIZATION_KEY: {**current, "specializzandi_abilitati": ["R1"]},
    })
    before = path.read_bytes()

    assert migrate(tmp_path, write=False)["pazienti"] == 1
    assert path.read_bytes() == before
    assert migrate(tmp_path, write=True)["pazienti"] == 1
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "id": "P1",
        OPTIMIZATION_KEY: current,
    }
    assert migrate(tmp_path, write=True)["pazienti"] == 0
