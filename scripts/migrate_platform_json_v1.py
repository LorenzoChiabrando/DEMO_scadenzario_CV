#!/usr/bin/env python3
"""Migrate legacy demo JSON files to optimization schema v1.

The default mode is a dry run; ``--write`` replaces only the files that need changes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.planning_schema import (  # noqa: E402 - executable script path bootstrap
    OPTIMIZATION_KEY,
    SCHEMA_VERSION,
    default_patient_optimization,
    default_schedule_optimization,
)

JsonObject = dict[str, Any]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist the migration; without this flag only report the planned changes",
    )
    return parser


def _read_json(path: Path) -> JsonObject:
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json_atomic(path: Path, payload: JsonObject) -> None:
    # Keep the temporary file beside the destination so os.replace stays atomic.
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=4, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            # Flush buffered data to disk before replacing the original JSON.
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _ensure_supported_version(record: JsonObject, path: Path) -> None:
    # Existing configurations are modified only when their schema is exactly v1.
    configuration = record.get(OPTIMIZATION_KEY)
    if configuration is None:
        return
    if not isinstance(configuration, dict):
        raise ValueError(f"{path} has an invalid {OPTIMIZATION_KEY} object")
    if configuration.get("versione_schema") != SCHEMA_VERSION:
        raise ValueError(f"{path} has an unsupported optimization schema version")


def _remove_deprecated_resident_qualification(record: JsonObject, path: Path) -> bool:
    """Remove the old explicit h_jl input while preserving unrelated future fields."""

    _ensure_supported_version(record, path)
    configuration = record.get(OPTIMIZATION_KEY)
    if configuration is None:
        return False

    updated_configuration = dict(configuration)
    removed = "complessita_abilitate" in updated_configuration
    updated_configuration.pop("complessita_abilitate", None)
    if set(updated_configuration) == {"versione_schema"}:
        record.pop(OPTIMIZATION_KEY)
        return True
    if removed:
        record[OPTIMIZATION_KEY] = updated_configuration
    return removed


def migrate(project_root: Path, *, write: bool) -> dict[str, int]:
    """Migrate catalogs idempotently and return aggregate change counts."""

    root = project_root.resolve()
    # Only these three catalogues contain inputs used by the optimization mapper.
    resident_paths = sorted((root / "mock_data" / "libretti").glob("*.json"))
    patient_paths = sorted((root / "mock_data" / "pazienti").glob("*.json"))
    schedule_paths = sorted((root / "mock_data" / "scadenzario").glob("*.json"))

    residents = [(path, _read_json(path)) for path in resident_paths]
    # Legacy patients start with every resident currently active at Molinette.
    active_resident_ids = [
        record["id"]
        for _, record in residents
        if record.get("stato") == "Molinette" and isinstance(record.get("id"), str)
    ]

    changed = {"libretti": 0, "pazienti": 0, "scadenzari": 0}
    # Resident qualifications now come from the training-level policy.
    for path, record in residents:
        if _remove_deprecated_resident_qualification(record, path):
            changed["libretti"] += 1
            if write:
                _write_json_atomic(path, record)

    # Existing optimization blocks are preserved; defaults are added only when absent.
    for path in patient_paths:
        record = _read_json(path)
        _ensure_supported_version(record, path)
        if OPTIMIZATION_KEY not in record:
            record[OPTIMIZATION_KEY] = default_patient_optimization(
                record.get("urgenza", ""),
                active_resident_ids,
            )
            changed["pazienti"] += 1
            if write:
                _write_json_atomic(path, record)

    # Monthly schedules need the room and capacity metadata used to build sessions.
    for path in schedule_paths:
        record = _read_json(path)
        _ensure_supported_version(record, path)
        if OPTIMIZATION_KEY not in record:
            record[OPTIMIZATION_KEY] = default_schedule_optimization()
            changed["scadenzari"] += 1
            if write:
                _write_json_atomic(path, record)

    return changed


def main() -> int:
    args = _parser().parse_args()
    changed = migrate(args.project_root, write=args.write)
    mode = "written" if args.write else "dry-run"
    print(
        f"Migration {mode}: {changed['pazienti']} patient files, "
        f"{changed['libretti']} specialist files, "
        f"{changed['scadenzari']} schedule files"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
