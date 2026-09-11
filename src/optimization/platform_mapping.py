from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from types import MappingProxyType
from typing import Any

from src.planning_schema import (
    DEFAULT_COMPLEXITIES_BY_TRAINING_LEVEL,
    OPTIMIZATION_KEY,
    PAPER_CATEGORIES,
    SCHEMA_VERSION,
)

from .domain import Patient, PatientCategory, Resident, SchedulingInput, Session
from .exceptions import PlatformDataError
from .results import SolveResult

JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class PlatformPlanningPolicy:
    """Platform settings used to build the paper model."""

    room_ids: tuple[str, ...] = ("OR-1", "OR-2")
    session_start_minute: int = 8 * 60
    changeover_minutes: int = 11
    max_operations_per_session: int = 12
    qualified_complexities_by_training_level: Mapping[str, frozenset[str]] = field(
        default_factory=lambda: {
            training_level: frozenset(complexities)
            for training_level, complexities in DEFAULT_COMPLEXITIES_BY_TRAINING_LEVEL.items()
        }
    )

    def __post_init__(self) -> None:
        room_ids = tuple(self.room_ids)
        if len(room_ids) != 2 or len(set(room_ids)) != 2:
            raise ValueError("the platform requires exactly two distinct operating rooms")
        if any(not isinstance(room_id, str) or not room_id.strip() for room_id in room_ids):
            raise ValueError("room identifiers must be non-blank strings")
        if not 0 <= self.session_start_minute < 24 * 60:
            raise ValueError("session_start_minute must fall within a day")
        if self.changeover_minutes < 0:
            raise ValueError("changeover_minutes cannot be negative")
        if self.max_operations_per_session <= 0:
            raise ValueError("max_operations_per_session must be positive")
        if not isinstance(self.qualified_complexities_by_training_level, Mapping):
            raise ValueError("training-level qualifications must be a mapping")
        normalized_qualifications: dict[str, frozenset[str]] = {}
        for training_level, complexities in self.qualified_complexities_by_training_level.items():
            if not isinstance(training_level, str) or not training_level.strip():
                raise ValueError("training levels must be non-blank strings")
            if isinstance(complexities, str):
                raise ValueError(
                    f"qualifications for training level {training_level!r} must be a collection"
                )
            try:
                normalized_complexities = frozenset(complexities)
            except TypeError as error:
                raise ValueError(
                    f"qualifications for training level {training_level!r} must be a collection"
                ) from error
            if not normalized_complexities or any(
                not isinstance(complexity, str) or not complexity.strip()
                for complexity in normalized_complexities
            ):
                raise ValueError(
                    f"qualifications for training level {training_level!r} are invalid"
                )
            normalized_qualifications[training_level] = normalized_complexities
        if not normalized_qualifications:
            raise ValueError("at least one training-level qualification is required")
        object.__setattr__(self, "room_ids", room_ids)
        object.__setattr__(
            self,
            "qualified_complexities_by_training_level",
            MappingProxyType(normalized_qualifications),
        )


@dataclass(frozen=True, slots=True)
class RosterAssignment:
    """Resident assigned to one operating room."""

    room_id: str
    role: str
    resident_id: str
    display_name: str
    capacity_minutes: int


@dataclass(frozen=True, slots=True)
class PlatformPlanningContext:
    """Validated data needed to map a result back to JSON."""

    monday: date
    scheduling_input: SchedulingInput
    patient_records: Mapping[str, Mapping[str, Any]]
    roster_by_day: Mapping[date, tuple[RosterAssignment, ...]]
    excluded_other_draft_count: int = 0

    def __post_init__(self) -> None:
        patient_records = {
            patient_id: MappingProxyType(deepcopy(dict(record)))
            for patient_id, record in self.patient_records.items()
        }
        roster_by_day = {day: tuple(assignments) for day, assignments in self.roster_by_day.items()}
        object.__setattr__(self, "patient_records", MappingProxyType(patient_records))
        object.__setattr__(self, "roster_by_day", MappingProxyType(roster_by_day))


@dataclass(frozen=True, slots=True)
class PlatformDayPlan:
    """Operations and room roster for one date."""

    day: date
    operations: tuple[JsonObject, ...]
    roster: tuple[RosterAssignment, ...]


@dataclass(frozen=True, slots=True)
class PlatformWeekPlan:
    """Monday-Friday plan ready for persistence."""

    monday: date
    days: tuple[PlatformDayPlan, ...]


