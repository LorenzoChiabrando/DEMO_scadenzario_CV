from __future__ import annotations

import threading
import time
from datetime import date
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QApplication

from src.controllers.controller_sale_operatorie import ControllerSaleOperatorie
from src.optimization.exceptions import PlanningCancelledError
from src.optimization.results import SolveStatus


class _Control(QObject):
    clicked = Signal()

    def __init__(self, text: str = "") -> None:
        super().__init__()
        self._text = text
        self.enabled = True

    def text(self) -> str:
        return self._text

    def setText(self, text: str) -> None:
        self._text = text

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled


class _Table(_Control):
    cellChanged = Signal(int, int)
    cellClicked = Signal(int, int)
    operazione_spostata = Signal(int, int, int)
    operazione_scambiata = Signal(int, int, int)


class _View(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.btn_storico = _Control()
        self.btn_consultazione = _Control()
        self.btn_pianificazione = _Control()
        self.btn_indietro = _Control()
        self.btn_prev = _Control()
        self.btn_next = _Control()
        self.btn_pianifica = _Control("PIANIFICA SETTIMANA")
        self.btn_pulisci = _Control()
        self.btn_convalida = _Control()
        self.tabella = _Table()


class _Model:
    def __init__(self) -> None:
        self.cache_invalidations = 0

    def get_operazioni(self, _day: str) -> list[dict[str, object]]:
        return []

    def invalidate_cache(self) -> None:
        self.cache_invalidations += 1


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _wait_until(
    app: QApplication,
    predicate,
    *,
    timeout_seconds: float = 2.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            pytest.fail("timed out while waiting for the Qt worker")
        time.sleep(0.001)
    app.processEvents()


def _planning_result() -> SimpleNamespace:
    solver_result = SimpleNamespace(
        objective=None,
        schedule=(object(), object()),
        status=SolveStatus.OPTIMAL,
    )
    return SimpleNamespace(result=solver_result)


def _controller(service) -> tuple[ControllerSaleOperatorie, _View, _Model, list[tuple]]:
    view = _View()
    model = _Model()
    controller = ControllerSaleOperatorie(
        view,
        model,
        model_scadenzario=object(),
        project_root=".",
        planning_service=service,
    )
    controller.settimana_display = date(2026, 5, 4)
    refreshes: list[bool] = []
    notices: list[tuple] = []
    controller.aggiorna_tabella = lambda: refreshes.append(True)
    controller._avviso = lambda *args, **kwargs: notices.append((*args, kwargs))
    controller._test_refreshes = refreshes
    return controller, view, model, notices


def _dispose_controller(app: QApplication, controller: ControllerSaleOperatorie) -> None:
    if controller._planning_worker is not None:
        controller.shutdown_planning()
        _wait_until(app, lambda: controller._planning_worker is None)
    controller.deleteLater()
    app.processEvents()


def test_planner_runs_off_the_ui_thread_then_invalidates_cache_and_refreshes(
    qt_app: QApplication,
) -> None:
    service_started = threading.Event()
    release_service = threading.Event()
    service_thread: list[QThread] = []
    main_qt_thread = QThread.currentThread()

    def service(*_args, **_kwargs):
        service_thread.append(QThread.currentThread())
        service_started.set()
        assert release_service.wait(2.0)
        return _planning_result()

    controller, view, model, notices = _controller(service)
    busy_states: list[bool] = []
    controller.planning_busy_changed.connect(busy_states.append)
    try:
        controller.pianifica_settimana()
        _wait_until(qt_app, service_started.is_set)

        assert controller._planning_worker is not None
        assert service_thread == [controller._planning_worker]
        assert service_thread[0] is not main_qt_thread
        assert busy_states == [True]
        assert view.btn_pianifica.text() == "ANNULLA PIANIFICAZIONE"
        assert view.btn_pianifica.enabled is True
        assert view.tabella.enabled is False
        assert model.cache_invalidations == 0

        release_service.set()
        _wait_until(qt_app, lambda: controller._planning_worker is None)

        assert model.cache_invalidations == 1
        assert controller._test_refreshes == [True]
        assert notices[0][0] == "Pianificazione completata"
        assert view.btn_pianifica.text() == "PIANIFICA SETTIMANA"
        assert view.tabella.enabled is True
        assert busy_states == [True, False]
    finally:
        release_service.set()
        _dispose_controller(qt_app, controller)


def test_second_planning_action_sets_the_cooperative_cancel_token(
    qt_app: QApplication,
) -> None:
    service_started = threading.Event()
    cancellation_seen = threading.Event()

    def service(*_args, cancel_requested, **_kwargs):
        service_started.set()
        deadline = time.monotonic() + 2.0
        while not cancel_requested():
            if time.monotonic() >= deadline:
                raise AssertionError("controller did not forward cancellation")
            time.sleep(0.001)
        cancellation_seen.set()
        raise PlanningCancelledError("cancelled")

    controller, view, model, notices = _controller(service)
    try:
        controller.pianifica_settimana()
        _wait_until(qt_app, service_started.is_set)

        controller.pianifica_settimana()

        assert view.btn_pianifica.text() == "ANNULLAMENTO IN CORSO…"
        assert view.btn_pianifica.enabled is False
        _wait_until(qt_app, cancellation_seen.is_set)
        _wait_until(qt_app, lambda: controller._planning_worker is None)

        assert model.cache_invalidations == 0
        assert controller._test_refreshes == []
        assert notices[0][0] == "Pianificazione annullata"
        assert view.btn_pianifica.text() == "PIANIFICA SETTIMANA"
        assert view.btn_pianifica.enabled is True
    finally:
        _dispose_controller(qt_app, controller)


def test_shutdown_waits_for_cooperative_worker_termination(
    qt_app: QApplication,
) -> None:
    service_started = threading.Event()
    cancellation_seen = threading.Event()

    def service(*_args, cancel_requested, **_kwargs):
        service_started.set()
        deadline = time.monotonic() + 2.0
        while not cancel_requested():
            if time.monotonic() >= deadline:
                raise AssertionError("shutdown did not forward cancellation")
            time.sleep(0.001)
        cancellation_seen.set()
        raise PlanningCancelledError("cancelled")

    controller, _view, model, notices = _controller(service)
    try:
        controller.pianifica_settimana()
        _wait_until(qt_app, service_started.is_set)
        active_thread = controller._planning_worker

        assert active_thread is not None
        assert controller.shutdown_planning(timeout_ms=2_000) is True
        assert active_thread.isRunning() is False
        assert cancellation_seen.is_set()

        _wait_until(qt_app, lambda: controller._planning_worker is None)
        assert model.cache_invalidations == 0
        assert notices[0][0] == "Pianificazione annullata"
    finally:
        _dispose_controller(qt_app, controller)
