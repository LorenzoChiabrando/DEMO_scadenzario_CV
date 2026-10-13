from __future__ import annotations

from pathlib import Path

import pytest

from src.data_paths import PROJECT_ROOT, resolve_data_directory
from src.optimization.platform_cli import _parser


def test_default_is_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("MMSD_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert resolve_data_directory() == PROJECT_ROOT / "mock_data"
    assert _parser().parse_args(["--week", "2026-10-12"]).project_root == PROJECT_ROOT


def test_explicit_path_wins_over_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("MMSD_DATA_DIR", str(tmp_path / "environment"))
    assert resolve_data_directory(tmp_path / "selected") == tmp_path / "selected"
    assert resolve_data_directory() == tmp_path / "environment"


def test_relative_paths_are_project_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MMSD_DATA_DIR", "external-data")
    assert resolve_data_directory() == PROJECT_ROOT / "external-data"
    assert resolve_data_directory("selected", project_root=tmp_path) == tmp_path / "selected"


def test_empty_environment_is_not_silently_ignored(monkeypatch):
    monkeypatch.setenv("MMSD_DATA_DIR", "  ")
    with pytest.raises(ValueError, match="empty"):
        resolve_data_directory()


def test_resolution_does_not_create_or_move_data(tmp_path, monkeypatch):
    monkeypatch.delenv("MMSD_DATA_DIR", raising=False)
    directory = tmp_path / "unused"
    assert resolve_data_directory(directory) == directory
    assert not directory.exists()
    assert isinstance(directory, Path)