def build_platform_context(
    *,
    monday: date,
    patient_records: Sequence[Mapping[str, Any]],
    resident_records: Sequence[Mapping[str, Any]],
    roster_by_day: Mapping[date, Sequence[RosterAssignment]],
    other_draft_patient_ids: frozenset[str] = frozenset(),
    policy: PlatformPlanningPolicy | None = None,
) -> PlatformPlanningContext:
    """Map one platform week to ``SchedulingInput``."""
    active_policy = policy or PlatformPlanningPolicy()
    if monday.weekday() != 0:
        raise PlatformDataError("the planning horizon must start on a Monday")

    expected_days = tuple(monday + timedelta(days=offset) for offset in range(5))
    if set(roster_by_day) != set(expected_days):
        raise PlatformDataError("the OR roster must contain exactly Monday through Friday")

    for day in expected_days:
        assignments = tuple(roster_by_day[day])
        assignment_by_room = {assignment.room_id: assignment for assignment in assignments}
        if len(assignment_by_room) != len(assignments):
            raise PlatformDataError(f"the OR roster has duplicate rooms on {day.isoformat()}")
        if set(assignment_by_room) != set(active_policy.room_ids):
            raise PlatformDataError(
                f"the OR roster must contain {list(active_policy.room_ids)} on {day.isoformat()}"
            )
        resident_ids_for_day = [assignment.resident_id for assignment in assignments]
        if len(set(resident_ids_for_day)) != len(resident_ids_for_day):
            raise PlatformDataError(
                f"the same resident cannot cover both operating rooms on {day.isoformat()}"
            )
        if any(assignment.capacity_minutes <= 0 for assignment in assignments):
            raise PlatformDataError(
                f"operating-room capacity must be positive on {day.isoformat()}"
            )

    resident_record_by_id = _index_records(resident_records, "id", "resident")
    weekly_resident_ids = tuple(
        dict.fromkeys(
            assignment.resident_id for day in expected_days for assignment in roster_by_day[day]
        )
    )
    if not weekly_resident_ids:
        raise PlatformDataError("the weekly OR roster contains no residents")

    residents: list[Resident] = []
    for resident_id in weekly_resident_ids:
        record = resident_record_by_id.get(resident_id)
        if record is None:
            raise PlatformDataError(
                f"resident {resident_id!r} is missing from the platform catalog"
            )
        if record.get("stato") != "Molinette":
            raise PlatformDataError(f"resident {resident_id!r} is not active at Molinette")
        training_level = record.get("livello")
        if not isinstance(training_level, str) or not training_level.strip():
            raise PlatformDataError(f"resident {resident_id!r} has no valid training level")
        qualified_levels = active_policy.qualified_complexities_by_training_level.get(
            training_level
        )
        if qualified_levels is None:
            raise PlatformDataError(
                f"resident {resident_id!r} has unsupported training level {training_level!r}"
            )
        residents.append(Resident(resident_id, qualified_levels))

    patient_record_by_id = _index_records(patient_records, "id", "patient")
    candidates: list[Patient] = []
    mapped_records: dict[str, Mapping[str, Any]] = {}
    excluded_count = 0
    supported_complexities = {
        value
        for values in active_policy.qualified_complexities_by_training_level.values()
        for value in values
    }
    for patient_id in sorted(patient_record_by_id):
        record = patient_record_by_id[patient_id]
        if record.get("stato") != "In Attesa":
            continue
        if patient_id in other_draft_patient_ids:
            excluded_count += 1
            continue

        configuration = _optimization_configuration(record, "patient", patient_id)
        category_label = configuration.get("categoria_paper")
        if category_label not in PAPER_CATEGORIES:
            raise PlatformDataError(f"patient {patient_id!r} has an invalid paper category")
        category = {
            "I'": PatientCategory.WAITING_LIST,
            "I''": PatientCategory.MANDATORY,
            "I'''": PatientCategory.RESCHEDULED,
        }[category_label]

        qualified_ids_value = configuration.get("specializzandi_abilitati")
        if not isinstance(qualified_ids_value, list) or any(
            not isinstance(resident_id, str) or not resident_id.strip()
            for resident_id in qualified_ids_value
        ):
            raise PlatformDataError(
                f"patient {patient_id!r} has invalid resident qualifications"
            )
        unknown_qualified_ids = set(qualified_ids_value) - set(resident_record_by_id)
        if unknown_qualified_ids:
            raise PlatformDataError(
                f"patient {patient_id!r} references unknown resident identifiers"
            )

        duration = record.get("durata_intervento")
        if not isinstance(duration, int) or isinstance(duration, bool) or duration <= 0:
            raise PlatformDataError(f"patient {patient_id!r} has an invalid duration")
        complexity = record.get("complessita")
        if not isinstance(complexity, str) or not complexity.strip():
            raise PlatformDataError(f"patient {patient_id!r} has no procedure complexity")
        if complexity not in supported_complexities:
            raise PlatformDataError(
                f"patient {patient_id!r} requires a supported procedure complexity; "
                "completare il campo Complessità nella scheda paziente"
            )
        waiting_time_days = None
        max_wait_days = None
        if category is PatientCategory.WAITING_LIST:
            max_wait_days = configuration.get("attesa_massima_giorni")
            if (
                not isinstance(max_wait_days, int)
                or isinstance(max_wait_days, bool)
                or max_wait_days <= 0
            ):
                raise PlatformDataError(
                    f"patient {patient_id!r} has an invalid maximum waiting time; "
                    "completare Urgenza o attesa_massima_giorni nella scheda paziente"
                )
            inserted = _parse_platform_date(record.get("data_inserimento"), patient_id)
            waiting_time_days = (monday - inserted).days
            if waiting_time_days < 0:
                raise PlatformDataError(
                    f"patient {patient_id!r} was inserted after the planning week began"
                )

        candidates.append(
            Patient(
                patient_id=patient_id,
                category=category,
                duration_minutes=duration,
                procedure_level=complexity,
                qualified_resident_ids=frozenset(qualified_ids_value) & set(weekly_resident_ids),
                waiting_time_days=waiting_time_days,
                max_wait_days=max_wait_days,
            )
        )
        mapped_records[patient_id] = record

    if not candidates:
        raise PlatformDataError("no waiting-list patients are available for this week")

    sessions = tuple(
        Session(
            room_id=assignment.room_id,
            day=day,
            capacity_minutes=assignment.capacity_minutes,
            available_resident_ids=frozenset({assignment.resident_id}),
        )
        for day in expected_days
        for room_id in active_policy.room_ids
        for assignment in roster_by_day[day]
        if assignment.room_id == room_id
    )
    scheduling_input = SchedulingInput(
        patients=tuple(candidates),
        residents=tuple(residents),
        sessions=sessions,
        changeover_minutes=active_policy.changeover_minutes,
    )
    return PlatformPlanningContext(
        monday=monday,
        scheduling_input=scheduling_input,
        patient_records=mapped_records,
        roster_by_day={day: tuple(roster_by_day[day]) for day in expected_days},
        excluded_other_draft_count=excluded_count,
    )


