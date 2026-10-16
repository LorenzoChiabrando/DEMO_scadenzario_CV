from __future__ import annotations

import calendar
import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QComboBox,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QTableWidget,
)

from src.calendar_presentation import (
    month_dates,
    month_weeks,
    person_initials,
    resident_legend,
    resolve_resident_name,
    row_display_label,
)
from src.calendar_versions import CalendarVersion
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
    *,
    version: CalendarVersion = CalendarVersion.PREVISTO,
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
        title=f"Scadenziario mensile · {CalendarVersion(version).value.capitalize()}",
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
        self.versione_corrente = CalendarVersion.PREVISTO
        self._model_previsto = model.for_version(CalendarVersion.PREVISTO)
        self._model_effettivo = model.for_version(CalendarVersion.EFFETTIVO)
        self.model = self._model_previsto
        self._model_sale_base = model_sale_operatorie
        self.model_sale_op = (
            model_sale_operatorie.for_version(self.versione_corrente)
            if model_sale_operatorie is not None else None
        )
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
        self.view.btn_crea_effettivo.clicked.connect(self.crea_effettivo_mese)
        self.view.combo_versione.currentIndexChanged.connect(self.cambia_versione)

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

    def cambia_versione(self, _index: int) -> None:
        """Switch bound managers without changing period, zoom or persisted data."""
        version = CalendarVersion(self.view.combo_versione.currentData())
        if version == self.versione_corrente:
            return
        # Discard an uncommitted editor before it can write into another version.
        for editor in self.view.tabella.viewport().findChildren(QComboBox):
            self.view.tabella.closeEditor(
                editor, QAbstractItemDelegate.EndEditHint.RevertModelCache
            )
        self.versione_corrente = version
        self.model = (
            self._model_previsto if version == CalendarVersion.PREVISTO
            else self._model_effettivo
        )
        if self._model_sale_base is not None:
            self.model_sale_op = self._model_sale_base.for_version(version)
        self.view.lbl_dettaglio_cella.setText("")
        self.aggiorna_tabella()

    def _effettivo_assente(self) -> bool:
        return (
            self.versione_corrente == CalendarVersion.EFFETTIVO
            and not self.model.has_mese(self.anno_corrente, self.mese_corrente)
        )

    def _puo_modificare(self) -> bool:
        if self._effettivo_assente():
            return False
        if self.model.get_stato_mese(self.anno_corrente, self.mese_corrente) == "CONVALIDATO":
            return False
        return not (
            self.modalita_corrente == "STORICO"
            and self.versione_corrente == CalendarVersion.PREVISTO
        )

    def _mesi_disponibili(self) -> list[tuple[int, int]]:
        return sorted(set(self._model_previsto.get_mesi_disponibili())
                      | set(self._model_effettivo.get_mesi_disponibili()))

    def _conflitto_assegnazioni_interventi(self, data_str: str, riga: str, valore: str) -> bool:
        """Reject ambiguous actual roster changes while operation assignments differ."""
        room_id, role = {
            "Sala Op. I": ("OR-1", "OR I"),
            "Sala Op. II": ("OR-2", "OR II"),
        }[riga]
        for operation in self.model_sale_op.get_operazioni(data_str):
            operation_room = operation.get("sala_operatoria")
            if operation_room and operation_room != room_id:
                continue
            operation_role = operation.get("ruolo_specializzando")
            if not operation_room and operation_role and operation_role != role:
                continue
            assigned = any(key in operation for key in (
                "id_specializzando", "specializzando", "ruolo_specializzando",
            ))
            specialist = operation.get("specializzando", "").strip().casefold()
            if assigned and specialist != valore.casefold():
                return True
        return False

    def crea_effettivo_mese(self) -> None:
        """Explicitly initialize a missing actual month from a confirmed planned month."""
        if not self._effettivo_assente():
            return
        answer = QMessageBox.question(
            self.view,
            "Crea calendario Effettivo",
            f"Creare l'Effettivo di {self.mese_corrente:02d}/{self.anno_corrente} "
            "dal Previsto convalidato?\n\nLa copia sarà modificabile separatamente.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._model_previsto.crea_effettivo_mese(self.anno_corrente, self.mese_corrente)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self.view, "Creazione Effettivo non riuscita", str(error))
        self.aggiorna_tabella()

    def get_max_history_date(self):
        """
        Calcola dinamicamente fino a che mese si può spingere lo Storico.
        Se il mese corrente è già CONVALIDATO, rientra nello storico.
        Altrimenti, lo storico si ferma rigorosamente al mese precedente.
        """
        if self._model_previsto.get_stato_mese(self.real_anno, self.real_mese) == "CONVALIDATO":
            return datetime.date(self.real_anno, self.real_mese, 1)
        else:
            if self.real_mese == 1:
                return datetime.date(self.real_anno - 1, 12, 1)
            else:
                return datetime.date(self.real_anno, self.real_mese - 1, 1)

    def convalida_mese(self):
        if not self._puo_modificare():
            return
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
                f"Scadenzario {self.versione_corrente.value.capitalize()} incompleto",
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
                f"Assegnazione sale non valida · {self.versione_corrente.value.capitalize()}",
                "Lo stesso specializzando non può coprire contemporaneamente "
                "Sala Op. I e Sala Op. II.\n\n" + preview,
            )
            return

        planned = self.versione_corrente == CalendarVersion.PREVISTO
        explanation = (
            "Il Previsto non sarà più modificabile. Verrà creata una copia Effettivo "
            "modificabile separatamente."
            if planned else
            "L'Effettivo non sarà più modificabile. Le attività operatorie si "
            "confermano separatamente nelle Sale Operatorie."
        )
        risposta = QMessageBox.question(
            self.view,
            f"Convalida {self.versione_corrente.value.capitalize()}",
            f"Convalidare il mese {self.mese_corrente:02d}/{self.anno_corrente} "
            f"{self.versione_corrente.value.capitalize()}?\n\n{explanation}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if risposta == QMessageBox.StandardButton.Yes:
            try:
                self.model.convalida_mese(self.anno_corrente, self.mese_corrente)
            except (OSError, ValueError) as error:
                QMessageBox.warning(
                    self.view,
                    f"Convalida {self.versione_corrente.value.capitalize()} non riuscita",
                    str(error),
                )
            self.aggiorna_tabella()

    def apri_calendario(self, modalita):
        if modalita == "STORICO":
            max_history_date = self.get_max_history_date()

            mesi_disp = self._mesi_disponibili()
            storici_validi = [(a, m) for a, m in mesi_disp if datetime.date(a, m, 1) <= max_history_date]

            if not storici_validi:
                QMessageBox.information(
                    self.view,
                    f"Nessuno storico · {self.versione_corrente.value.capitalize()}",
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

            mesi_disp = self._mesi_disponibili()
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
            versione=self.versione_corrente.value,
        )

    def esporta_pdf(self) -> None:
        """Esporta il mese o una settimana in PDF."""

        if self._effettivo_assente():
            return
        weeks = month_weeks(self.anno_corrente, self.mese_corrente)
        choices = ["Mese intero"] + [
            f"Settimana {index}: {week[0].strftime('%d/%m')} - {week[-1].strftime('%d/%m')}"
            for index, week in enumerate(weeks, 1)
        ]
        choice, accepted = QInputDialog.getItem(
            self.view,
            f"Esporta scadenzario {self.versione_corrente.value.capitalize()}",
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

        suggested = (
            f"scadenzario-{self.versione_corrente.value}-"
            f"{self.anno_corrente:04d}-{self.mese_corrente:02d}-{scope}.pdf"
        )
        path, _ = QFileDialog.getSaveFileName(
            self.view,
            f"Salva calendario {self.versione_corrente.value.capitalize()} PDF",
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
                version=self.versione_corrente,
            )
            output_path = write_calendar_pdf(path, document)
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.critical(
                self.view,
                f"Esportazione {self.versione_corrente.value.capitalize()} non riuscita",
                f"Impossibile creare il PDF:\n{error}",
            )
            return
        QMessageBox.information(
            self.view,
            f"PDF {self.versione_corrente.value.capitalize()} creato",
            f"Calendario esportato in:\n{output_path}",
        )

    def aggiorna_tabella(self):
        self.view.tabella.blockSignals(True)

        self._model_previsto.invalidate_cache()
        self._model_effettivo.invalidate_cache()
        if self.model_sale_op is not None:
            self.model_sale_op.invalidate_cache()

        self.gestisci_navigazione()

        stato_json = self.model.get_stato_mese(self.anno_corrente, self.mese_corrente)
        absent = self._effettivo_assente()
        can_edit = self._puo_modificare()
        self.view.tabella.setEditTriggers(
            QTableWidget.EditTrigger.AllEditTriggers if can_edit
            else QTableWidget.EditTrigger.NoEditTriggers
        )
        self.view.btn_convalida.setVisible(can_edit)
        self.view.btn_convalida.setText(
            f"CONVALIDA IL MESE {self.versione_corrente.value.upper()}"
        )
        self.view.btn_esporta_pdf.setEnabled(not absent)
        can_create = absent and (
            self._model_previsto.get_stato_mese(self.anno_corrente, self.mese_corrente)
            == "CONVALIDATO"
        )
        self.view.btn_crea_effettivo.setVisible(can_create)
        if absent:
            message = (
                "Effettivo non ancora creato. Puoi copiarlo dal Previsto convalidato."
                if can_create else
                "Effettivo non ancora creato. "
                "Convalida il Previsto per creare la copia modificabile."
            )
        elif stato_json == "CONVALIDATO":
            message = f"{self.versione_corrente.value.capitalize()} convalidato: sola lettura."
        elif self.versione_corrente == CalendarVersion.EFFETTIVO:
            message = "Le correzioni all'Effettivo non modificano il Previsto."
        else:
            message = "La convalida del Previsto crea una copia Effettivo modificabile."
        self.view.lbl_versione_info.setText(message)
        self.view.aggiorna_badge_modalita(
            self.modalita_corrente, "ASSENTE" if absent else stato_json,
            self.versione_corrente.value,
        )

        nome_mese = self.mesi_ita[self.mese_corrente - 1].upper()
        self.view.btn_mese_anno.setText(f"{nome_mese} {self.anno_corrente}")

        _, num_giorni = calendar.monthrange(self.anno_corrente, self.mese_corrente)

        self.view.tabella.setColumnCount(num_giorni)
        self.view.tabella.setHorizontalHeaderLabels([str(i) for i in range(1, num_giorni + 1)])

        oggi = datetime.date.today()

        self.view.tabella.clearSpans()

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
                    continue
                valore = "-" if is_festivo else (
                    "" if absent else self.model.get_valore_cella(data_str, nome_riga)
                )
                self.view.tabella.setItem(riga, giorno - 1, self.view.crea_item_cella(valore, is_festivo, nome_riga, is_oggi))

        self._applica_giro_visite(num_giorni, oggi)

        self.view.tabella.blockSignals(False)

    def _applica_giro_visite(self, num_giorni: int, oggi: datetime.date):
        """Mostra la stessa assegnazione in ogni cella lavorativa della settimana."""
        row = self.view.row_labels.index("Giro Visite")
        for column in range(num_giorni):
            day = datetime.date(self.anno_corrente, self.mese_corrente, column + 1)
            weekend = day.weekday() >= 5
            monday = day - datetime.timedelta(days=day.weekday())
            value = "-" if weekend else (
                "" if self._effettivo_assente() else self.model.get_giro_visite_settimana(
                    monday.isoformat(), day.year, day.month
                )
            )
            item = self.view.crea_item_cella(value, weekend, "Giro Visite", day == oggi)
            self.view.tabella.setItem(row, column, item)

    def salva_modifica_cella(self, riga, colonna):
        if riga == 0 or not self._puo_modificare():
            return

        giorno = colonna + 1
        data_corrente = datetime.date(self.anno_corrente, self.mese_corrente, giorno)
        if data_corrente.weekday() >= 5:
            self.aggiorna_tabella()
            return
        data_str = data_corrente.strftime("%Y-%m-%d")

        nome_riga = self.view.row_labels[riga]
        item = self.view.tabella.item(riga, colonna)
        nuovo_valore = item.text().strip() if item else ""
        if nuovo_valore == "-":
            nuovo_valore = ""

        if nome_riga == "Giro Visite":
            lun_date = data_corrente - datetime.timedelta(days=data_corrente.weekday())
            lun_str = lun_date.strftime("%Y-%m-%d")
            previous = self.model.get_giro_visite_settimana(
                lun_str, self.anno_corrente, self.mese_corrente
            )
            if previous == nuovo_valore:
                return
            try:
                self.model.valida_giro_visite_settimana(lun_str, nuovo_valore)
            except ValueError as error:
                QMessageBox.warning(
                    self.view, f"Giro visite {self.versione_corrente.value} non modificabile",
                    str(error),
                )
                self.aggiorna_tabella()
                return
            if previous:
                friday = lun_date + datetime.timedelta(days=4)
                action = "Sostituire l'assegnazione" if nuovo_valore else "Rimuovere l'assegnazione"
                answer = QMessageBox.question(
                    self.view,
                    f"Modifica giro visite · {self.versione_corrente.value.capitalize()}",
                    f"{action} per tutta la settimana "
                    f"dal {lun_date:%d/%m} al {friday:%d/%m}?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    self.aggiorna_tabella()
                    return
            try:
                self.model.set_giro_visite_settimana(
                    lun_str, self.anno_corrente, self.mese_corrente, nuovo_valore
                )
            except (OSError, ValueError) as error:
                QMessageBox.warning(
                    self.view,
                    f"Giro visite {self.versione_corrente.value} non salvato", str(error),
                )
            self.aggiorna_tabella()
            return

        if nuovo_valore and nome_riga != "Tipo Guardia":
            monday = data_corrente - datetime.timedelta(days=data_corrente.weekday())
            used = [self.model.get_giro_visite_settimana(
                monday.isoformat(), self.anno_corrente, self.mese_corrente
            )] + [
                self.model.get_valore_cella(data_str, role)
                for role in self.view.row_labels[2:]
                if role not in (nome_riga, "Giro Visite")
            ]
            if nuovo_valore.casefold() in {value.strip().casefold() for value in used}:
                QMessageBox.warning(
                    self.view,
                    f"Assegnazione non valida · {self.versione_corrente.value.capitalize()}",
                    "Lo specializzando ha già un altro incarico in questa giornata.",
                )
                self.aggiorna_tabella()
                return

        sync_rooms = (
            nome_riga in ("Sala Op. I", "Sala Op. II") and self.model_sale_op is not None
        )
        monday = data_corrente - datetime.timedelta(days=data_corrente.weekday())
        if sync_rooms and self.versione_corrente == CalendarVersion.EFFETTIVO:
            sync_rooms = self.model_sale_op.has_settimana(monday)
        if sync_rooms and (
            self.model_sale_op.get_stato_settimana(monday) == "CONVALIDATO"
            or self.model_sale_op.get_stato_mese(
                data_corrente.year, data_corrente.month
            ) == "CONVALIDATO"
        ):
            QMessageBox.warning(
                self.view, f"Sale {self.versione_corrente.value.capitalize()} convalidate",
                "La settimana delle Sale Operatorie è già convalidata. "
                "L'assegnazione non è stata modificata.",
            )
            self.aggiorna_tabella()
            return
        actual_assignments = None
        if sync_rooms and self.versione_corrente == CalendarVersion.EFFETTIVO:
            daily = self.model_sale_op.load_mese(
                data_corrente.year, data_corrente.month
            ).get("turni", {}).get(data_str, {})
            actual_assignments = dict(daily.get("specializzandi") or {})
            edited_role = "OR I" if nome_riga == "Sala Op. I" else "OR II"
            other_role = "OR II" if edited_role == "OR I" else "OR I"
            other_assignment = actual_assignments.get(other_role, "")
            if nuovo_valore and nuovo_valore.casefold() == other_assignment.strip().casefold():
                QMessageBox.warning(
                    self.view, "Assegnazione non valida · Effettivo",
                    "Lo specializzando è già assegnato all'altra sala nell'Effettivo "
                    "delle Sale Operatorie. L'assegnazione non è stata modificata.",
                )
                self.aggiorna_tabella()
                return
            actual_assignments[edited_role] = nuovo_valore
        if (
            sync_rooms and self.versione_corrente == CalendarVersion.EFFETTIVO
            and self._conflitto_assegnazioni_interventi(data_str, nome_riga, nuovo_valore)
        ):
            QMessageBox.warning(
                self.view, "Assegnazioni Effettivo da verificare",
                "La sala contiene interventi assegnati a uno specializzando diverso. "
                "La modifica del turno non riassegna i singoli interventi né le attività "
                "del libretto. L'assegnazione non è stata modificata.",
            )
            self.aggiorna_tabella()
            return
        try:
            self.model.set_valore_cella(data_str, nome_riga, nuovo_valore)
        except (OSError, ValueError) as error:
            QMessageBox.warning(
                self.view, f"Assegnazione {self.versione_corrente.value} non salvata", str(error),
            )
            self.aggiorna_tabella()
            return

        if sync_rooms:
            try:
                if actual_assignments is not None:
                    or1 = actual_assignments.get("OR I", "")
                    or2 = actual_assignments.get("OR II", "")
                else:
                    or1 = self.model.get_valore_cella(data_str, "Sala Op. I")
                    or2 = self.model.get_valore_cella(data_str, "Sala Op. II")
                self.model_sale_op.set_specializzandi(data_str, or1, or2)
            except (OSError, ValueError) as error:
                QMessageBox.warning(
                    self.view, f"Sincronizzazione Sale {self.versione_corrente.value} non riuscita",
                    f"Assegnazione dello Scadenzario salvata. "
                    f"Aggiornamento delle Sale non riuscito:\n{error}",
                )

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
        dialog.setWindowTitle(f"Scegli mese · {self.versione_corrente.value.capitalize()}")
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

            mesi_disp = self._mesi_disponibili()
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
