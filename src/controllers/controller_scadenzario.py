import calendar
import datetime
from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog
from PySide6.QtCore import Qt

from src.calendar_presentation import (
    GUARD_TEXT_COLORS,
    ROLE_CELL_COLORS,
    month_dates,
    month_weeks,
    resolve_resident_name,
    row_display_label,
)
from src.error_messages import describe_error
from src.exports.calendar_pdf import CalendarPdfDocument, CalendarPdfRow, write_calendar_pdf
from src.roster_assignment import (
    GUARD_TYPE_ROLE,
    WARD_ROUND_ROLE,
    assignment_context,
    busy_residents_for_day,
    busy_residents_for_week,
    resident_options,
)
from src.roster_month import GUARD_ROLE, ROLE_KEYS, RosterMonth, load_roster_month, resident_rows
from src.views.components import messages
from src.views.dialog_assegnazione_turno import DialogAssegnazioneSpecializzando, DialogTipoGuardia
from src.views.dialog_mese_anno import DialogMeseAnno


_SEZIONE = "scadenzario"
_RUOLI_SALA = ("Sala Op. I", "Sala Op. II")
"""Ruoli obbligatori in ogni giorno feriale: senza di essi il mese non si convalida."""

_PDF_GUARD_NOTE = "118 = Emergenza territoriale · PI = Pronto Intervento · L = Liscia (routinaria)"


def build_scadenzario_pdf_document(
    roster: RosterMonth,
    dates: tuple[datetime.date, ...],
    residents: list[dict],
) -> CalendarPdfDocument:
    """Prepara il PDF dello scadenzario a partire dal mese caricato.

    Nel mese gli specializzandi compaiono come ``Cognome N.`` (il PDF li abbrevia al
    cognome se serve), nella settimana con il nome completo.
    """

    if not dates:
        raise ValueError("Serve almeno una data da esportare.")
    monthly = len(dates) > 7
    weekday_labels = ("Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom")
    columns = tuple(f"{day.day} {weekday_labels[day.weekday()]}" for day in dates)
    rows: list[CalendarPdfRow] = []
    for role in ROLE_KEYS:
        values: list[str] = []
        for day in dates:
            value = roster.value(day, role) if RosterMonth.is_workday(day) else "-"
            if role != GUARD_ROLE and value and value != "-" and not monthly:
                value = resolve_resident_name(value, residents)
            values.append(value or "-")
        rows.append(
            CalendarPdfRow(
                label=row_display_label(role),
                values=tuple(values),
                background=ROLE_CELL_COLORS[role],
                value_colors=GUARD_TEXT_COLORS if role == GUARD_ROLE else {},
            )
        )

    period = f"{dates[0]:%d/%m/%Y} - {dates[-1]:%d/%m/%Y}"
    return CalendarPdfDocument(
        title="Scadenzario mensile" if monthly else "Scadenzario settimanale",
        period=period,
        column_headers=columns,
        rows=tuple(rows),
        footnote=_PDF_GUARD_NOTE,
        rest_columns=frozenset(index for index, day in enumerate(dates) if day.weekday() >= 5),
        stacked_names=monthly,
    )


def _missing_operating_room_assignments(data: dict, year: int, month: int) -> list[str]:
    """Return weekday dates missing either operating-room specialist assignment."""

    _, days_in_month = calendar.monthrange(year, month)
    missing: list[str] = []
    for day_number in range(1, days_in_month + 1):
        day = datetime.date(year, month, day_number)
        if day.weekday() >= 5:
            continue
        daily = data.get("turni", {}).get(day.isoformat(), {})
        missing_fields = [
            field
            for field in _RUOLI_SALA
            if not isinstance(daily.get(field), str) or not daily[field].strip()
        ]
        if missing_fields:
            missing.append(f"{day.isoformat()}: {', '.join(missing_fields)}")
    return missing


