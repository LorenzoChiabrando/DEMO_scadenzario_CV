import calendar
import datetime
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QTableWidget
from PySide6.QtCore import Qt

from src.calendar_presentation import (
    month_dates,
    month_weeks,
    person_initials,
    resident_legend,
    resolve_resident_name,
    row_display_label,
)
from src.exports.calendar_pdf import CalendarPdfDocument, CalendarPdfRow, write_calendar_pdf
from src.views.components.combo_delegate import ComboBoxDelegate, SmartComboBoxDelegate
from src.views.dialog_mese_anno import DialogMeseAnno


_PDF_ROW_COLORS = {
    "Tipo Guardia": "#e0e7ff",
    "Reparto I": "#e0e7ff",
    "Reparto II": "#e0e7ff",
    "Sala Op. I": "#dcfce7",
    "Sala Op. II": "#dcfce7",
    "Giro Visite": "#fef9c3",
    "Day Hospital": "#fae8ff",
    "Day Surgery": "#fae8ff",
}


def build_scadenzario_pdf_document(
    model,
    dates: tuple[datetime.date, ...],
    row_keys: list[str],
    residents: list[dict],
) -> CalendarPdfDocument:
    """Prepara i dati dello scadenziario per il PDF."""

    if not dates:
        raise ValueError("at least one date is required")
    compact = len(dates) > 7
    weekday_labels = ("Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom")
    columns = tuple(
        f"{day.day} {weekday_labels[day.weekday()][:1]}"
        if compact
        else f"{day.day} {weekday_labels[day.weekday()]}"
        for day in dates
    )
    rows: list[CalendarPdfRow] = []
    for row_key in row_keys:
        if row_key == "Giorno":
            continue
        values: list[str] = []
        for day in dates:
            if day.weekday() >= 5:
                value = "-"
            elif row_key == "Giro Visite":
                monday = day - datetime.timedelta(days=day.weekday())
                value = model.get_giro_visite_settimana(
                    monday.isoformat(), day.year, day.month
                )
            else:
                value = model.get_valore_cella(day.isoformat(), row_key)
            if row_key != "Tipo Guardia" and value and value != "-":
                value = (
                    person_initials(value)
                    if compact
                    else resolve_resident_name(value, residents)
                )
            values.append(value or "-")
        rows.append(
            CalendarPdfRow(
                label=row_display_label(row_key),
                values=tuple(values),
                background=_PDF_ROW_COLORS.get(row_key, "#ffffff"),
            )
        )

    period = (
        f"{dates[0].strftime('%d/%m/%Y')} - {dates[-1].strftime('%d/%m/%Y')}"
    )
    legend = tuple(resident_legend(residents).items()) if compact else ()
    return CalendarPdfDocument(
        title="Scadenziario mensile",
        period=period,
        column_headers=columns,
        rows=tuple(rows),
        legend=legend,
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
            for field in ("Sala Op. I", "Sala Op. II")
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

        self.setup_delegates()

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

        self.view.tabella.cellChanged.connect(self.salva_modifica_cella)
        self.view.tabella.cellClicked.connect(self._mostra_nome_completo)

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
            QMessageBox.warning(
                self.view,
                "Scadenzario incompleto",
                "Prima della convalida assegna Sala Op. I e Sala Op. II "
                "a tutti i giorni lavorativi.\n\n" + preview,
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
            QMessageBox.warning(
                self.view,
                "Assegnazione sale non valida",
                "Lo stesso specializzando non può coprire contemporaneamente "
                "Sala Op. I e Sala Op. II.\n\n" + preview,
            )
            return

        risposta = QMessageBox.question(
            self.view,
            "Conferma Convalida",
            "Vuoi convalidare in via definitiva questo mese?\n\nUna volta convalidato, il mese passerà allo Storico e non sarà più modificabile.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if risposta == QMessageBox.StandardButton.Yes:
            self.model.set_stato_mese(self.anno_corrente, self.mese_corrente, "CONVALIDATO")
            self.aggiorna_tabella()

    def apri_calendario(self, modalita):
        if modalita == "STORICO":
            max_history_date = self.get_max_history_date()

            mesi_disp = self.model.get_mesi_disponibili()
            storici_validi = [(a, m) for a, m in mesi_disp if datetime.date(a, m, 1) <= max_history_date]

            if not storici_validi:
                QMessageBox.information(
                    self.view,
                    "Nessuno storico",
                    "Non sono presenti dati di mesi passati o convalidati salvati nel sistema."
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

    def setup_delegates(self):
        tipi_guardia = ["118", "PI", "L"]
        delegate_tipo = ComboBoxDelegate(tipi_guardia, self.view.tabella)
        self.view.tabella.setItemDelegateForRow(1, delegate_tipo)

        specializzandi_attivi = self.model.get_specializzandi_attivi()
        delegate_spec = SmartComboBoxDelegate(specializzandi_attivi, self.view.tabella)
        self.delegate_specializzandi = delegate_spec

        for riga in range(2, len(self.view.row_labels)):
            self.view.tabella.setItemDelegateForRow(riga, delegate_spec)

    def imposta_vista_compatta(self, compact: bool) -> None:
        """Attiva o disattiva la vista mensile compatta."""

        self.delegate_specializzandi.set_compact(compact)
        self.view.set_compact_mode(compact)
        self.aggiorna_tabella()

    def _item_effettivo(self, row: int, column: int):
        item = self.view.tabella.item(row, column)
        if item is not None:
            return item
        for candidate in range(column - 1, -1, -1):
            if self.view.tabella.columnSpan(row, candidate) + candidate > column:
                return self.view.tabella.item(row, candidate)
        return None

    def _mostra_nome_completo(self, row: int, column: int) -> None:
        if not self.view._compact or row < 2 or column < 0:
            return
        item = self._item_effettivo(row, column)
        value = item.text().strip() if item else ""
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
        choice, accepted = QInputDialog.getItem(
            self.view,
            "Esporta scadenzario",
            "Intervallo da esportare:",
            choices,
            0,
            False,
        )
        if not accepted:
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
                self.model,
                dates,
                self.view.row_labels,
                self.model.specializzandi,
            )
            output_path = write_calendar_pdf(path, document)
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.critical(
                self.view,
                "Esportazione non riuscita",
                f"Impossibile creare il PDF:\n{error}",
            )
            return
        QMessageBox.information(
            self.view,
            "PDF creato",
            f"Calendario esportato in:\n{output_path}",
        )

    def aggiorna_tabella(self):
        self.view.tabella.blockSignals(True)

        self.gestisci_navigazione()

        stato_json = self.model.get_stato_mese(self.anno_corrente, self.mese_corrente)

        if self.modalita_corrente == "STORICO":
            self.view.tabella.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            self.view.btn_convalida.setVisible(False)

        elif self.modalita_corrente == "PIANIFICAZIONE":
            if stato_json == "CONVALIDATO":
                self.view.tabella.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            else:
                self.view.tabella.setEditTriggers(QTableWidget.EditTrigger.AllEditTriggers)
            self.view.btn_convalida.setVisible(stato_json != "CONVALIDATO")

        elif self.modalita_corrente == "CORRENTE":
            if stato_json == "CONVALIDATO":
                self.view.tabella.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            else:
                self.view.tabella.setEditTriggers(QTableWidget.EditTrigger.AllEditTriggers)
            self.view.btn_convalida.setVisible(stato_json != "CONVALIDATO")

        self.view.aggiorna_badge_modalita(self.modalita_corrente, stato_json)

        nome_mese = self.mesi_ita[self.mese_corrente - 1].upper()
        self.view.btn_mese_anno.setText(f"{nome_mese} {self.anno_corrente}")

        _, num_giorni = calendar.monthrange(self.anno_corrente, self.mese_corrente)

        self.view.tabella.setColumnCount(num_giorni)
        self.view.tabella.setHorizontalHeaderLabels([str(i) for i in range(1, num_giorni + 1)])

        oggi = datetime.date.today()

        # Qt segnala un warning se si rimuove uno span inesistente.
        riga_gv = self.view.row_labels.index("Giro Visite")
        for col in range(num_giorni):
            if self.view.tabella.columnSpan(riga_gv, col) > 1:
                self.view.tabella.setSpan(riga_gv, col, 1, 1)

        for giorno in range(1, num_giorni + 1):
            data_corrente = datetime.date(self.anno_corrente, self.mese_corrente, giorno)
            data_str = data_corrente.strftime("%Y-%m-%d")

            giorno_settimana = data_corrente.weekday()
            is_festivo = giorno_settimana in (5, 6)
            is_oggi = (data_corrente == oggi)
            nome_giorno = self.giorni_ita[giorno_settimana].upper()

            self.view.tabella.setItem(0, giorno - 1, self.view.crea_item_giorno(nome_giorno, is_festivo, is_oggi))

            for riga in range(1, len(self.view.row_labels)):
                nome_riga = self.view.row_labels[riga]
                if nome_riga == "Giro Visite":
                    continue  # gestita separatamente con setSpan
                valore = "-" if is_festivo else self.model.get_valore_cella(data_str, nome_riga)
                self.view.tabella.setItem(riga, giorno - 1, self.view.crea_item_cella(valore, is_festivo, nome_riga, is_oggi))

        self._applica_giro_visite(num_giorni, oggi)

        self.view.tabella.blockSignals(False)

    def _applica_giro_visite(self, num_giorni: int, oggi: datetime.date):
        """Applica setSpan per la riga Giro Visite, raggruppando i giorni lun-ven in blocchi settimanali."""
        RIGA_GV = self.view.row_labels.index("Giro Visite")
        col = 0
        while col < num_giorni:
            data_corrente = datetime.date(self.anno_corrente, self.mese_corrente, col + 1)
            wd = data_corrente.weekday()

            if wd >= 5:  # sabato/domenica
                item = self.view.crea_item_cella("-", True, "Giro Visite", False)
                self.view.tabella.setItem(RIGA_GV, col, item)
                col += 1
                continue

            block_start = col
            while col < num_giorni:
                d = datetime.date(self.anno_corrente, self.mese_corrente, col + 1)
                if d.weekday() >= 5:
                    break
                col += 1
            block_end = col  # esclusivo
            block_len = block_end - block_start

            start_date = datetime.date(self.anno_corrente, self.mese_corrente, block_start + 1)
            lun_date = start_date - datetime.timedelta(days=start_date.weekday())
            lun_str = lun_date.strftime("%Y-%m-%d")

            valore = self.model.get_giro_visite_settimana(lun_str, self.anno_corrente, self.mese_corrente)

            is_oggi_block = any(
                datetime.date(self.anno_corrente, self.mese_corrente, c + 1) == oggi
                for c in range(block_start, block_end)
            )

            if block_len > 1:
                self.view.tabella.setSpan(RIGA_GV, block_start, 1, block_len)
            item = self.view.crea_item_cella(valore, False, "Giro Visite", is_oggi_block)
            self.view.tabella.setItem(RIGA_GV, block_start, item)

    def salva_modifica_cella(self, riga, colonna):
        if riga == 0 or self.modalita_corrente == "STORICO":
            return

        if self.model.get_stato_mese(self.anno_corrente, self.mese_corrente) == "CONVALIDATO":
            return

        giorno = colonna + 1
        data_corrente = datetime.date(self.anno_corrente, self.mese_corrente, giorno)
        data_str = data_corrente.strftime("%Y-%m-%d")

        nome_riga = self.view.row_labels[riga]
        item = self.view.tabella.item(riga, colonna)
        nuovo_valore = item.text() if item else ""

        if nome_riga == "Giro Visite":
            lun_date = data_corrente - datetime.timedelta(days=data_corrente.weekday())
            lun_str = lun_date.strftime("%Y-%m-%d")
            self.model.set_giro_visite_settimana(lun_str, self.anno_corrente, self.mese_corrente, nuovo_valore)
            is_oggi = (data_corrente == datetime.date.today())
            self.view.aggiorna_stile_cella(riga, colonna, nuovo_valore, nome_riga, False, is_oggi)
            return

        self.model.set_valore_cella(data_str, nome_riga, nuovo_valore)

        if nome_riga in ("Sala Op. I", "Sala Op. II") and self.model_sale_op is not None:
            or1 = self.model.get_valore_cella(data_str, "Sala Op. I")
            or2 = self.model.get_valore_cella(data_str, "Sala Op. II")
            self.model_sale_op.set_specializzandi(data_str, or1, or2)

        is_festivo = data_corrente.weekday() in (5, 6)
        is_oggi = (data_corrente == datetime.date.today())
        self.view.aggiorna_stile_cella(riga, colonna, nuovo_valore, nome_riga, is_festivo, is_oggi)

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
