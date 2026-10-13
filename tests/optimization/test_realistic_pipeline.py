from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from scripts.verify_synthetic_planning import build_synthetic_catalog, run_verification
from src.optimization import HighsSolver
from src.optimization.platform_cli import main as planner_cli

pytestmark = pytest.mark.skipif(not HighsSolver.is_available(), reason="highspy is unavailable")
MONDAY = date(2026, 11, 30)


def test_real_solver_full_json_pipeline_and_cross_month_persistence(tmp_path):
    directory = tmp_path / "data"
    build_synthetic_catalog(directory, MONDAY, 40)
    report = run_verification(directory, MONDAY)
    assert report["time_limit_seconds"] == 300
    assert report["candidate_count"] == 40
    assert report["residents"] == 8
    assert report["sessions"] == 10
    assert report["excluded_other_draft"] == 4
    assert report["scheduled"] >= 8
    assert report["written"]
    assert report["status"] in {"optimal", "feasible_not_proven_optimal"}


def test_real_solver_infeasibility_never_writes_a_plan(tmp_path):
    directory = tmp_path / "data"
    build_synthetic_catalog(directory, MONDAY, 40)
    patient_path = directory / "pazienti" / "SYN-P0000.json"
    patient = json.loads(patient_path.read_text())
    patient["data_inserimento"] = (MONDAY + timedelta(days=7)).strftime("%d/%m/%Y")
    patient_path.write_text(json.dumps(patient))
    report = run_verification(directory, MONDAY)
    assert report["status"] == "infeasible"
    assert report["scheduled"] == 0
    assert not report["written"]


def test_real_solver_tiny_time_limit_does_not_persist_without_a_solution(tmp_path):
    directory = tmp_path / "data"
    build_synthetic_catalog(directory, MONDAY, 120)
    report = run_verification(directory, MONDAY, 0.000001)
    assert report["status"] == "limit_reached_no_solution"
    assert report["scheduled"] == 0
    assert not report["written"]


def test_generator_refuses_to_replace_existing_data(tmp_path):
    directory = tmp_path / "data"
    build_synthetic_catalog(directory, MONDAY, 12)
    before = {path: path.read_bytes() for path in directory.rglob("*.json")}
    with pytest.raises(FileExistsError):
        build_synthetic_catalog(directory, MONDAY, 12)
    assert all(path.read_bytes() == payload for path, payload in before.items())


def test_cli_uses_explicit_catalog_and_keeps_dry_run_read_only(tmp_path, monkeypatch, capsys):
    directory = tmp_path / "external data"
    build_synthetic_catalog(directory, MONDAY, 12)
    before = {path: path.read_bytes() for path in directory.rglob("*.json")}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MMSD_DATA_DIR", str(tmp_path / "not-selected"))
    assert planner_cli(["--week", MONDAY.isoformat(), "--data-dir", str(directory)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["candidate_count"] == 12
    assert report["scheduled_count"] >= 8
    assert not report["written"]
    assert all(path.read_bytes() == payload for path, payload in before.items())
    assert not (tmp_path / "not-selected").exists()
