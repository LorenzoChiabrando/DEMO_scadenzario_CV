from __future__ import annotations

import calendar
import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QLabel,
    QPushButton,
)

from src.calendar_versions import CalendarVersion
from src.controllers import controller_scadenzario
from src.controllers.controller_scadenzario import (
    ControllerScadenzario,
    build_scadenzario_pdf_document,
)
from src.models.data_manager import DataManager
from src.models.data_manager_sale_operatorie import DataManagerSaleOperatorie
from src.planning_schema import default_schedule_optimization
from src.views.components import messages
from src.views.dialog_assegnazione_turno import DialogAssegnazioneSpecializzando
from src.views.view_scadenzario import ViewScadenzario


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def roster(qt_app: QApplication, tmp_path: Path) -> Iterator[ControllerScadenzario]:
    model = DataManager(tmp_path / "scadenzario", tmp_path / "libretti")
    rooms = DataManagerSaleOperatorie(tmp_path / "sale_operatorie")
    view = ViewScadenzario()
    controller = ControllerScadenzario(view, model, rooms)
    controller.real_anno, controller.real_mese = 2026, 10
    controller.anno_corrente, controller.mese_corrente = 2026, 9
    controller.modalita_corrente = "STORICO"
    view.stacked_widget.setCurrentIndex(1)
    controller.aggiorna_tabella()
    yield controller
    view.close()
    view.deleteLater()
    qt_app.processEvents()


def _month(state: str = "BOZZA", year: int = 2026, month: int = 9) -> dict:
    return {
        "metadata": {"stato": state},
        "turni": {
            day.isoformat(): {
                "Tipo Guardia": "118",
                "Sala Op. I": "Alpha R.",
                "Sala Op. II": "Beta R.",
            }
            for number in range(1, calendar.monthrange(year, month)[1] + 1)
            if (day := date(year, month, number)).weekday() < 5
        },
        "modello_ottimizzazione": default_schedule_optimization(),
    }


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _select(controller: ControllerScadenzario, version: CalendarVersion) -> None:
    controller.view.combo_versione.setCurrentIndex(
        controller.view.combo_versione.findData(version.value)
    )


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*.json")}


def _value(controller: ControllerScadenzario, row: int, column: int) -> str:
    """Valore mostrato dalla vista per attività (indipendente da Dettaglio/Intero mese)."""
    return controller.view.modello_attivita.value_at(row, column)


def _editable(controller: ControllerScadenzario, row: int = 4, column: int = 0) -> bool:
    """Un click sulla cella aprirebbe il dialog di assegnazione."""
    return controller._cella_modificabile(row, column)


def _record_warnings(monkeypatch: pytest.MonkeyPatch, *, text: bool = False) -> list[str]:
    shown: list[str] = []

    def show_message(_parent, title: str, message: str, **_kwargs) -> None:
        shown.append(message if text else title)

    monkeypatch.setattr(messages, "show_message", show_message)
    return shown


def _answer_confirmations(monkeypatch: pytest.MonkeyPatch, answer: bool) -> None:
    monkeypatch.setattr(messages, "ask_confirmation", lambda *_args, **_kwargs: answer)


@pytest.mark.parametrize("mode", ["STORICO", "CORRENTE", "PIANIFICAZIONE"])
def test_switch_preserves_period_zoom_and_leaves_missing_actual_unwritten(
    roster: ControllerScadenzario,
    tmp_path: Path,
    mode: str,
) -> None:
    _write(tmp_path / "scadenzario/2026-09.json", _month("CONVALIDATO"))
    roster.modalita_corrente = mode
    roster.imposta_vista_compatta(True)
    before = _snapshot(tmp_path)

    _select(roster, CalendarVersion.EFFETTIVO)

    assert (roster.anno_corrente, roster.mese_corrente) == (2026, 9)
    assert roster.modalita_corrente == mode
    assert roster.view._compact
    assert roster.model.version == CalendarVersion.EFFETTIVO
    assert roster.model_sale_op.version == CalendarVersion.EFFETTIVO
    assert roster._model_previsto.version == CalendarVersion.PREVISTO
    assert roster._model_sale_base.version == CalendarVersion.PREVISTO
    assert "ASSENTE" in roster.view.lbl_stato.text()
    assert "non ancora creato" in roster.view.lbl_versione_info.text()
    assert not roster.view.btn_crea_effettivo.isHidden()
    assert roster.view.btn_convalida.isHidden()
    assert not roster.view.btn_esporta_pdf.isEnabled()
    assert not _editable(roster)
    assert _value(roster, 4, 0) == ""
    assert _snapshot(tmp_path) == before

    _select(roster, CalendarVersion.PREVISTO)
    assert _value(roster, 4, 0) == "Alpha R."
    assert roster.view._compact
    assert _snapshot(tmp_path) == before


