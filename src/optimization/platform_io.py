from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.planning_schema import OPTIMIZATION_KEY, SCHEMA_VERSION

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from .exceptions import PlatformDataError, PlatformPersistenceError
from .platform_mapping import (
    PlatformPlanningContext,
    PlatformPlanningPolicy,
    PlatformWeekPlan,
    RosterAssignment,
    build_platform_context,
)

JsonObject = dict[str, Any]
_LEGACY_SLOT_KEYS = ("8.00-10.00", "10.00-12.00", "14.00-16.00", "16.00-18.00")


@dataclass(frozen=True, slots=True)
class PlatformWriteReceipt:
    """Updated files and backups created by a weekly write."""

    updated_paths: tuple[Path, ...]
    backup_paths: tuple[Path, ...]


def load_platform_context(
    project_root: str | Path,
    monday: date,
    policy: PlatformPlanningPolicy | None = None,
) -> PlatformPlanningContext:
    """Load and map the requested platform week."""
    root = Path(project_root).resolve()
    active_policy = policy or PlatformPlanningPolicy()
    if monday.weekday() != 0:
        raise PlatformDataError("the planning horizon must start on a Monday")
    expected_days = tuple(monday + timedelta(days=offset) for offset in range(5))
    scadenzario_by_month = _load_convalidated_scadenzario_months(root, expected_days)
    patient_records = _read_catalog(root / "mock_data" / "pazienti")
    resident_records = _read_catalog(root / "mock_data" / "libretti")
    resident_by_display_name = _build_resident_name_index(resident_records)

    roster_by_day: dict[date, tuple[RosterAssignment, ...]] = {}
    for day in expected_days:
        month_data = scadenzario_by_month[day.year, day.month]
        daily_data = month_data.get("turni", {}).get(day.isoformat(), {})
        assignments: list[RosterAssignment] = []
        room_configuration = _room_configuration_for_day(
            month_data,
            day,
            active_policy.room_ids,
        )
        for room_id in active_policy.room_ids:
            room = room_configuration[room_id]
            roster_field = room["riga_turno"]
            display_name = daily_data.get(roster_field)
            if not isinstance(display_name, str) or not display_name.strip():
                raise PlatformDataError(
                    f"the OR roster is incomplete for {day.isoformat()} ({roster_field})"
                )
            resident_id = resident_by_display_name.get(_normalize_display_name(display_name))
            if resident_id is None:
                raise PlatformDataError(
                    f"an OR roster entry cannot be resolved on {day.isoformat()}"
                )
            assignments.append(
                RosterAssignment(
                    room_id=room_id,
                    role=room["ruolo_specializzando"],
                    resident_id=resident_id,
                    display_name=display_name.strip(),
                    capacity_minutes=room["capacita_minuti"],
                )
            )
        roster_by_day[day] = tuple(assignments)

    other_draft_patient_ids = _collect_other_draft_patient_ids(
        root / "mock_data" / "sale_operatorie",
        excluded_monday=monday,
    )
    return build_platform_context(
        monday=monday,
        patient_records=patient_records,
        resident_records=resident_records,
        roster_by_day=roster_by_day,
        other_draft_patient_ids=frozenset(other_draft_patient_ids),
        policy=active_policy,
    )


