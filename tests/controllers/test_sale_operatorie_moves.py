from __future__ import annotations

import copy
import datetime as dt
from types import SimpleNamespace

from PySide6.QtCore import QObject

from src.controllers.controller_sale_operatorie import ControllerSaleOperatorie


def _operation(name: str, duration: int, room_id: str = "OR-1") -> dict[str, object]:
    return {
        "nome_paziente": name,
        "durata": duration,
        "sala_operatoria": room_id,
    }


class _FakeModel:
    def __init__(self, operations: dict[str, list[dict[str, object]]], fail_at: int | None = None):
        self.operations = copy.deepcopy(operations)
        self.fail_at = fail_at
        self.set_calls = 0

    def get_operazioni(self, day: str) -> list[dict[str, object]]:
        return copy.deepcopy(self.operations.get(day, []))

    def set_operazioni(self, day: str, operations: list[dict[str, object]]) -> None:
        self.set_calls += 1
        if self.set_calls == self.fail_at:
            raise OSError("synthetic write failure")
        self.operations[day] = copy.deepcopy(operations)

    def load_mese(self, _year: int, _month: int) -> dict[str, object]:
        return {
            "turni": {
                day: {
                    "specializzandi": {
                        "OR I": "Alpha R.",
                        "OR II": "Beta R.",
                    }
                }
                for day in self.operations
            }
        }


class _RecordingLibretto:
    def __init__(self) -> None:
        self.activities: dict[str, list[dict[str, object]]] | None = None

    def registra_attivita_settimana(
        self,
        activities: dict[str, list[dict[str, object]]],
    ) -> None:
        self.activities = copy.deepcopy(activities)


def _controller(model: _FakeModel):
    controller = ControllerSaleOperatorie.__new__(ControllerSaleOperatorie)
    QObject.__init__(controller)
    controller.model = model
    controller.view = SimpleNamespace(MAX_OPS=12)
    controller.modalita_corrente = "PIANIFICAZIONE"
    controller._stato_corrente = "BOZZA"
    controller.settimana_display = dt.date(2026, 5, 4)
    controller.model_paz = None
    controller.model_lib = None
    warnings: list[tuple[str, str]] = []
    refreshes: list[bool] = []
    controller._avviso = lambda title, message, **_kwargs: warnings.append((title, message))
    controller.aggiorna_tabella = lambda: refreshes.append(True)
    return controller, warnings, refreshes


def test_cross_day_move_rejects_negative_source_index() -> None:
    model = _FakeModel({"2026-05-04": [_operation("A", 60)], "2026-05-05": []})
    controller, warnings, _ = _controller(model)

    controller._sposta_operazione(0, -1, 1)

    assert model.set_calls == 0
    assert warnings == []


def test_cross_day_move_rejects_full_destination() -> None:
    destination = [_operation(str(index), 30) for index in range(12)]
    model = _FakeModel({"2026-05-04": [_operation("A", 60)], "2026-05-05": destination})
    controller, warnings, _ = _controller(model)

    controller._sposta_operazione(0, 0, 1)

    assert model.set_calls == 0
    assert warnings[0][0] == "Sala completa"


def test_cross_day_move_rejects_schedule_ending_after_1800() -> None:
    destination = [_operation(str(index), 90) for index in range(6)]
    model = _FakeModel({"2026-05-04": [_operation("A", 90)], "2026-05-05": destination})
    controller, warnings, _ = _controller(model)

    controller._sposta_operazione(0, 0, 1)

    assert model.set_calls == 0
    assert warnings[0][0] == "Capacità giornaliera superata"


def test_cross_day_move_rejects_non_positive_duration() -> None:
    model = _FakeModel(
        {
            "2026-05-04": [_operation("A", 60)],
            "2026-05-05": [_operation("B", -30)],
        }
    )
    controller, warnings, _ = _controller(model)

    controller._sposta_operazione(0, 0, 1)

    assert model.set_calls == 0
    assert warnings[0][0] == "Durata non valida"


def test_cross_day_move_recalculates_both_days() -> None:
    model = _FakeModel(
        {
            "2026-05-04": [_operation("A", 60), _operation("B", 90)],
            "2026-05-05": [_operation("C", 30)],
        }
    )
    controller, warnings, refreshes = _controller(model)

    controller._sposta_operazione(0, 1, 1)

    assert warnings == []
    assert model.set_calls == 2
    assert refreshes == [True]
    assert model.operations["2026-05-04"][0]["ora_fine"] == "09:00"
    assert model.operations["2026-05-05"][1]["ora_inizio"] == "08:41"
    assert model.operations["2026-05-05"][1]["ora_fine"] == "10:11"