def test_missing_actual_cannot_be_created_from_unconfirmed_planned(
    roster: ControllerScadenzario,
    tmp_path: Path,
) -> None:
    _write(tmp_path / "scadenzario/2026-09.json", _month())
    _select(roster, CalendarVersion.EFFETTIVO)

    assert roster.view.btn_crea_effettivo.isHidden()
    assert "Convalida il Previsto" in roster.view.lbl_versione_info.text()
    assert not (tmp_path / "scadenzario/effettivo").exists()


def test_history_uses_both_versions_and_month_navigation_preserves_actual_selection(
    roster: ControllerScadenzario,
    tmp_path: Path,
) -> None:
    _write(tmp_path / "scadenzario/2026-08.json", _month("CONVALIDATO", month=8))
    _write(tmp_path / "scadenzario/2026-09.json", _month("CONVALIDATO"))
    actual = _month()
    actual["turni"]["2026-09-01"]["Sala Op. I"] = "Gamma R."
    _write(tmp_path / "scadenzario/effettivo/2026-09.json", actual)
    _select(roster, CalendarVersion.EFFETTIVO)
    before = _snapshot(tmp_path)

    roster.apri_calendario("STORICO")
    assert roster.mese_corrente == 9
    assert _value(roster, 4, 0) == "Gamma R."
    roster.mese_precedente()
    assert roster.mese_corrente == 8
    assert "ASSENTE" in roster.view.lbl_stato.text()
    assert not roster.view.btn_crea_effettivo.isHidden()
    roster.mese_successivo()

    assert roster.mese_corrente == 9
    assert roster.versione_corrente == CalendarVersion.EFFETTIVO
    assert roster.view.combo_versione.currentData() == CalendarVersion.EFFETTIVO.value
    assert _value(roster, 4, 0) == "Gamma R."
    assert _snapshot(tmp_path) == before


def _history_with_an_unconfirmed_gap(tmp_path: Path) -> None:
    """August and October (the current month) confirmed, September still a draft."""
    _write(tmp_path / "scadenzario/2026-08.json", _month("CONVALIDATO", month=8))
    _write(tmp_path / "scadenzario/2026-09.json", _month())
    _write(tmp_path / "scadenzario/2026-10.json", _month("CONVALIDATO", month=10))


@pytest.mark.parametrize("version", list(CalendarVersion))
def test_history_lists_only_months_with_a_confirmed_plan(
    roster: ControllerScadenzario,
    tmp_path: Path,
    version: CalendarVersion,
) -> None:
    # As the operating rooms list only confirmed weeks: a draft never confirmed is not history.
    _history_with_an_unconfirmed_gap(tmp_path)
    _select(roster, version)

    roster.apri_calendario("STORICO")
    assert (roster.anno_corrente, roster.mese_corrente) == (2026, 10)
    assert roster.view.btn_next.isHidden()
    assert not roster.view.btn_prev.isHidden()

    roster.mese_precedente()
    assert roster.mese_corrente == 8
    assert roster.view.btn_prev.isHidden()
    assert not roster.view.btn_next.isHidden()

    roster.mese_successivo()
    assert roster.mese_corrente == 10


@pytest.mark.parametrize(
    ("picked", "shown"),
    [((9, 2026), 8), ((12, 2026), 10), ((1, 2026), 8)],
    ids=["draft-gap", "after-last", "before-first"],
)
def test_history_month_picker_lands_on_a_confirmed_month(
    roster: ControllerScadenzario,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    picked: tuple[int, int],
    shown: int,
) -> None:
    _history_with_an_unconfirmed_gap(tmp_path)
    roster.apri_calendario("STORICO")

    class Pick:
        def __init__(self, *_args: object) -> None:
            pass

        def exec(self) -> int:
            return 1

        def get_selezione(self) -> tuple[int, int]:
            return picked

    monkeypatch.setattr(controller_scadenzario, "DialogMeseAnno", Pick)
    roster.scegli_mese_anno()

    assert (roster.anno_corrente, roster.mese_corrente) == (2026, shown)


