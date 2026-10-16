"""I messaggi che possono arrivare all'utente devono essere in italiano."""

from __future__ import annotations

import ast
import errno
import re
from pathlib import Path

import pytest

from src.data_paths import PROJECT_ROOT
from src.error_messages import describe_error, describe_os_error
from src.importers.patient_csv import PatientCsvError, read_patient_csv
from src.optimization.results import SolveStatus

_ENGLISH_WORDS = re.compile(
    r"\b(the|must|cannot|can't|is|are|has|have|was|were|be|been|invalid|required|missing|"
    r"unknown|only|every|least|exactly|should|failed|unavailable|could|does|did|not|requires|"
    r"appears|contains|unexpected|error|while|please|no|of|for|with|without|and|or)\b",
    re.IGNORECASE,
)
_ERROR_LISTS = {"errors", "reasons", "problems", "issues"}


def _strings(node: ast.AST) -> list[str]:
    """Testi letterali (anche nelle f-string) contenuti in un nodo."""

    return [
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    ]


def _is_user_message_call(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr == "emit":
        return True
    return (
        func.attr == "append" and isinstance(func.value, ast.Name) and func.value.id in _ERROR_LISTS
    )


def _messages(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            found += [(node.lineno, text) for text in _strings(node.exc)]
        elif isinstance(node, ast.Call) and _is_user_message_call(node):
            found += [(node.lineno, text) for text in _strings(node)]
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "__init__"
            and isinstance(node.func.value, ast.Call)
        ):
            # super().__init__("...") nelle eccezioni personalizzate
            found += [(node.lineno, text) for text in _strings(node)]
    return found


def test_messages_that_reach_the_user_are_italian() -> None:
    sources = sorted((PROJECT_ROOT / "src").rglob("*.py"))
    english = [
        f"{path.relative_to(PROJECT_ROOT)}:{line}: {text!r}"
        for path in sources
        for line, text in _messages(path)
        if _ENGLISH_WORDS.search(text)
    ]
    assert english == [], "Messaggi in inglese:\n" + "\n".join(english)


def test_guard_detects_english_messages(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "def f(errors):\n"
        "    errors.append('resident_id cannot be blank')\n"
        "    raise ValueError(f'the week {1} is convalidated')\n"
        "    raise ValueError('La settimana è già convalidata')\n",
        encoding="utf-8",
    )

    flagged = [text for _, text in _messages(sample) if _ENGLISH_WORDS.search(text)]

    assert sorted(flagged) == [" is convalidated", "resident_id cannot be blank", "the week "]


def test_every_solver_status_has_an_italian_label() -> None:
    labels = {status: status.label for status in SolveStatus}

    assert labels[SolveStatus.OPTIMAL] == "ottimo"
    assert labels[SolveStatus.FEASIBLE] == "ammissibile (ottimalità non dimostrata)"
    assert all(label and not _ENGLISH_WORDS.search(label) for label in labels.values())
    assert len(set(labels.values())) == len(labels)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (PermissionError(errno.EACCES, "Permission denied", "/tmp/x.pdf"), "Permesso negato"),
        (FileNotFoundError(errno.ENOENT, "No such file", "/tmp/x.csv"), "non esiste"),
        (OSError(errno.ENOSPC, "No space left on device"), "Spazio su disco esaurito"),
        (OSError(errno.EROFS, "Read-only file system", "/mnt/x.pdf"), "sola lettura"),
        (IsADirectoryError(errno.EISDIR, "Is a directory", "/tmp"), "è una cartella"),
        (OSError(errno.EIO, "Input/output error"), "Errore di sistema"),
    ],
)
def test_os_errors_are_described_in_italian(error: OSError, expected: str) -> None:
    text = describe_os_error(error)

    assert expected in text
    assert not _ENGLISH_WORDS.search(text.replace(str(error.filename or ""), ""))
    if error.filename:
        assert str(error.filename) in text


def test_unexpected_csv_read_errors_are_explained_in_italian(tmp_path: Path) -> None:
    with pytest.raises(PatientCsvError) as caught:
        read_patient_csv(tmp_path)

    assert str(caught.value) == (
        f"Impossibile leggere il file: Il percorso indicato è una cartella: {tmp_path}"
    )


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            PermissionError(errno.EACCES, "Permission denied", "/tmp/x.pdf"),
            "Permesso negato: /tmp/x.pdf",
        ),
        (
            ValueError("Il PDF richiede un titolo e un periodo."),
            "Il PDF richiede un titolo e un periodo.",
        ),
    ],
)
def test_describe_error_translates_only_system_errors(error: Exception, expected: str) -> None:
    assert describe_error(error) == expected