def map_result_to_platform_plan(
    context: PlatformPlanningContext,
    result: SolveResult,
    policy: PlatformPlanningPolicy | None = None,
) -> PlatformWeekPlan:
    """Convert a feasible result to ordered platform records."""
    active_policy = policy or PlatformPlanningPolicy()
    if not result.has_solution or result.objective is None:
        raise PlatformDataError("only a validated feasible solver result can be persisted")

    patient_by_id = {patient.patient_id: patient for patient in context.scheduling_input.patients}
    expected_days = tuple(context.monday + timedelta(days=offset) for offset in range(5))
    session_by_key = {
        (session.day, session.room_id): session for session in context.scheduling_input.sessions
    }
    records_by_session: dict[tuple[date, str], list[Any]] = {
        key: [] for key in session_by_key
    }
    seen_patient_ids: set[str] = set()
    for record in result.schedule:
        if record.patient_id in seen_patient_ids:
            raise PlatformDataError(f"patient {record.patient_id!r} appears more than once")
        if record.patient_id not in patient_by_id:
            raise PlatformDataError(f"solver returned unknown patient {record.patient_id!r}")
        session_key = (record.day, record.room_id)
        if session_key not in records_by_session:
            raise PlatformDataError("solver returned a session outside the target platform week")
        seen_patient_ids.add(record.patient_id)
        records_by_session[session_key].append(record)

    day_plans: list[PlatformDayPlan] = []
    for day in expected_days:
        roster = context.roster_by_day[day]
        operations: list[JsonObject] = []
        roster_by_room = {assignment.room_id: assignment for assignment in roster}
        for room_id in active_policy.room_ids:
            session = session_by_key[day, room_id]
            assignment_for_room = roster_by_room[room_id]
            sorted_records = sorted(
                records_by_session[day, room_id],
                key=lambda record: (-patient_by_id[record.patient_id].urgency, record.patient_id),
            )
            if len(sorted_records) > active_policy.max_operations_per_session:
                raise PlatformDataError(
                    f"session {(room_id, day.isoformat())!r} exceeds the operation-row limit"
                )

            current_minute = active_policy.session_start_minute
            for index, scheduled in enumerate(sorted_records):
                patient = patient_by_id[scheduled.patient_id]
                source_record = context.patient_records[scheduled.patient_id]
                assignment = None
                if scheduled.resident_id is not None:
                    if scheduled.resident_id != assignment_for_room.resident_id:
                        raise PlatformDataError(
                            f"resident {scheduled.resident_id!r} is outside room {room_id!r} "
                            f"on {day.isoformat()}"
                        )
                    assignment = assignment_for_room

                end_minute = current_minute + patient.duration_minutes
                operations.append(
                    _build_operation_record(
                        source_record=source_record,
                        patient=patient,
                        room_id=scheduled.room_id,
                        assignment=assignment,
                        start_minute=current_minute,
                        end_minute=end_minute,
                    )
                )
                current_minute = end_minute
                if index < len(sorted_records) - 1:
                    current_minute += active_policy.changeover_minutes

            session_end = active_policy.session_start_minute + session.capacity_minutes
            if current_minute > session_end:
                raise PlatformDataError(
                    f"mapped operations exceed capacity in room {room_id!r} "
                    f"on {day.isoformat()}"
                )

        operations.sort(
            key=lambda operation: (
                operation["ora_inizio"],
                operation["sala_operatoria"],
                operation["id_paziente"],
            )
        )
        day_plans.append(
            PlatformDayPlan(day=day, operations=tuple(operations), roster=tuple(roster))
        )

    return PlatformWeekPlan(
        monday=context.monday,
        days=tuple(day_plans),
    )


