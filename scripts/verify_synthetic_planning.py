"""Run the real JSON/Pyomo/HiGHS pipeline on an isolated synthetic workload."""

from __future__ import annotations

import argparse
import json
import math
import random
import tempfile
from collections import Counter
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter

import pyomo.core as pyo

from src.data_paths import PROJECT_ROOT
from src.optimization import HighsConfig, HighsSolver, build_platform_model
from src.optimization.domain import PatientCategory
from src.optimization.platform_io import load_platform_context, persist_platform_week_plan
from src.optimization.platform_mapping import map_result_to_platform_plan
from src.planning_schema import OPTIMIZATION_KEY, default_schedule_optimization


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def build_synthetic_catalog(directory: Path, monday: date, patient_count: int = 120) -> None:
    """Create complete JSON catalogs in a new directory; never replace existing data.

    Cases mix waiting-list, mandatory and rescheduled patients, three complexity
    levels, multiple procedures, historical operations and another week's draft.
    Durations are plausible workload assumptions, not clinical estimates.
    """
    if monday.weekday() != 0 or patient_count < 12:
        raise ValueError("Use a Monday and at least 12 candidate patients")
    directory.mkdir(parents=True, exist_ok=False)
    rng = random.Random(20261013)
    residents = []
    for index in range(8):
        resident = {
            "id": f"SYN-R{index:02}", "nome": "Test", "cognome": f"Resident{index:02}",
            "matricola": f"SYN-{index:02}", "livello": ("Junior", "Intermediate", "Senior")[
                index % 3
            ], "stato": "Molinette", "attivita": [], "attivita_extra": [], "meta_giorni": {},
        }
        residents.append(resident)
    roster_months: dict[str, dict] = {}
    plan_months: dict[str, dict] = {}
    for week_offset in (-1, 0, 1):
        week = monday + timedelta(days=7 * week_offset)
        for offset in range(5):
            day = week + timedelta(days=offset)
            key = day.strftime("%Y-%m")
            roster = roster_months.setdefault(key, {
                "metadata": {"stato": "CONVALIDATO"}, "turni": {},
                OPTIMIZATION_KEY: default_schedule_optimization(),
            })
            config = roster[OPTIMIZATION_KEY]["sale_operatorie"]
            config["OR-1"]["capacita_minuti"] = 600
            config["OR-2"]["capacita_minuti"] = 480
            roster["turni"][day.isoformat()] = {
                "Sala Op. I": f"Resident{(offset * 2) % 8:02} T.",
                "Sala Op. II": f"Resident{(offset * 2 + 1) % 8:02} T.",
            }
            plan = plan_months.setdefault(key, {
                "metadata": {"stato": "BOZZA", "settimane": {}}, "turni": {},
            })
            plan["turni"][day.isoformat()] = {"operazioni": []}
        canonical = plan_months[week.strftime("%Y-%m")]
        canonical["metadata"]["settimane"][week.isoformat()] = (
            "CONVALIDATO" if week_offset == -1 else "BOZZA"
        )

    for index in range(patient_count + 8):
        duration = 60 if index < 8 or index >= patient_count else rng.choice(
            (45, 60, 75, 90, 120, 150, 180, 240)
        )
        priority, wait_limit = rng.choice((("Alta", 30), ("Media", 60), ("Bassa", 180)))
        inserted = monday - timedelta(days=rng.randrange(1, 241))
        if index >= patient_count:
            inserted = monday - timedelta(days=30 + index % 31)
        if index == 2 or (8 <= index < patient_count and index % 11 == 0):
            inserted = monday + timedelta(days=2 if index == 2 else index % 9)
        category = "I''" if index < 4 else "I'''" if index < 8 else "I'"
        state = "In Attesa" if index < patient_count else (
            "Completato" if index < patient_count + 4 else "Pianificato"
        )
        parts = [duration - 15, 15] if index % 5 == 0 else [duration]
        procedures = [
            {"codice": f"SYN-PROC-{index:04}-{part}",
             "descrizione": f"Procedura sintetica {index:04}/{part}", "durata": minutes}
            for part, minutes in enumerate(parts)
        ]
        patient = {
            "id": f"SYN-P{index:04}", "nome": "Test", "cognome": f"Case{index:04}",
            "codice_diagnosi": f"SYN-D{index:04}",
            "descrizione_diagnosi": "Diagnosi sintetica di test",
            "diagnosi": f"SYN-D{index:04} Diagnosi sintetica di test",
            "interventi": procedures, "codice_intervento": procedures[0]["codice"],
            "descrizione_intervento": procedures[0]["descrizione"],
            "durata_intervento": duration, "tipo_chirurgia": (
                "Aperta" if index % 2 else "Endovascolare"
            ), "complessita": ("Bassa", "Media", "Alta")[index % 3],
            "urgenza": priority, "stato": state,
            "data_inserimento": inserted.strftime("%d/%m/%Y"),
            "note": "Dataset interamente sintetico; codici non clinici.",
            OPTIMIZATION_KEY: {
                "versione_schema": 1, "categoria_paper": category,
                "attesa_massima_giorni": wait_limit,
            },
        }
        _write_json(directory / "pazienti" / f"{patient['id']}.json", patient)
        if index >= patient_count:
            historical = state == "Completato"
            day = monday + timedelta(days=-7 if historical else 7)
            start = 480 + (index % 4) * 71
            end = start + duration
            operation = {
                "id_paziente": patient["id"], "nome_paziente": f"{patient['cognome']} Test",
                "sala_operatoria": "OR-1", "id_specializzando": residents[0]["id"],
                "specializzando": "Resident00 T.", "ruolo_specializzando": "OR I",
                "durata": duration, "ora_inizio": f"{start // 60:02}:{start % 60:02}",
                "ora_fine": f"{end // 60:02}:{end % 60:02}", "interventi": procedures,
                "diagnosi": patient["diagnosi"], "chirurgo": "Chirurgo sintetico",
            }
            plan_months[day.strftime("%Y-%m")]["turni"][day.isoformat()]["operazioni"].append(
                operation
            )
            if historical:
                residents[0]["attivita"].append({**operation, "data": day.isoformat()})
    for resident in residents:
        _write_json(directory / "libretti" / f"{resident['id']}.json", resident)
    for key, roster in roster_months.items():
        _write_json(directory / "scadenzario" / f"{key}.json", roster)
        _write_json(directory / "sale_operatorie" / f"{key}.json", plan_months[key])


