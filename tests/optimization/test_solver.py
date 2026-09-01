from __future__ import annotations

from datetime import date

import pytest
from pyomo.contrib.appsi.base import TerminationCondition

from src.optimization import (
    HighsSolver,
    ObjectiveWeights,
    Patient,
    PatientCategory,
    Resident,
    SchedulingInput,
    Session,
    SolveStatus,
    build_paper_model,
    build_platform_model,
)
from src.optimization.solver import _interrupt_if_requested, _status_without_solution

pytestmark = pytest.mark.skipif(not HighsSolver.is_available(), reason="highspy is unavailable")


def test_highs_finds_hand_checkable_optimum() -> None:
    data = SchedulingInput(
        patients=(
            Patient(
                "MANDATORY",
                PatientCategory.MANDATORY,
                60,
                "high",
                frozenset({"R2"}),
            ),
            Patient(
                "OPTION-A",
                PatientCategory.WAITING_LIST,
                60,
                "low",
                frozenset({"R1"}),
                waiting_time_days=9,
                max_wait_days=10,
            ),
            Patient(
                "OPTION-B",
                PatientCategory.WAITING_LIST,
                60,
                "high",
                frozenset({"R2"}),
                waiting_time_days=8,
                max_wait_days=10,
            ),
        ),
        residents=(
            Resident("R1", frozenset({"low"})),
            Resident("R2", frozenset({"high"})),
        ),
        sessions=(Session("OR-1", date(2026, 8, 10), 120),),
    )

    result = HighsSolver().solve(build_paper_model(data))

    assert result.status is SolveStatus.OPTIMAL
    assert {record.patient_id for record in result.schedule} == {"MANDATORY", "OPTION-A"}
    assert {record.resident_id for record in result.schedule} == {"R1", "R2"}
    assert result.objective is not None
    assert result.objective.treatment_efficiency == pytest.approx(0.9)
    assert result.objective.fairness_floor == 1
    assert result.objective.unassigned_count == 0
    assert result.objective.weighted_total == pytest.approx(10.0)


def test_highs_uses_unassigned_indicator_when_no_resident_is_compatible() -> None:
    data = SchedulingInput(
        patients=(
            Patient(
                "MANDATORY",
                PatientCategory.MANDATORY,
                60,
                "low",
                frozenset({"R1"}),
            ),
        ),
        residents=(Resident("R1", frozenset({"high"})),),
        sessions=(Session("OR-1", date(2026, 8, 10), 60),),
    )

    result = HighsSolver().solve(build_paper_model(data))

    assert result.status is SolveStatus.OPTIMAL
    assert result.schedule[0].resident_id is None
    assert result.objective is not None
    assert result.objective.unassigned_count == 1
    assert result.objective.weighted_total == pytest.approx(-1.0)


def test_highs_reports_infeasible_without_loading_variables() -> None:
    data = SchedulingInput(
        patients=tuple(
            Patient(
                f"REQUIRED-{index}",
                PatientCategory.MANDATORY,
                60,
                "low",
                frozenset({"R1"}),
            )
            for index in range(3)
        ),
        residents=(Resident("R1", frozenset({"low"})),),
        sessions=(
            Session("OR-1", date(2026, 8, 10), 100),
            Session("OR-1", date(2026, 8, 11), 100),
        ),
    )

    result = HighsSolver().solve(build_paper_model(data))

    assert result.status is SolveStatus.INFEASIBLE
    assert result.schedule == ()
    assert result.objective is None


def test_changeover_prevents_overfilling_a_session() -> None:
    patients = tuple(
        Patient(
            f"P{index}",
            PatientCategory.WAITING_LIST,
            60,
            "low",
            frozenset({"R1"}),
            waiting_time_days=5,
            max_wait_days=10,
        )
        for index in range(2)
    )
    common = {
        "patients": patients,
        "residents": (Resident("R1", frozenset({"low"})),),
        "sessions": (Session("OR-1", date(2026, 8, 10), 120),),
    }

    without_changeover = HighsSolver().solve(
        build_paper_model(SchedulingInput(**common, changeover_minutes=0))
    )
    with_changeover = HighsSolver().solve(
        build_platform_model(SchedulingInput(**common, changeover_minutes=11))
    )

    assert len(without_changeover.schedule) == 2
    assert len(with_changeover.schedule) == 1


def test_no_fairness_configuration_reports_the_actual_workload_floor() -> None:
    data = SchedulingInput(
        patients=(
            Patient(
                "MANDATORY",
                PatientCategory.MANDATORY,
                60,
                "high",
                frozenset({"R2"}),
            ),
            Patient(
                "OPTIONAL",
                PatientCategory.WAITING_LIST,
                60,
                "low",
                frozenset({"R1"}),
                waiting_time_days=5,
                max_wait_days=10,
            ),
        ),
        residents=(
            Resident("R1", frozenset({"low"})),
            Resident("R2", frozenset({"high"})),
        ),
        sessions=(Session("OR-1", date(2026, 8, 10), 120),),
        objective_weights=ObjectiveWeights(fairness=0),
    )

    result = HighsSolver().solve(build_platform_model(data))

    assert result.status is SolveStatus.OPTIMAL
    assert result.objective is not None
    assert result.objective.fairness_floor == 1
    assert result.objective.weighted_total == pytest.approx(5.0)


def test_pre_cancelled_solve_never_loads_a_solution() -> None:
    data = SchedulingInput(
        patients=(
            Patient(
                "MANDATORY",
                PatientCategory.MANDATORY,
                60,
                "low",
                frozenset({"R1"}),
            ),
        ),
        residents=(Resident("R1", frozenset({"low"})),),
        sessions=(Session("OR-1", date(2026, 8, 10), 60),),
    )

    result = HighsSolver().solve(
        build_paper_model(data),
        cancel_requested=lambda: True,
    )

    assert result.status is SolveStatus.INTERRUPTED
    assert result.schedule == ()
    assert result.objective is None
    assert result.termination_condition == "cancelled_before_solve"


def test_highs_callback_interrupts_only_after_cancellation() -> None:
    class CallbackEvent:
        interrupted = False

        def interrupt(self) -> None:
            self.interrupted = True

    callback_event = CallbackEvent()
    _interrupt_if_requested(callback_event, lambda: False)
    assert callback_event.interrupted is False

    _interrupt_if_requested(callback_event, lambda: True)
    assert callback_event.interrupted is True


@pytest.mark.parametrize(
    ("termination", "expected"),
    [
        (TerminationCondition.maxTimeLimit, SolveStatus.LIMIT_REACHED),
        (TerminationCondition.maxIterations, SolveStatus.LIMIT_REACHED),
        (TerminationCondition.objectiveLimit, SolveStatus.LIMIT_REACHED),
        (TerminationCondition.interrupted, SolveStatus.INTERRUPTED),
        (TerminationCondition.error, SolveStatus.ERROR),
    ],
)
def test_termination_without_incumbent_is_preserved(
    termination: TerminationCondition,
    expected: SolveStatus,
) -> None:
    assert _status_without_solution(termination) is expected
