from __future__ import annotations

from datetime import date

import pytest

from src.optimization import (
    InputValidationError,
    Patient,
    PatientCategory,
    Resident,
    SchedulingInput,
    Session,
    build_paper_model,
)


def test_validation_reports_multiple_input_errors() -> None:
    data = SchedulingInput(
        patients=(
            Patient(
                patient_id="P1",
                category=PatientCategory.WAITING_LIST,
                duration_minutes=-1,
                procedure_level="low",
                qualified_resident_ids=frozenset({"UNKNOWN"}),
            ),
        ),
        residents=(Resident("R1", frozenset({"low"})),),
        sessions=(Session("OR-1", date(2026, 8, 10), 0),),
    )

    with pytest.raises(InputValidationError) as caught:
        build_paper_model(data)

    message = str(caught.value)
    assert "duration_minutes must be positive" in message
    assert "requires waiting_time_days and max_wait_days" in message
    assert "unknown residents" in message
    assert "capacity_minutes must be positive" in message


def test_validation_rejects_duplicate_identifiers() -> None:
    patient = Patient(
        patient_id="P1",
        category=PatientCategory.WAITING_LIST,
        duration_minutes=60,
        procedure_level="low",
        qualified_resident_ids=frozenset({"R1"}),
        waiting_time_days=1,
        max_wait_days=10,
    )
    data = SchedulingInput(
        patients=(patient, patient),
        residents=(Resident("R1", frozenset({"low"})),),
        sessions=(Session("OR-1", date(2026, 8, 10), 120),),
    )

    with pytest.raises(InputValidationError, match="duplicate patient identifiers"):
        build_paper_model(data)


def test_validation_converts_wrong_field_types_to_domain_errors() -> None:
    data = SchedulingInput(
        patients=(
            Patient(
                patient_id=7,  # type: ignore[arg-type]
                category="waiting_list",  # type: ignore[arg-type]
                duration_minutes=60.5,  # type: ignore[arg-type]
                procedure_level=3,  # type: ignore[arg-type]
                qualified_resident_ids=frozenset({99}),  # type: ignore[arg-type]
                waiting_time_days=1.5,  # type: ignore[arg-type]
                max_wait_days="10",  # type: ignore[arg-type]
            ),
        ),
        residents=(
            Resident(
                resident_id=4,  # type: ignore[arg-type]
                qualified_levels=frozenset({1}),  # type: ignore[arg-type]
            ),
        ),
        sessions=(
            Session(
                room_id=5,  # type: ignore[arg-type]
                day="2026-08-10",  # type: ignore[arg-type]
                capacity_minutes=60.5,  # type: ignore[arg-type]
            ),
        ),
        changeover_minutes=1.5,  # type: ignore[arg-type]
    )

    with pytest.raises(InputValidationError) as caught:
        build_paper_model(data)

    message = str(caught.value)
    assert "patient_id must be a string" in message
    assert "duration_minutes must be an integer" in message
    assert "day must be datetime.date" in message
    assert "capacity_minutes must be an integer" in message
    assert "changeover_minutes must be an integer" in message


def test_validation_rejects_an_individually_impossible_required_patient() -> None:
    data = SchedulingInput(
        patients=(
            Patient(
                "TOO-LONG",
                PatientCategory.MANDATORY,
                121,
                "low",
                frozenset({"R1"}),
            ),
        ),
        residents=(Resident("R1", frozenset({"low"})),),
        sessions=(Session("OR-1", date(2026, 8, 10), 120),),
    )

    with pytest.raises(InputValidationError, match="longest session has 120"):
        build_paper_model(data)


def test_validation_rejects_unknown_available_resident() -> None:
    data = SchedulingInput(
        patients=(
            Patient(
                "P1",
                PatientCategory.WAITING_LIST,
                60,
                "low",
                frozenset({"R1"}),
                waiting_time_days=1,
                max_wait_days=10,
            ),
        ),
        residents=(Resident("R1", frozenset({"low"})),),
        sessions=(
            Session(
                "OR-1",
                date(2026, 8, 10),
                120,
                available_resident_ids=frozenset({"UNKNOWN"}),
            ),
        ),
    )

    with pytest.raises(InputValidationError, match="unknown available residents"):
        build_paper_model(data)