def test_two_rooms_have_independent_capacity_and_timelines() -> None:
    destination = [_operation(str(index), 90, "OR-2") for index in range(6)]
    model = _FakeModel(
        {
            "2026-05-04": [_operation("A", 90, "OR-1")],
            "2026-05-05": destination,
        }
    )
    controller, warnings, _ = _controller(model)

    controller._sposta_operazione(0, 0, 1)

    assert warnings == []
    moved = next(
        operation
        for operation in model.operations["2026-05-05"]
        if operation["nome_paziente"] == "A"
    )
    assert moved["sala_operatoria"] == "OR-1"
    assert moved["ora_inizio"] == "08:00"
    assert model.operations["2026-05-05"][0]["ora_inizio"] == "08:00"


def test_cross_day_move_rolls_back_after_persistence_failure() -> None:
    original = {
        "2026-05-04": [_operation("A", 60)],
        "2026-05-05": [_operation("B", 30)],
    }
    model = _FakeModel(original, fail_at=2)
    controller, warnings, refreshes = _controller(model)

    controller._sposta_operazione(0, 0, 1)

    assert model.operations == original
    assert warnings[0][0] == "Spostamento non salvato"
    assert refreshes == [True]


def test_cross_day_move_clears_individual_resident_assignment() -> None:
    assigned = {
        **_operation("Synthetic", 60),
        "id_specializzando": "R1",
        "specializzando": "Alpha R.",
        "ruolo_specializzando": "OR I",
    }
    model = _FakeModel({"2026-05-04": [assigned], "2026-05-05": []})
    controller, warnings, _ = _controller(model)

    controller._sposta_operazione(0, 0, 1)

    assert warnings == []
    moved = model.operations["2026-05-05"][0]
    assert moved["id_specializzando"] == ""
    assert moved["specializzando"] == ""
    assert moved["ruolo_specializzando"] == ""


def test_validation_registers_only_the_individually_assigned_resident() -> None:
    operation = {
        **_operation("Synthetic", 60),
        "id_specializzando": "R2",
        "specializzando": "Beta R.",
        "ruolo_specializzando": "OR II",
    }
    model = _FakeModel({"2026-05-04": [operation]})
    controller, _, _ = _controller(model)
    libretto = _RecordingLibretto()
    controller.model_lib = libretto

    controller._registra_in_libretti()

    assert libretto.activities is not None
    assert list(libretto.activities) == ["Beta R."]
    assert libretto.activities["Beta R."][0]["ruolo"] == "OR II"


def test_validation_keeps_legacy_dual_registration() -> None:
    model = _FakeModel({"2026-05-04": [_operation("Synthetic", 60)]})
    controller, _, _ = _controller(model)
    libretto = _RecordingLibretto()
    controller.model_lib = libretto

    controller._registra_in_libretti()

    assert libretto.activities is not None
    assert set(libretto.activities) == {"Alpha R.", "Beta R."}
    assert libretto.activities["Alpha R."][0]["ruolo"] == "OR I"
    assert libretto.activities["Beta R."][0]["ruolo"] == "OR II"


def test_historic_months_and_week_switch_include_cross_month_week() -> None:
    controller = ControllerSaleOperatorie.__new__(ControllerSaleOperatorie)
    QObject.__init__(controller)
    controller._settimane_convalidate = [dt.date(2024, 1, 29)]
    controller._idx_storico = 0
    controller.modalita_corrente = "STORICO"
    controller.visualizzazione = "MESE"
    controller.mese_display = dt.date(2024, 2, 1)
    controller.settimana_display = dt.date(2024, 1, 29)
    month_modes: list[bool] = []
    controller.view = SimpleNamespace(set_month_mode=month_modes.append)
    controller.aggiorna_tabella = lambda: None

    assert controller._mesi_storici() == [dt.date(2024, 1, 1), dt.date(2024, 2, 1)]

    controller.imposta_visualizzazione("SETTIMANA")

    assert controller.settimana_display == dt.date(2024, 1, 29)
    assert controller._idx_storico == 0
    assert month_modes == [False]