def run_verification(directory: Path, monday: date, time_limit: float = 300.0) -> dict:
    """Solve with the production adapter and validate before writing synthetic data."""
    original = {path: path.read_bytes() for path in directory.rglob("*.json")}
    started = perf_counter()
    context = load_platform_context(PROJECT_ROOT, monday, data_directory=directory)
    data = context.scheduling_input
    built = build_platform_model(data, max_operations_per_session=12)
    result = HighsSolver(HighsConfig(time_limit_seconds=time_limit)).solve(built)
    report = {
        "data_directory": str(directory), "week": monday.isoformat(),
        "candidate_count": len(data.patients), "residents": len(data.residents),
        "sessions": len(data.sessions), "excluded_other_draft": context.excluded_other_draft_count,
        "categories": dict(Counter(patient.category.value for patient in data.patients)),
        "variables": sum(1 for _ in built.model.component_data_objects(pyo.Var)),
        "constraints": sum(1 for _ in built.model.component_data_objects(pyo.Constraint)),
        "time_limit_seconds": time_limit, "solver_seconds": result.elapsed_seconds,
        "solver": f"{result.solver_name} {result.solver_version}",
        "status": result.status.value, "termination": result.termination_condition,
        "scheduled": len(result.schedule), "gap": result.relative_gap,
        "bound": result.best_objective_bound, "written": False,
    }
    if not result.has_solution:
        assert not result.schedule and result.objective is None
        assert all(path.read_bytes() == before for path, before in original.items())
        report["total_seconds"] = perf_counter() - started
        return report

    assert result.objective is not None
    for variable in built.model.component_data_objects(pyo.Var):
        value = pyo.value(variable)
        assert variable.lb is None or value >= variable.lb - 1e-6
        assert variable.ub is None or value <= variable.ub + 1e-6
        if variable.is_integer():
            assert abs(value - round(value)) <= 1e-6
    for constraint in built.model.component_data_objects(pyo.Constraint, active=True):
        value = pyo.value(constraint.body)
        assert constraint.lower is None or value >= pyo.value(constraint.lower) - 1e-6
        assert constraint.upper is None or value <= pyo.value(constraint.upper) + 1e-6
    by_id = {patient.patient_id: patient for patient in data.patients}
    selected = {item.patient_id for item in result.schedule}
    assert len(selected) == len(result.schedule)
    required = {p.patient_id for p in data.patients
                if p.category is not PatientCategory.WAITING_LIST}
    assert required <= selected
    assert all(item.day >= by_id[item.patient_id].earliest_surgery_date for item in result.schedule)
    efficiency = sum(by_id[i].urgency for i in selected
                     if by_id[i].category is PatientCategory.WAITING_LIST)
    workload = Counter(item.resident_id for item in result.schedule
                       if by_id[item.patient_id].category is not PatientCategory.RESCHEDULED)
    fairness = min(workload[resident.resident_id] for resident in data.residents)
    unassigned = sum(item.resident_id is None for item in result.schedule)
    reconstructed = data.efficiency_scale * efficiency + fairness - unassigned
    assert math.isclose(reconstructed, result.objective.weighted_total, abs_tol=1e-6)
    assert math.isclose(efficiency, result.objective.treatment_efficiency, abs_tol=1e-6)
    assert fairness == result.objective.fairness_floor
    assert unassigned == result.objective.unassigned_count

    sessions = []
    for session in data.sessions:
        items = [item for item in result.schedule
                 if (item.room_id, item.day) == (session.room_id, session.day)]
        occupied = sum(by_id[item.patient_id].duration_minutes for item in items)
        occupied += max(0, len(items) - 1) * data.changeover_minutes
        assert occupied <= session.capacity_minutes and len(items) <= 12
        assert all(item.resident_id in session.assigned_resident_ids for item in items)
        sessions.append({"day": session.day.isoformat(), "room": session.room_id,
                         "count": len(items), "minutes": occupied,
                         "capacity": session.capacity_minutes})
    plan = map_result_to_platform_plan(context, result)
    for day in plan.days:
        for room in ("OR-1", "OR-2"):
            previous_end = None
            for operation in [op for op in day.operations if op["sala_operatoria"] == room]:
                start, end = (sum(int(x) * factor for x, factor in zip(
                    operation[key].split(":"), (60, 1), strict=True
                )) for key in ("ora_inizio", "ora_fine"))
                assert end - start == operation["durata"]
                assert start == (480 if previous_end is None else previous_end + 11)
                previous_end = end
    receipt = persist_platform_week_plan(
        PROJECT_ROOT, plan, overwrite=False, data_directory=directory,
    )
    for path in (directory / "pazienti").glob("*.json"):
        patient = json.loads(path.read_text(encoding="utf-8"))
        before = json.loads(original[path])
        assert patient == {**before, "stato": (
            "Pianificato" if patient["id"] in selected else before["stato"]
        )}
    for path, before in original.items():
        if path.parent.name in {"libretti", "scadenzario"}:
            assert path.read_bytes() == before
        elif path.parent.name == "sale_operatorie":
            after = json.loads(path.read_text(encoding="utf-8"))
            for day, payload in json.loads(before)["turni"].items():
                if not monday <= date.fromisoformat(day) < monday + timedelta(days=5):
                    assert after["turni"][day] == payload
    for day in plan.days:
        saved = json.loads((directory / "sale_operatorie" / f"{day.day:%Y-%m}.json").read_text())
        assert saved["turni"][day.day.isoformat()]["operazioni"] == list(day.operations)
    report.update(objective=asdict(result.objective), sessions_detail=sessions,
                  written=True, files_written=len(receipt.updated_paths),
                  total_seconds=perf_counter() - started)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    today = date.today()
    parser.add_argument("--week", type=date.fromisoformat,
                        default=today - timedelta(days=today.weekday()))
    parser.add_argument("--patients", type=int, default=120)
    parser.add_argument("--time-limit", type=float, default=300)
    args = parser.parse_args()
    directory = Path(tempfile.mkdtemp(prefix="mmsd-real-solver-")) / "data"
    build_synthetic_catalog(directory, args.week, args.patients)
    print(json.dumps(run_verification(directory, args.week, args.time_limit), indent=2))


if __name__ == "__main__":
    main()
