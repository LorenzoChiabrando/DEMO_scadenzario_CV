from __future__ import annotations

import math
from datetime import date
from numbers import Real

from .domain import ObjectiveWeights, PatientCategory, SchedulingInput
from .exceptions import InputValidationError


def validate_scheduling_input(data: SchedulingInput) -> None:
    """Validate input data before constructing Pyomo components."""

    errors: list[str] = []

    if not data.patients:
        errors.append("at least one patient is required")
    if not data.residents:
        errors.append("at least one resident is required for max-min fairness")
    if not data.sessions:
        errors.append("at least one operating-room session is required")

    patient_ids: list[str] = []
    resident_ids: list[str] = []
    session_keys: list[tuple[str, str]] = []

    for resident in data.residents:
        prefix = f"resident {resident.resident_id!r}"
        if not isinstance(resident.resident_id, str):
            errors.append(f"{prefix} resident_id must be a string")
        else:
            resident_ids.append(resident.resident_id)
            if not resident.resident_id.strip():
                errors.append("resident_id cannot be blank")

        invalid_levels = [
            level for level in resident.qualified_levels if not isinstance(level, str)
        ]
        if invalid_levels:
            errors.append(
                f"{prefix} qualified levels must be strings: {sorted(map(repr, invalid_levels))}"
            )
        if any(isinstance(level, str) and not level.strip() for level in resident.qualified_levels):
            errors.append(f"{prefix} contains a blank qualified level")

    known_residents = set(resident_ids)
    required_durations: list[tuple[str, int]] = []
    for patient in data.patients:
        prefix = f"patient {patient.patient_id!r}"
        if not isinstance(patient.patient_id, str):
            errors.append(f"{prefix} patient_id must be a string")
        else:
            patient_ids.append(patient.patient_id)
            if not patient.patient_id.strip():
                errors.append("patient_id cannot be blank")

        category_is_valid = isinstance(patient.category, PatientCategory)
        if not category_is_valid:
            errors.append(f"{prefix} has an invalid category: {patient.category!r}")

        duration_is_valid = _is_plain_int(patient.duration_minutes)
        if not duration_is_valid:
            errors.append(f"{prefix} duration_minutes must be an integer")
        elif patient.duration_minutes <= 0:
            errors.append(f"{prefix} duration_minutes must be positive")
        elif category_is_valid and patient.category in {
            PatientCategory.MANDATORY,
            PatientCategory.RESCHEDULED,
        }:
            required_durations.append((str(patient.patient_id), patient.duration_minutes))

        if not isinstance(patient.procedure_level, str):
            errors.append(f"{prefix} procedure_level must be a string")
        elif not patient.procedure_level.strip():
            errors.append(f"{prefix} procedure_level cannot be blank")

        waiting_values = (patient.waiting_time_days, patient.max_wait_days)
        if patient.category is PatientCategory.WAITING_LIST and None in waiting_values:
            errors.append(f"{prefix} requires waiting_time_days and max_wait_days")
        if (patient.waiting_time_days is None) != (patient.max_wait_days is None):
            errors.append(f"{prefix} must define both waiting fields or neither")
        _validate_optional_integer(
            errors,
            prefix,
            "waiting_time_days",
            patient.waiting_time_days,
            allow_zero=True,
        )
        _validate_optional_integer(
            errors,
            prefix,
            "max_wait_days",
            patient.max_wait_days,
            allow_zero=False,
        )

        invalid_qualified_ids = [
            resident_id
            for resident_id in patient.qualified_resident_ids
            if not isinstance(resident_id, str)
        ]
        if invalid_qualified_ids:
            errors.append(
                f"{prefix} qualified resident identifiers must be strings: "
                f"{sorted(map(repr, invalid_qualified_ids))}"
            )
        qualified_ids = {
            resident_id
            for resident_id in patient.qualified_resident_ids
            if isinstance(resident_id, str)
        }
        unknown = qualified_ids - known_residents
        if unknown:
            errors.append(f"{prefix} references unknown residents: {sorted(unknown)}")

    valid_capacities: list[int] = []
    for session in data.sessions:
        prefix = f"session ({session.room_id!r}, {session.day!r})"
        room_is_valid = isinstance(session.room_id, str)
        day_is_valid = isinstance(session.day, date)
        if not room_is_valid:
            errors.append(f"{prefix} room_id must be a string")
        elif not session.room_id.strip():
            errors.append("session room_id cannot be blank")
        if not day_is_valid:
            errors.append(f"{prefix} day must be datetime.date")
        if room_is_valid and day_is_valid:
            session_keys.append((session.room_id, session.day.isoformat()))

        if not _is_plain_int(session.capacity_minutes):
            errors.append(f"{prefix} capacity_minutes must be an integer")
        elif session.capacity_minutes <= 0:
            errors.append(f"{prefix} capacity_minutes must be positive")
        else:
            valid_capacities.append(session.capacity_minutes)

        if session.available_resident_ids is not None:
            invalid_available_ids = [
                resident_id
                for resident_id in session.available_resident_ids
                if not isinstance(resident_id, str)
            ]
            if invalid_available_ids:
                errors.append(
                    f"{prefix} available resident identifiers must be strings: "
                    f"{sorted(map(repr, invalid_available_ids))}"
                )
            available_ids = {
                resident_id
                for resident_id in session.available_resident_ids
                if isinstance(resident_id, str)
            }
            unknown_available = available_ids - known_residents
            if unknown_available:
                errors.append(
                    f"{prefix} references unknown available residents: {sorted(unknown_available)}"
                )

    _append_duplicate_errors(errors, "patient", patient_ids)
    _append_duplicate_errors(errors, "resident", resident_ids)
    _append_duplicate_errors(errors, "session", session_keys)

    weights = data.objective_weights
    if not isinstance(weights, ObjectiveWeights):
        errors.append("objective_weights must be an ObjectiveWeights instance")
    else:
        if weights.efficiency_scale is not None and not _is_finite_positive_number(
            weights.efficiency_scale
        ):
            errors.append("objective efficiency_scale must be finite and positive")
        if not _is_finite_non_negative_number(weights.fairness):
            errors.append("objective fairness weight must be finite and non-negative")
        if not _is_finite_positive_number(weights.unassigned_penalty):
            errors.append("objective unassigned_penalty must be finite and positive")

    changeover_is_valid = _is_plain_int(data.changeover_minutes)
    if not changeover_is_valid:
        errors.append("changeover_minutes must be an integer")
    elif data.changeover_minutes < 0:
        errors.append("changeover_minutes cannot be negative")

    if len(valid_capacities) == len(data.sessions) and valid_capacities:
        _validate_obvious_required_capacity(
            errors,
            required_durations,
            valid_capacities,
            data.changeover_minutes if changeover_is_valid else 0,
        )

    if errors:
        raise InputValidationError(errors)


