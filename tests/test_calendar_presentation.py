from __future__ import annotations

from src.calendar_presentation import fit_resident_label


def test_label_falls_back_to_surname_then_initials() -> None:
    assert fit_resident_label("Gasparri A.", lambda text: True) == "Gasparri A."
    assert fit_resident_label("Gasparri A.", lambda text: len(text) <= 8) == "Gasparri"
    assert fit_resident_label("Gasparri A.", lambda text: len(text) <= 2) == "GA"
    assert fit_resident_label("Gasparri A.", lambda text: False) == "GA"