def _build_operation_record(
    *,
    source_record: Mapping[str, Any],
    patient: Patient,
    room_id: str,
    assignment: RosterAssignment | None,
    start_minute: int,
    end_minute: int,
) -> JsonObject:
    interventions = deepcopy(source_record.get("interventi") or [])
    if not interventions:
        interventions = [
            {
                "codice": source_record.get("codice_intervento", ""),
                "descrizione": source_record.get("descrizione_intervento", ""),
                "durata": patient.duration_minutes,
            }
        ]
    first_intervention = interventions[0]
    return {
        "nome_paziente": (
            f"{source_record.get('cognome', '')} {source_record.get('nome', '')}"
        ).strip(),
        "id_paziente": patient.patient_id,
        "diagnosi": source_record.get("diagnosi", ""),
        "codice_diagnosi": source_record.get("codice_diagnosi", ""),
        "descrizione_diagnosi": source_record.get(
            "descrizione_diagnosi", source_record.get("diagnosi", "")
        ),
        "intervento": first_intervention.get("descrizione", ""),
        "codice_intervento": first_intervention.get("codice", ""),
        "interventi": interventions,
        "chirurgo": "",
        "complessita": source_record.get("complessita", ""),
        "tipo_chirurgia": source_record.get("tipo_chirurgia", ""),
        "durata": patient.duration_minutes,
        "ora_inizio": _minute_to_time(start_minute),
        "ora_fine": _minute_to_time(end_minute),
        "sala_operatoria": room_id,
        "id_specializzando": assignment.resident_id if assignment else "",
        "specializzando": assignment.display_name if assignment else "",
        "ruolo_specializzando": assignment.role if assignment else "",
    }


def _index_records(
    records: Sequence[Mapping[str, Any]],
    key: str,
    label: str,
) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for record in records:
        identifier = record.get(key)
        if not isinstance(identifier, str) or not identifier.strip():
            raise PlatformDataError(f"{label} record has no stable identifier")
        if identifier in indexed:
            raise PlatformDataError(f"duplicate {label} identifier {identifier!r}")
        indexed[identifier] = record
    return indexed


def _optimization_configuration(
    record: Mapping[str, Any],
    label: str,
    identifier: str,
) -> Mapping[str, Any]:
    configuration = record.get(OPTIMIZATION_KEY)
    if not isinstance(configuration, Mapping):
        raise PlatformDataError(
            f"{label} {identifier!r} has no {OPTIMIZATION_KEY} configuration"
        )
    if configuration.get("versione_schema") != SCHEMA_VERSION:
        raise PlatformDataError(
            f"{label} {identifier!r} has an unsupported optimization schema version"
        )
    return configuration


def _parse_platform_date(value: object, patient_id: str) -> date:
    if not isinstance(value, str):
        raise PlatformDataError(f"patient {patient_id!r} has no insertion date")
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError as exc:
        raise PlatformDataError(f"patient {patient_id!r} has an invalid insertion date") from exc


def _minute_to_time(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"