def _duplicate_operating_room_assignments(data: dict, year: int, month: int) -> list[str]:
    """Return weekdays where one specialist is assigned to both physical rooms."""

    _, days_in_month = calendar.monthrange(year, month)
    duplicates: list[str] = []
    for day_number in range(1, days_in_month + 1):
        day = datetime.date(year, month, day_number)
        if day.weekday() >= 5:
            continue
        daily = data.get("turni", {}).get(day.isoformat(), {})
        first = daily.get("Sala Op. I")
        second = daily.get("Sala Op. II")
        if (
            isinstance(first, str)
            and isinstance(second, str)
            and first.strip()
            and first.strip().casefold() == second.strip().casefold()
        ):
            duplicates.append(day.isoformat())
    return duplicates


class ControllerScadenzario:
    def __init__(self, view, model, model_sale_operatorie=None):
        self.view = view
        self.model = model
        self.model_sale_op = model_sale_operatorie
        self.modalita_corrente = None

        self.mesi_ita = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                         "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
        self.giorni_ita = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]

        self.oggi = datetime.date.today()
        self.real_anno = self.oggi.year
        self.real_mese = self.oggi.month

        self.anno_corrente = self.real_anno
        self.mese_corrente = self.real_mese

        self.view.btn_storico.clicked.connect(lambda: self.apri_calendario("STORICO"))
        self.view.btn_corrente.clicked.connect(lambda: self.apri_calendario("CORRENTE"))
        self.view.btn_pianificazione.clicked.connect(lambda: self.apri_calendario("PIANIFICAZIONE"))
        self.view.btn_indietro.clicked.connect(self.torna_alla_dashboard)

        self.view.btn_convalida.clicked.connect(self.convalida_mese)

        self.view.btn_prev.clicked.connect(self.mese_precedente)
        self.view.btn_next.clicked.connect(self.mese_successivo)
        self.view.btn_mese_anno.clicked.connect(self.scegli_mese_anno)
        self.view.btn_esporta_pdf.clicked.connect(self.esporta_pdf)
        self.view.btn_vista_dettaglio.clicked.connect(
            lambda: self.imposta_vista_compatta(False)
        )
        self.view.btn_vista_mese.clicked.connect(
            lambda: self.imposta_vista_compatta(True)
        )

        self.view.btn_per_attivita.clicked.connect(
            lambda: self.view.mostra_vista_specializzandi(False)
        )
        self.view.btn_per_specializzando.clicked.connect(
            lambda: self.view.mostra_vista_specializzandi(True)
        )
        self.view.tabella.clicked.connect(
            lambda index: self._gestisci_click_cella(index.row(), index.column())
        )

        self.roster = None
        self.aggiorna_tabella()

    def get_max_history_date(self):
        """
        Calcola dinamicamente fino a che mese si può spingere lo Storico.
        Se il mese corrente è già CONVALIDATO, rientra nello storico.
        Altrimenti, lo storico si ferma rigorosamente al mese precedente.
        """
        if self.model.get_stato_mese(self.real_anno, self.real_mese) == "CONVALIDATO":
            return datetime.date(self.real_anno, self.real_mese, 1)
        else:
            if self.real_mese == 1:
                return datetime.date(self.real_anno - 1, 12, 1)
            else:
                return datetime.date(self.real_anno, self.real_mese - 1, 1)

    def convalida_mese(self):
        month_data = self.model.load_mese(self.anno_corrente, self.mese_corrente)
        missing = _missing_operating_room_assignments(
            month_data,
            self.anno_corrente,
            self.mese_corrente,
        )
        if missing:
            preview = "\n".join(f"• {item}" for item in missing[:8])
            remaining = len(missing) - 8
            if remaining > 0:
                preview += f"\n• ...e altri {remaining} giorni"
            messages.show_message(
                self.view,
                "Scadenzario incompleto",
                "Prima della convalida assegna Sala Op. I e Sala Op. II "
                "a tutti i giorni lavorativi.\n\n" + preview,
                section=_SEZIONE,
                kind="warning",
            )
            return

        duplicates = _duplicate_operating_room_assignments(
            month_data,
            self.anno_corrente,
            self.mese_corrente,
        )
        if duplicates:
            preview = "\n".join(f"• {item}" for item in duplicates[:8])
            remaining = len(duplicates) - 8
            if remaining > 0:
                preview += f"\n• ...e altri {remaining} giorni"
            messages.show_message(
                self.view,
                "Assegnazione sale non valida",
                "Lo stesso specializzando non può coprire contemporaneamente "
                "Sala Op. I e Sala Op. II.\n\n" + preview,
                section=_SEZIONE,
                kind="warning",
            )
            return

        if messages.ask_confirmation(
            self.view,
            "Conferma Convalida",
            "Vuoi convalidare in via definitiva questo mese?\n\nUna volta convalidato, il mese passerà allo Storico e non sarà più modificabile.",
            section=_SEZIONE,
            confirm_text="Convalida",
        ):
            self.model.set_stato_mese(self.anno_corrente, self.mese_corrente, "CONVALIDATO")
            self.aggiorna_tabella()

    def apri_calendario(self, modalita):
        if modalita == "STORICO":
            max_history_date = self.get_max_history_date()

            mesi_disp = self.model.get_mesi_disponibili()
            storici_validi = [(a, m) for a, m in mesi_disp if datetime.date(a, m, 1) <= max_history_date]

            if not storici_validi:
                messages.show_message(
                    self.view,
                    "Nessuno storico",
                    "Non sono presenti dati di mesi passati o convalidati salvati nel sistema.",
                    section=_SEZIONE,
                )
                return
            else:
                self.anno_corrente, self.mese_corrente = storici_validi[-1]

        elif modalita == "CORRENTE":
            self.anno_corrente = self.real_anno
            self.mese_corrente = self.real_mese

        elif modalita == "PIANIFICAZIONE":
            if self.real_mese == 12:
                self.anno_corrente = self.real_anno + 1
                self.mese_corrente = 1
            else:
                self.anno_corrente = self.real_anno
                self.mese_corrente = self.real_mese + 1

        self.modalita_corrente = modalita
        self.view.stacked_widget.setCurrentIndex(1)
        self.aggiorna_tabella()

    def gestisci_navigazione(self):
        view_date = datetime.date(self.anno_corrente, self.mese_corrente, 1)
        real_date = datetime.date(self.real_anno, self.real_mese, 1)

        self.view.btn_prev.setVisible(True)
        self.view.btn_next.setVisible(True)
        self.view.btn_mese_anno.setEnabled(True)

        if self.modalita_corrente == "CORRENTE":
            self.view.btn_prev.setVisible(False)
            self.view.btn_next.setVisible(False)
            self.view.btn_mese_anno.setEnabled(False)

        elif self.modalita_corrente == "PIANIFICAZIONE":
            if self.real_mese == 12:
                min_plan_date = datetime.date(self.real_anno + 1, 1, 1)
            else:
                min_plan_date = datetime.date(self.real_anno, self.real_mese + 1, 1)
            if view_date <= min_plan_date:
                self.view.btn_prev.setVisible(False)

        elif self.modalita_corrente == "STORICO":
            max_history_date = self.get_max_history_date()

            if view_date >= max_history_date:
                self.view.btn_next.setVisible(False)

            mesi_disp = self.model.get_mesi_disponibili()
            storici_validi = [(a, m) for a, m in mesi_disp if datetime.date(a, m, 1) <= max_history_date]

            if storici_validi:
                min_y, min_m = storici_validi[0]
                min_history_date = datetime.date(min_y, min_m, 1)
                if view_date <= min_history_date:
                    self.view.btn_prev.setVisible(False)
            else:
                self.view.btn_prev.setVisible(False)

    def torna_alla_dashboard(self):
        self.modalita_corrente = None
        self.view.stacked_widget.setCurrentIndex(0)

    def imposta_vista_compatta(self, compact: bool) -> None:
        """Attiva o disattiva la vista mensile compatta."""

        self.view.set_compact_mode(compact)
        self.aggiorna_tabella()

    def _cella_modificabile(self, row: int, column: int) -> bool:
        if row < 1 or column < 0 or self.modalita_corrente not in ("CORRENTE", "PIANIFICAZIONE"):
            return False
        if self.model.get_stato_mese(self.anno_corrente, self.mese_corrente) == "CONVALIDATO":
            return False
        day = datetime.date(self.anno_corrente, self.mese_corrente, column + 1)
        return day.weekday() < 5

    def _gestisci_click_cella(self, row: int, column: int) -> None:
        self._mostra_nome_completo(row, column)
        if self._cella_modificabile(row, column):
            self._apri_modal_assegnazione(row, column)

    def _specializzandi_occupati(self, day: datetime.date, role: str) -> dict[str, str]:
        """Specializzandi già impegnati nel giorno (o nella settimana del giro visite)."""

        monday = day - datetime.timedelta(days=day.weekday())
        if role == WARD_ROUND_ROLE:
            week = [monday + datetime.timedelta(days=offset) for offset in range(5)]
            return busy_residents_for_week({
                weekday: self.model.load_mese(weekday.year, weekday.month)
                .get("turni", {})
                .get(weekday.isoformat(), {})
                for weekday in week
            })
        daily = (
            self.model.load_mese(day.year, day.month).get("turni", {}).get(day.isoformat(), {})
        )
        ward_round = self.model.get_giro_visite_settimana(
            monday.isoformat(), day.year, day.month
        )
        return busy_residents_for_day(daily, role, ward_round)

    def _apri_modal_assegnazione(self, row: int, column: int) -> None:
        """Apre il dialog della cella e passa la scelta ad ``assegna``."""

        modello = self.view.modello_attivita
        day = modello.date_at(column)
        role = self.view.row_labels[row]
        current = modello.value_at(row, column)
        context = assignment_context(day, role)

        if role == GUARD_TYPE_ROLE:
            dialog = DialogTipoGuardia(context, current, self.view)
        else:
            options = resident_options(
                self.model.specializzandi,
                self._specializzandi_occupati(day, role),
                current,
            )
            dialog = DialogAssegnazioneSpecializzando(options, context, current, self.view)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        nuovo_valore = dialog.selected_value()
        if nuovo_valore != current:
            self.assegna(row, column, nuovo_valore)

    def _mostra_nome_completo(self, row: int, column: int) -> None:
        if not self.view._compact or row < 2 or column < 0:
            return
        value = self.view.modello_attivita.value_at(row, column)
        full_name = self.model.get_nome_completo_specializzando(value) if value else ""
        day = datetime.date(self.anno_corrente, self.mese_corrente, column + 1)
        self.view.mostra_dettaglio_assegnazione(
            day.strftime("%d/%m/%Y"),
            self.view.row_labels[row],
            full_name,
        )

    def esporta_pdf(self) -> None:
        """Esporta il mese o una settimana in PDF."""

        weeks = month_weeks(self.anno_corrente, self.mese_corrente)
        choices = ["Mese intero"] + [
            f"Settimana {index}: {week[0].strftime('%d/%m')} - {week[-1].strftime('%d/%m')}"
            for index, week in enumerate(weeks, 1)
        ]
        choice = messages.choose_option(
            self.view,
            "Esporta scadenzario",
            "Intervallo da esportare:",
            choices,
            section=_SEZIONE,
        )
        if choice is None:
            return
        if choice == choices[0]:
            dates = month_dates(self.anno_corrente, self.mese_corrente)
            scope = "mese"
        else:
            week_index = choices.index(choice) - 1
            dates = weeks[week_index]
            scope = f"settimana-{week_index + 1}"

        suggested = f"scadenzario-{self.anno_corrente:04d}-{self.mese_corrente:02d}-{scope}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self.view,
            "Salva calendario PDF",
            str(Path.home() / suggested),
            "Documento PDF (*.pdf)",
        )
        if not path:
            return
        try:
            document = build_scadenzario_pdf_document(
                self.roster, dates, self.model.specializzandi
            )
            output_path = write_calendar_pdf(path, document)
        except (OSError, ValueError, RuntimeError) as error:
            messages.show_message(
                self.view,
                "Esportazione non riuscita",
                f"Impossibile creare il PDF:\n{describe_error(error)}",
                section=_SEZIONE,
                kind="error",
            )
            return
        messages.show_message(
            self.view,
            "PDF creato",
            f"Calendario esportato in:\n{output_path}",
            section=_SEZIONE,
        )

    def aggiorna_tabella(self):
        self.gestisci_navigazione()

        stato_json = self.model.get_stato_mese(self.anno_corrente, self.mese_corrente)
        if self.modalita_corrente == "STORICO":
            self.view.btn_convalida.setVisible(False)
        elif self.modalita_corrente in ("PIANIFICAZIONE", "CORRENTE"):
            self.view.btn_convalida.setVisible(stato_json != "CONVALIDATO")

        self.view.aggiorna_badge_modalita(self.modalita_corrente, stato_json)
        nome_mese = self.mesi_ita[self.mese_corrente - 1].upper()
        self.view.btn_mese_anno.setText(f"{nome_mese} {self.anno_corrente}")

        self.roster = load_roster_month(self.model, self.anno_corrente, self.mese_corrente)
        modello = self.view.modello_attivita
        oggi = datetime.date.today()
        modello.set_roster(self.roster, self.model.specializzandi)
        modello.set_today(oggi)
        self.view.modello_specializzandi.set_rows(
            self.roster, resident_rows(self.roster, self.model.specializzandi)
        )
        self.view.modello_specializzandi.set_today(oggi)

    def assegna(self, riga: int, colonna: int, nuovo_valore: str) -> None:
        """Assegna ``nuovo_valore`` alla cella (riga = ruolo, colonna = giorno) e ricarica il mese.

        Applica le regole dell'inserimento manuale: mese non convalidato e non storico,
        giorno feriale, nessun altro incarico nella giornata, giro visite valido per tutta
        la settimana (con conferma se sostituisce o rimuove un'assegnazione).
        """

        if riga == 0 or self.modalita_corrente == "STORICO":
            return
        if self.model.get_stato_mese(self.anno_corrente, self.mese_corrente) == "CONVALIDATO":
            return
        data_corrente = datetime.date(self.anno_corrente, self.mese_corrente, colonna + 1)
        if data_corrente.weekday() >= 5:
            return
        data_str = data_corrente.isoformat()
        nome_riga = self.view.row_labels[riga]
        nuovo_valore = nuovo_valore.strip()
        if nuovo_valore == "-":
            nuovo_valore = ""

        if nome_riga == "Giro Visite":
            lun_date = data_corrente - datetime.timedelta(days=data_corrente.weekday())
            lun_str = lun_date.isoformat()
            previous = self.model.get_giro_visite_settimana(
                lun_str, self.anno_corrente, self.mese_corrente
            )
            if previous == nuovo_valore:
                return
            try:
                self.model.valida_giro_visite_settimana(lun_str, nuovo_valore)
            except ValueError as error:
                messages.show_message(
                    self.view,
                    "Giro visite non modificabile",
                    str(error),
                    section=_SEZIONE,
                    kind="warning",
                )
                return
            if previous:
                friday = lun_date + datetime.timedelta(days=4)
                action = "Sostituire l'assegnazione" if nuovo_valore else "Rimuovere l'assegnazione"
                if not messages.ask_confirmation(
                    self.view,
                    "Modifica giro visite",
                    f"{action} per tutta la settimana dal {lun_date:%d/%m} al {friday:%d/%m}?",
                    section=_SEZIONE,
                    confirm_text="Sostituisci" if nuovo_valore else "Rimuovi",
                    destructive=True,
                ):
                    return
            self.model.set_giro_visite_settimana(
                lun_str, self.anno_corrente, self.mese_corrente, nuovo_valore
            )
            self.aggiorna_tabella()
            return

        if nuovo_valore and nome_riga != "Tipo Guardia":
            monday = data_corrente - datetime.timedelta(days=data_corrente.weekday())
            used = [
                self.model.get_giro_visite_settimana(
                    monday.isoformat(), self.anno_corrente, self.mese_corrente
                )
            ] + [
                self.model.get_valore_cella(data_str, role)
                for role in self.view.row_labels[2:]
                if role not in (nome_riga, "Giro Visite")
            ]
            if nuovo_valore.casefold() in {value.strip().casefold() for value in used}:
                messages.show_message(
                    self.view,
                    "Assegnazione non valida",
                    "Lo specializzando ha già un altro incarico in questa giornata.",
                    section=_SEZIONE,
                    kind="warning",
                )
                return

        self.model.set_valore_cella(data_str, nome_riga, nuovo_valore)
        if nome_riga in _RUOLI_SALA and self.model_sale_op is not None:
            or1 = self.model.get_valore_cella(data_str, "Sala Op. I")
            or2 = self.model.get_valore_cella(data_str, "Sala Op. II")
            self.model_sale_op.set_specializzandi(data_str, or1, or2)
        self.aggiorna_tabella()

    def mese_precedente(self):
        if self.mese_corrente == 1:
            self.mese_corrente = 12
            self.anno_corrente -= 1
        else:
            self.mese_corrente -= 1
        self.aggiorna_tabella()

    def mese_successivo(self):
        if self.mese_corrente == 12:
            self.mese_corrente = 1
            self.anno_corrente += 1
        else:
            self.mese_corrente += 1
        self.aggiorna_tabella()

    def scegli_mese_anno(self):
        dialog = DialogMeseAnno(self.mesi_ita, self.mese_corrente, self.anno_corrente, self.view)
        if not dialog.exec():
            return

        selected_mese, selected_anno = dialog.get_selezione()
        selected_date = datetime.date(selected_anno, selected_mese, 1)
        real_date = datetime.date(self.real_anno, self.real_mese, 1)

        if self.modalita_corrente == "PIANIFICAZIONE" and selected_date <= real_date:
            if self.real_mese == 12:
                self.anno_corrente = self.real_anno + 1
                self.mese_corrente = 1
            else:
                self.anno_corrente = self.real_anno
                self.mese_corrente = self.real_mese + 1

        elif self.modalita_corrente == "STORICO":
            max_history_date = self.get_max_history_date()

            mesi_disp = self.model.get_mesi_disponibili()
            storici_validi = [(a, m) for a, m in mesi_disp if datetime.date(a, m, 1) <= max_history_date]

            if not storici_validi:
                self.mese_corrente = max_history_date.month
                self.anno_corrente = max_history_date.year
            else:
                min_y, min_m = storici_validi[0]
                min_history_date = datetime.date(min_y, min_m, 1)

                if selected_date > max_history_date:
                    self.mese_corrente = max_history_date.month
                    self.anno_corrente = max_history_date.year
                elif selected_date < min_history_date:
                    self.mese_corrente = min_m
                    self.anno_corrente = min_y
                else:
                    self.mese_corrente = selected_mese
                    self.anno_corrente = selected_anno
        else:
            self.mese_corrente = selected_mese
            self.anno_corrente = selected_anno

        self.aggiorna_tabella()