def persist_platform_week_plan(
    project_root: str | Path,
    plan: PlatformWeekPlan,
    *,
    overwrite: bool,
    backup_directory: str | Path | None = None,
) -> PlatformWriteReceipt:
    """Replace one draft week atomically, preserving unrelated data."""
    root = Path(project_root).resolve()
    sale_directory = root / "mock_data" / "sale_operatorie"
    sale_directory.mkdir(parents=True, exist_ok=True)
    backup_root = (
        Path(backup_directory).resolve()
        if backup_directory is not None
        else Path(tempfile.gettempdir()) / "mmsd-platform-plan-backups" / uuid4().hex
    )

    expected_days = tuple(plan.monday + timedelta(days=offset) for offset in range(5))
    plan_by_day = {day_plan.day: day_plan for day_plan in plan.days}
    if set(plan_by_day) != set(expected_days):
        raise PlatformPersistenceError("the plan must contain exactly Monday through Friday")

    affected_months = tuple(sorted({(day.year, day.month) for day in expected_days}))
    paths = tuple(
        sale_directory / f"{year:04d}-{month:02d}.json" for year, month in affected_months
    )
    with _directory_lock(sale_directory):
        _load_convalidated_scadenzario_months(root, expected_days)
        originals = {path: path.read_bytes() if path.exists() else None for path in paths}
        month_data: dict[tuple[int, int], JsonObject] = {}
        for (year, month), path in zip(affected_months, paths, strict=True):
            if path.exists():
                month_data[year, month] = _read_json(path)
            else:
                month_data[year, month] = {"metadata": {"stato": "BOZZA"}, "turni": {}}

        convalidated_target_months = [
            f"{year:04d}-{month:02d}"
            for (year, month), data in month_data.items()
            if data.get("metadata", {}).get("stato", "BOZZA") == "CONVALIDATO"
        ]
        if convalidated_target_months:
            raise PlatformPersistenceError(
                "the target operating-room months are convalidated: "
                + ", ".join(convalidated_target_months)
            )

        canonical = month_data[plan.monday.year, plan.monday.month]
        metadata = canonical.setdefault("metadata", {})
        week_states = metadata.setdefault("settimane", {})
        week_key = plan.monday.isoformat()
        if week_states.get(week_key, "BOZZA") == "CONVALIDATO":
            raise PlatformPersistenceError("the target week is convalidated")

        has_existing_operations = any(
            month_data[day.year, day.month]
            .get("turni", {})
            .get(day.isoformat(), {})
            .get("operazioni", [])
            for day in expected_days
        )
        if has_existing_operations and not overwrite:
            raise PlatformPersistenceError(
                "the target draft already contains operations; explicit overwrite is required"
            )

        updated = deepcopy(month_data)
        for day in expected_days:
            day_plan = plan_by_day[day]
            data = updated[day.year, day.month]
            turni = data.setdefault("turni", {})
            daily = turni.setdefault(day.isoformat(), {})
            daily["specializzandi"] = {
                assignment.role: assignment.display_name for assignment in day_plan.roster
            }
            daily["operazioni"] = [deepcopy(operation) for operation in day_plan.operations]
            for legacy_key in _LEGACY_SLOT_KEYS:
                daily.pop(legacy_key, None)
        updated[plan.monday.year, plan.monday.month].setdefault("metadata", {}).setdefault(
            "settimane", {}
        )[week_key] = "BOZZA"

        backup_paths = _write_private_backups(originals, backup_root)
        temporary_paths: dict[Path, Path] = {}
        try:
            for (year, month), destination in zip(affected_months, paths, strict=True):
                temporary_paths[destination] = _write_json_temporary(
                    destination,
                    updated[year, month],
                )
            for destination in paths:
                os.replace(temporary_paths[destination], destination)
            _fsync_directory(sale_directory)
        except Exception as exc:
            _restore_originals(originals)
            raise PlatformPersistenceError(
                "the weekly plan commit failed and was rolled back"
            ) from exc
        finally:
            for temporary in temporary_paths.values():
                temporary.unlink(missing_ok=True)

    return PlatformWriteReceipt(updated_paths=paths, backup_paths=backup_paths)


def _read_catalog(directory: Path) -> tuple[JsonObject, ...]:
    if not directory.is_dir():
        raise PlatformDataError(f"required platform directory is missing: {directory}")
    return tuple(_read_json(path) for path in sorted(directory.glob("*.json")))


def _room_configuration_for_day(
    month_data: JsonObject,
    day: date,
    expected_room_ids: tuple[str, ...],
) -> dict[str, JsonObject]:
    configuration = month_data.get(OPTIMIZATION_KEY)
    if not isinstance(configuration, dict):
        raise PlatformDataError(
            f"the scadenzario has no {OPTIMIZATION_KEY} configuration for {day:%Y-%m}"
        )
    if configuration.get("versione_schema") != SCHEMA_VERSION:
        raise PlatformDataError(
            f"the scadenzario has an unsupported optimization schema for {day:%Y-%m}"
        )

    rooms = configuration.get("sale_operatorie")
    if not isinstance(rooms, dict) or set(rooms) != set(expected_room_ids):
        raise PlatformDataError(
            f"the scadenzario must define exactly {list(expected_room_ids)} for {day:%Y-%m}"
        )

    capacity_overrides = configuration.get("capacita_sessioni", {})
    if not isinstance(capacity_overrides, dict):
        raise PlatformDataError("capacita_sessioni must be a JSON object")
    daily_overrides = capacity_overrides.get(day.isoformat(), {})
    if not isinstance(daily_overrides, dict):
        raise PlatformDataError(
            f"session capacity overrides must be a JSON object for {day.isoformat()}"
        )
    unknown_override_rooms = set(daily_overrides) - set(expected_room_ids)
    if unknown_override_rooms:
        raise PlatformDataError(
            f"session capacity overrides reference unknown rooms on {day.isoformat()}"
        )

    resolved: dict[str, JsonObject] = {}
    roster_fields: set[str] = set()
    roles: set[str] = set()
    for room_id in expected_room_ids:
        room = rooms[room_id]
        if not isinstance(room, dict):
            raise PlatformDataError(f"room {room_id!r} configuration must be a JSON object")
        roster_field = room.get("riga_turno")
        role = room.get("ruolo_specializzando")
        capacity = daily_overrides.get(room_id, room.get("capacita_minuti"))
        if not isinstance(roster_field, str) or not roster_field.strip():
            raise PlatformDataError(f"room {room_id!r} has no roster field")
        if not isinstance(role, str) or not role.strip():
            raise PlatformDataError(f"room {room_id!r} has no specialist role")
        if (
            not isinstance(capacity, int)
            or isinstance(capacity, bool)
            or capacity <= 0
        ):
            raise PlatformDataError(
                f"room {room_id!r} has invalid capacity on {day.isoformat()}"
            )
        if roster_field in roster_fields or role in roles:
            raise PlatformDataError("operating rooms must use distinct roster fields and roles")
        roster_fields.add(roster_field)
        roles.add(role)
        resolved[room_id] = {
            "riga_turno": roster_field,
            "ruolo_specializzando": role,
            "capacita_minuti": capacity,
        }
    return resolved