def test_history_without_confirmed_months_stays_on_the_dashboard(
    roster: ControllerScadenzario,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write(tmp_path / "scadenzario/2026-09.json", _month())
    roster.torna_alla_dashboard()
    shown = _record_warnings(monkeypatch)

    roster.apri_calendario("STORICO")

    assert shown and shown[0].startswith("Nessuno storico")
    assert roster.modalita_corrente is None
    assert roster.view.stacked_widget.currentIndex() == 0


def test_explicit_creation_initializes_legacy_actual_without_altering_planned(
    roster: ControllerScadenzario,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "scadenzario/2026-09.json"
    target = tmp_path / "scadenzario/effettivo/2026-09.json"
    _write(source, _month("CONVALIDATO"))
    before = source.read_bytes()
    _select(roster, CalendarVersion.EFFETTIVO)
    _answer_confirmations(monkeypatch, False)
    roster.view.btn_crea_effettivo.click()
    assert not target.exists()

    _answer_confirmations(monkeypatch, True)
    roster.view.btn_crea_effettivo.click()

    assert json.loads(target.read_text())["metadata"]["stato"] == "BOZZA"
    assert source.read_bytes() == before
    assert roster.view.btn_crea_effettivo.isHidden()
    assert not roster.view.btn_convalida.isHidden()
    assert _editable(roster)
    roster.assegna(4, 0, "Gamma R.")
    assert json.loads(target.read_text())["turni"]["2026-09-01"]["Sala Op. I"] == "Gamma R."
    assert source.read_bytes() == before
    assert not (tmp_path / "sale_operatorie/effettivo").exists()


def test_actual_confirmed_month_remains_read_only_in_history(
    roster: ControllerScadenzario,
    tmp_path: Path,
) -> None:
    target = tmp_path / "scadenzario/effettivo/2026-09.json"
    _write(target, _month("CONVALIDATO"))
    _select(roster, CalendarVersion.EFFETTIVO)
    before = target.read_bytes()

    assert not _editable(roster)
    assert roster.view.btn_convalida.isHidden()
    roster.assegna(4, 0, "Gamma R.")
    assert target.read_bytes() == before


def test_history_click_opens_the_modal_only_for_the_actual_and_saves_there(
    roster: ControllerScadenzario,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nello Storico il Previsto è in sola lettura; l'Effettivo si corregge dal dialog."""
    planned = tmp_path / "scadenzario/2026-09.json"
    _write(planned, _month("CONVALIDATO"))
    _write(tmp_path / "scadenzario/effettivo/2026-09.json", _month())
    planned_before = planned.read_bytes()
    opened: list[QDialog] = []

    def accept(dialog: QDialog) -> QDialog.DialogCode:
        opened.append(dialog)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(DialogAssegnazioneSpecializzando, "exec", accept)
    monkeypatch.setattr(DialogAssegnazioneSpecializzando, "selected_value", lambda _d: "Gamma R.")
    row = roster.view.row_labels.index("Sala Op. I")

    roster.view.tabella.clicked.emit(roster.view.tabella.model().index(row, 0))
    assert opened == []

    _select(roster, CalendarVersion.EFFETTIVO)
    roster.view.tabella.clicked.emit(roster.view.tabella.model().index(row, 0))

    assert len(opened) == 1
    assert roster.model.get_valore_cella("2026-09-01", "Sala Op. I") == "Gamma R."
    assert _value(roster, row, 0) == "Gamma R."
    assert planned.read_bytes() == planned_before


def test_actual_roster_does_not_silently_reassign_individual_operations(
    roster: ControllerScadenzario,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write(tmp_path / "scadenzario/effettivo/2026-09.json", _month())
    _write(
        tmp_path / "sale_operatorie/effettivo/2026-09.json",
        {
            "metadata": {"stato": "BOZZA", "settimane": {"2026-09-07": "BOZZA"}},
            "turni": {
                "2026-09-07": {
                    "specializzandi": {"OR I": "Alpha R.", "OR II": "Beta R."},
                    "operazioni": [
                        {
                            "sala_operatoria": "OR-1",
                            "id_specializzando": "SYN-1",
                            "specializzando": "Alpha R.",
                            "ruolo_specializzando": "OR I",
                        }
                    ],
                }
            },
        },
    )
    warnings = _record_warnings(monkeypatch)
    _select(roster, CalendarVersion.EFFETTIVO)
    before = _snapshot(tmp_path)

    roster.assegna(4, 6, "Gamma R.")

    assert warnings == ["Assegnazioni Effettivo da verificare"]
    assert _snapshot(tmp_path) == before
    assert _value(roster, 4, 6) == "Alpha R."


def test_room_sync_failure_reports_that_the_roster_was_saved(
    roster: ControllerScadenzario,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write(tmp_path / "scadenzario/2026-09.json", _month())
    roster.modalita_corrente = "CORRENTE"
    roster.aggiorna_tabella()
    warnings = _record_warnings(monkeypatch, text=True)

    def fail_sync(*args):
        raise OSError("synthetic write failure")

    monkeypatch.setattr(roster.model_sale_op, "set_specializzandi", fail_sync)

    roster.assegna(4, 6, "Gamma R.")

    assert roster.model.get_valore_cella("2026-09-07", "Sala Op. I") == "Gamma R."
    assert "Assegnazione dello Scadenzario salvata" in warnings[0]
    assert "Aggiornamento delle Sale non riuscito" in warnings[0]


@pytest.mark.parametrize("version", list(CalendarVersion))
def test_room_assignments_propagate_only_to_the_matching_version(
    roster: ControllerScadenzario,
    tmp_path: Path,
    version: CalendarVersion,
) -> None:
    for branch in (Path(), Path("effettivo")):
        _write(tmp_path / "scadenzario" / branch / "2026-09.json", _month())
        _write(
            tmp_path / "sale_operatorie" / branch / "2026-09.json",
            {
                "metadata": {"stato": "BOZZA", "settimane": {"2026-09-07": "BOZZA"}},
                "turni": {
                    "2026-09-07": {"specializzandi": {"OR I": "Alpha R.", "OR II": "Beta R."}}
                },
            },
        )
    roster.modalita_corrente = "CORRENTE"
    _select(roster, version)
    roster.aggiorna_tabella()
    opposite = Path("effettivo") if version == CalendarVersion.PREVISTO else Path()
    unchanged_roster = tmp_path / "scadenzario" / opposite / "2026-09.json"
    unchanged_rooms = tmp_path / "sale_operatorie" / opposite / "2026-09.json"
    before = (unchanged_roster.read_bytes(), unchanged_rooms.read_bytes())

    roster.assegna(4, 6, "Gamma R.")

    assert roster.model.get_valore_cella("2026-09-07", "Sala Op. I") == "Gamma R."
    assert roster.model_sale_op.load_mese(2026, 9)["turni"]["2026-09-07"]["specializzandi"] == {
        "OR I": "Gamma R.",
        "OR II": "Beta R.",
    }
    assert (unchanged_roster.read_bytes(), unchanged_rooms.read_bytes()) == before


def test_actual_room_assignment_does_not_create_an_absent_week_in_an_existing_month(
    roster: ControllerScadenzario,
    tmp_path: Path,
) -> None:
    _write(tmp_path / "scadenzario/effettivo/2026-09.json", _month())
    rooms = tmp_path / "sale_operatorie/effettivo/2026-09.json"
    _write(
        rooms,
        {
            "metadata": {"stato": "BOZZA", "settimane": {"2026-09-14": "BOZZA"}},
            "turni": {"2026-09-14": {}},
        },
    )
    before = rooms.read_bytes()
    _select(roster, CalendarVersion.EFFETTIVO)

    roster.assegna(4, 6, "Gamma R.")

    assert roster.model.get_valore_cella("2026-09-07", "Sala Op. I") == "Gamma R."
    assert rooms.read_bytes() == before


@pytest.mark.parametrize(
    ("edited_row", "edited_role", "other_row", "other_role", "other_room"),
    [
        ("Sala Op. I", "OR I", "Sala Op. II", "OR II", "OR-2"),
        ("Sala Op. II", "OR II", "Sala Op. I", "OR I", "OR-1"),
    ],
)
@pytest.mark.parametrize("duplicate_other", [False, True])
def test_actual_room_sync_preserves_the_other_rooms_independent_assignment(
    roster: ControllerScadenzario,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    edited_row: str,
    edited_role: str,
    other_row: str,
    other_role: str,
    other_room: str,
    duplicate_other: bool,
) -> None:
    day = "2026-09-07"
    planned_path = tmp_path / "scadenzario/2026-09.json"
    _write(planned_path, _month("CONVALIDATO"))
    planned_before = planned_path.read_bytes()
    actual = _month()
    actual["turni"][day][other_row] = "Gamma R."
    _write(tmp_path / "scadenzario/effettivo/2026-09.json", actual)
    assigned = {"OR I": "Alpha R.", "OR II": "Beta R."}
    operation = {
        "sala_operatoria": other_room,
        "id_specializzando": "SYN-OTHER",
        "specializzando": assigned[other_role],
        "ruolo_specializzando": other_role,
    }
    rooms_path = tmp_path / "sale_operatorie/effettivo/2026-09.json"
    _write(
        rooms_path,
        {
            "metadata": {"stato": "BOZZA", "settimane": {day: "BOZZA"}},
            "turni": {day: {"specializzandi": assigned, "operazioni": [operation]}},
        },
    )
    warnings = _record_warnings(monkeypatch)
    _select(roster, CalendarVersion.EFFETTIVO)
    before = _snapshot(tmp_path)

    value = assigned[other_role] if duplicate_other else "Delta R."
    roster.assegna(roster.view.row_labels.index(edited_row), 6, value)

    if duplicate_other:
        assert warnings == ["Assegnazione non valida · Effettivo"]
        assert _snapshot(tmp_path) == before
        return

    assert warnings == []
    saved = json.loads(rooms_path.read_text(encoding="utf-8"))["turni"][day]
    assert saved["specializzandi"] == {**assigned, edited_role: "Delta R."}
    assert saved["operazioni"] == [operation]
    assert roster.model.get_valore_cella(day, edited_row) == "Delta R."
    assert roster.model.get_valore_cella(day, other_row) == "Gamma R."
    assert planned_path.read_bytes() == planned_before


def test_actual_room_assignment_rejects_a_confirmed_room_week(
    roster: ControllerScadenzario,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write(tmp_path / "scadenzario/effettivo/2026-09.json", _month())
    _write(
        tmp_path / "sale_operatorie/effettivo/2026-09.json",
        {
            "metadata": {"stato": "BOZZA", "settimane": {"2026-09-07": "CONVALIDATO"}},
            "turni": {"2026-09-07": {"specializzandi": {"OR I": "Alpha R.", "OR II": "Beta R."}}},
        },
    )
    warnings = _record_warnings(monkeypatch)
    _select(roster, CalendarVersion.EFFETTIVO)
    before = _snapshot(tmp_path)

    roster.assegna(4, 6, "Gamma R.")

    assert warnings == ["Sale Effettivo convalidate"]
    assert _snapshot(tmp_path) == before
    assert _value(roster, 4, 6) == "Alpha R."


def test_actual_ward_round_changes_both_months_without_touching_planned(
    roster: ControllerScadenzario,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for month in (9, 10):
        for branch in (Path(), Path("effettivo")):
            data = _month(month=month)
            data["giro_visite"] = {"2026-09-28": "Gamma R."}
            _write(tmp_path / "scadenzario" / branch / f"2026-{month:02d}.json", data)
    _select(roster, CalendarVersion.EFFETTIVO)
    originals = {path: path.read_bytes() for path in (tmp_path / "scadenzario").glob("*.json")}
    _answer_confirmations(monkeypatch, True)

    roster.assegna(6, 28, "Delta R.")

    for month in (9, 10):
        assert roster.model.load_mese(2026, month)["giro_visite"]["2026-09-28"] == "Delta R."
    assert all(path.read_bytes() == content for path, content in originals.items())


def test_actual_pdf_reads_selected_content_and_identifies_the_version(
    roster: ControllerScadenzario,
    tmp_path: Path,
) -> None:
    _write(tmp_path / "scadenzario/2026-09.json", _month("CONVALIDATO"))
    actual = _month()
    actual["turni"]["2026-09-01"]["Sala Op. I"] = "Gamma R."
    _write(tmp_path / "scadenzario/effettivo/2026-09.json", actual)
    _select(roster, CalendarVersion.EFFETTIVO)

    document = build_scadenzario_pdf_document(
        roster.roster,
        (date(2026, 9, 1),),
        [],
        version=roster.versione_corrente,
    )

    assert "Effettivo" in document.title
    assert "Gamma R." in {value for row in document.rows for value in row.values}


@pytest.fixture
def roster_view(qt_app: QApplication) -> Iterator[ViewScadenzario]:
    view = ViewScadenzario()
    view.stacked_widget.setCurrentIndex(1)
    view.resize(1300, 850)
    view.show()
    qt_app.processEvents()
    try:
        yield view
    finally:
        view.close()
        view.deleteLater()
        qt_app.processEvents()


def test_roster_exposes_both_versions_and_actual_creation_controls(
    roster_view: ViewScadenzario,
) -> None:
    selector = roster_view.combo_versione

    assert isinstance(selector, QComboBox)
    assert selector.isVisible()
    assert [(selector.itemText(index), selector.itemData(index)) for index in range(2)] == [
        ("Previsto", CalendarVersion.PREVISTO.value),
        ("Effettivo", CalendarVersion.EFFETTIVO.value),
    ]
    assert selector.count() == 2
    assert selector.currentData() == CalendarVersion.PREVISTO.value
    assert isinstance(roster_view.lbl_versione_info, QLabel)
    assert isinstance(roster_view.btn_crea_effettivo, QPushButton)


@pytest.mark.parametrize("version", list(CalendarVersion))
def test_compact_toggle_preserves_the_version_selection(
    roster_view: ViewScadenzario,
    qt_app: QApplication,
    version: CalendarVersion,
) -> None:
    selector = roster_view.combo_versione
    selector.setCurrentIndex(selector.findData(version.value))
    changes: list[int] = []
    selector.currentIndexChanged.connect(changes.append)

    for compact in (True, False, True, False):
        roster_view.set_compact_mode(compact)
        qt_app.processEvents()

        assert selector.isVisible()
        assert selector.currentData() == version.value
        assert selector.currentText() == version.name.capitalize()
        assert selector.count() == 2

    assert changes == []


@pytest.mark.parametrize("mode", ["CORRENTE", "STORICO", "PIANIFICAZIONE"])
@pytest.mark.parametrize("state", ["BOZZA", "CONVALIDATO"])
def test_roster_badges_distinguish_versions_and_keep_the_state_visible(
    roster_view: ViewScadenzario,
    mode: str,
    state: str,
) -> None:
    roster_view.aggiorna_badge_modalita(mode, state, CalendarVersion.PREVISTO.value)
    planned_badge = roster_view.lbl_modalita.text()

    assert mode in planned_badge
    assert "PREVISTO" in planned_badge
    assert "EFFETTIVO" not in planned_badge
    assert roster_view.lbl_stato.isVisible()
    assert state in roster_view.lbl_stato.text()

    roster_view.aggiorna_badge_modalita(mode, state, CalendarVersion.EFFETTIVO)
    actual_badge = roster_view.lbl_modalita.text()

    assert mode in actual_badge
    assert "EFFETTIVO" in actual_badge
    assert "PREVISTO" not in actual_badge
    assert actual_badge != planned_badge
    assert roster_view.lbl_stato.isVisible()
    assert state in roster_view.lbl_stato.text()


def test_legacy_badge_call_defaults_to_planned_even_in_history(
    roster_view: ViewScadenzario,
) -> None:
    roster_view.aggiorna_badge_modalita("STORICO", "CONVALIDATO")

    assert "STORICO" in roster_view.lbl_modalita.text()
    assert "PREVISTO" in roster_view.lbl_modalita.text()
    assert roster_view.lbl_stato.isVisible()
    assert "CONVALIDATO" in roster_view.lbl_stato.text()