def _validate_optional_integer(
    errors: list[str],
    prefix: str,
    field_name: str,
    value: object,
    *,
    allow_zero: bool,
) -> None:
    if value is None:
        return
    if not _is_plain_int(value):
        errors.append(f"{prefix} {field_name} must be an integer")
        return
    if value < 0 or (value == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        errors.append(f"{prefix} {field_name} must be {qualifier}")


def _validate_obvious_required_capacity(
    errors: list[str],
    required_durations: list[tuple[str, int]],
    capacities: list[int],
    changeover_minutes: int,
) -> None:
    max_capacity = max(capacities)
    for patient_id, duration in required_durations:
        if duration > max_capacity:
            errors.append(
                f"required patient {patient_id!r} needs {duration} minutes, but the longest "
                f"session has {max_capacity}"
            )

    minimum_changeovers = max(0, len(required_durations) - len(capacities))
    minimum_total_load = sum(duration for _, duration in required_durations)
    minimum_total_load += changeover_minutes * minimum_changeovers
    total_capacity = sum(capacities)
    if minimum_total_load > total_capacity:
        errors.append(
            f"required patients need at least {minimum_total_load} total minutes, but only "
            f"{total_capacity} are available"
        )


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_finite_positive_number(value: object) -> bool:
    return _is_finite_number(value) and float(value) > 0


def _is_finite_non_negative_number(value: object) -> bool:
    return _is_finite_number(value) and float(value) >= 0


def _is_finite_number(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(float(value))


def _append_duplicate_errors(errors: list[str], label: str, values: list[object]) -> None:
    seen: set[object] = set()
    duplicates: set[object] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        errors.append(f"duplicate {label} identifiers: {sorted(duplicates)!r}")