def _load_convalidated_scadenzario_months(
    root: Path,
    expected_days: tuple[date, ...],
) -> dict[tuple[int, int], JsonObject]:
    month_keys = tuple(sorted({(day.year, day.month) for day in expected_days}))
    snapshots: dict[tuple[int, int], JsonObject] = {}
    unconvalidated: list[str] = []
    for year, month in month_keys:
        path = root / "mock_data" / "scadenzario" / f"{year:04d}-{month:02d}.json"
        data = _read_json(path)
        snapshots[year, month] = data
        metadata = data.get("metadata")
        state = metadata.get("stato") if isinstance(metadata, dict) else None
        if state != "CONVALIDATO":
            unconvalidated.append(f"{year:04d}-{month:02d}")
    if unconvalidated:
        raise PlatformDataError(
            "the scadenzario months must be convalidated before planning: "
            + ", ".join(unconvalidated)
        )
    return snapshots


def _read_json(path: Path) -> JsonObject:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlatformDataError(f"cannot read valid platform JSON from {path}") from exc
    if not isinstance(parsed, dict):
        raise PlatformDataError(f"platform JSON root must be an object: {path}")
    return parsed


def _build_resident_name_index(
    resident_records: tuple[JsonObject, ...],
) -> dict[str, str]:
    index: dict[str, str] = {}
    ambiguous: set[str] = set()
    for record in resident_records:
        resident_id = record.get("id")
        name = record.get("nome")
        surname = record.get("cognome")
        if not all(
            isinstance(value, str) and value.strip() for value in (resident_id, name, surname)
        ):
            raise PlatformDataError("a resident catalog record has incomplete identity fields")
        display_key = _normalize_display_name(f"{surname} {name[0]}.")
        if display_key in index:
            ambiguous.add(display_key)
        index[display_key] = resident_id
    if ambiguous:
        raise PlatformDataError("resident display names are not unique")
    return index


def _normalize_display_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _collect_other_draft_patient_ids(
    sale_directory: Path,
    *,
    excluded_monday: date,
) -> set[str]:
    month_data: dict[tuple[int, int], JsonObject] = {}
    for path in sorted(sale_directory.glob("????-??.json")):
        try:
            year, month = map(int, path.stem.split("-"))
        except ValueError:
            continue
        month_data[year, month] = _read_json(path)

    planned: set[str] = set()
    for data in month_data.values():
        for day_text, daily in data.get("turni", {}).items():
            try:
                day = date.fromisoformat(day_text)
            except ValueError:
                continue
            monday = day - timedelta(days=day.weekday())
            if monday == excluded_monday:
                continue
            canonical = month_data.get((monday.year, monday.month), {})
            state = (
                canonical.get("metadata", {}).get("settimane", {}).get(monday.isoformat(), "BOZZA")
            )
            if state == "CONVALIDATO":
                continue
            for operation in daily.get("operazioni", []):
                patient_id = operation.get("id_paziente")
                if isinstance(patient_id, str) and patient_id:
                    planned.add(patient_id)
    return planned


@contextmanager
def _directory_lock(directory: Path):
    if os.name == "nt":
        lock_path = directory / ".mmsd-planning.lock"
        with lock_path.open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        return

    descriptor = os.open(directory, os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _write_private_backups(
    originals: dict[Path, bytes | None],
    backup_root: Path,
) -> tuple[Path, ...]:
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(backup_root, 0o700)
    backups: list[Path] = []
    for source, payload in originals.items():
        if payload is None:
            continue
        destination = backup_root / source.name
        destination.write_bytes(payload)
        os.chmod(destination, 0o600)
        backups.append(destination)
    return tuple(backups)


def _write_json_temporary(destination: Path, payload: JsonObject) -> Path:
    serialized = json.dumps(payload, indent=4)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(serialized)
        stream.flush()
        os.fsync(stream.fileno())
    json.loads(temporary.read_text(encoding="utf-8"))
    return temporary


def _restore_originals(originals: dict[Path, bytes | None]) -> None:
    for destination, payload in originals.items():
        if payload is None:
            destination.unlink(missing_ok=True)
            continue
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.restore")
        try:
            with temporary.open("wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
