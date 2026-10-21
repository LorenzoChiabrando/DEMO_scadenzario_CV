from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src.data_paths import (
    PROJECT_ROOT,
    prepare_user_data,
    resolve_data_directory,
    user_app_directory,
    user_data_directory,
)
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
    with pytest.raises(ValueError, match="vuota"):
        resolve_data_directory()


def test_resolution_does_not_create_or_move_data(tmp_path, monkeypatch):
    monkeypatch.delenv("MMSD_DATA_DIR", raising=False)
    directory = tmp_path / "unused"
    assert resolve_data_directory(directory) == directory
    assert not directory.exists()
    assert isinstance(directory, Path)


@pytest.mark.parametrize(
    ("platform", "environ", "expected"),
    [
        ("linux", {}, "home/.local/share/ScadenzarioCV/v2"),
        ("linux", {"XDG_DATA_HOME": "xdg"}, "xdg/ScadenzarioCV/v2"),
        ("win32", {"APPDATA": "roaming"}, "roaming/ScadenzarioCV/v2"),
        ("win32", {}, "home/AppData/Roaming/ScadenzarioCV/v2"),
        ("darwin", {}, "home/Library/Application Support/ScadenzarioCV/v2"),
    ],
)
def test_user_app_directory_follows_platform_conventions(tmp_path, platform, environ, expected):
    environ = {key: str(tmp_path / value) for key, value in environ.items()}

    directory = user_app_directory(platform=platform, environ=environ, home=tmp_path / "home")

    # "v2": the executable of the previous version kept older-format data in ScadenzarioCV.
    assert directory == tmp_path / expected


def test_the_executable_keeps_data_in_the_user_folder(tmp_path, monkeypatch):
    monkeypatch.delenv("MMSD_DATA_DIR", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    # The bundle is extracted to a temporary folder deleted on exit: data must live elsewhere.
    assert resolve_data_directory() == user_data_directory()
    assert user_data_directory() == user_app_directory() / "dati"
    assert resolve_data_directory(tmp_path / "selected") == tmp_path / "selected"
    monkeypatch.setenv("MMSD_DATA_DIR", str(tmp_path / "environment"))
    assert resolve_data_directory() == tmp_path / "environment"


def _bundle(tmp_path: Path) -> Path:
    bundled = tmp_path / "bundle" / "mock_data"
    (bundled / "pazienti").mkdir(parents=True)
    (bundled / "pazienti" / "PZ0001.json").write_text('{"id": "PZ0001"}', encoding="utf-8")
    return bundled


def test_first_start_copies_the_bundled_demo_data(tmp_path):
    target = tmp_path / "user" / "dati"

    assert prepare_user_data(target, _bundle(tmp_path)) is True

    assert (target / "pazienti" / "PZ0001.json").read_text(encoding="utf-8") == '{"id": "PZ0001"}'
    assert [path.name for path in target.parent.iterdir()] == ["dati"]  # no half-copied folders


def test_later_starts_keep_the_user_changes(tmp_path):
    target = tmp_path / "user" / "dati"
    bundled = _bundle(tmp_path)
    prepare_user_data(target, bundled)
    (target / "pazienti" / "PZ0001.json").write_text('{"id": "changed"}', encoding="utf-8")

    assert prepare_user_data(target, bundled) is False

    assert (target / "pazienti" / "PZ0001.json").read_text(encoding="utf-8") == '{"id": "changed"}'
