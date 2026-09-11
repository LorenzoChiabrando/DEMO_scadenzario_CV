import copy
import datetime
import logging
import os as _os
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, Signal, QSize, Qt, Slot
from PySide6.QtWidgets import (
    QTableWidget, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QPushButton, QListWidget, QListWidgetItem, QComboBox,
    QFileDialog, QInputDialog, QMessageBox,
)

from src.calendar_presentation import (
    month_dates,
    month_weeks,
    person_initials,
    resident_legend,
    resolve_resident_name,
)
from src.exports.calendar_pdf import CalendarPdfDocument, CalendarPdfRow, write_calendar_pdf
from src.optimization.platform_service import plan_platform_week
from src.planning_schema import OPTIMIZATION_KEY
from src.workers.platform_planning_worker import (
    PlanningService,
    PlatformPlanningWorker,
)

MESI_ITA = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
            "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
MESI_ITA_COMPLETI = [
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
]

GIORNI_ITA = ["LUN", "MAR", "MER", "GIO", "VEN"]
CHANGEOVER_MINUTES = 11
ROOM_IDS = ("OR-1", "OR-2")
MAX_OPERATIONS_PER_ROOM = 12

CHIRURGHI_MOCK = [
    "Prof. Rinaldi F.", "Dr. Mauro M.", "Dr. Ferrini A.",
    "Dr. Giordano S.", "Dr. Bianchi L.",
]

_LOGGER = logging.getLogger(__name__)


def build_sale_operatorie_pdf_document(
    model,
    dates: tuple[datetime.date, ...],
    residents: list[dict],
) -> CalendarPdfDocument:
    """Prepara i dati delle sale operatorie per il PDF."""

    if not dates:
        raise ValueError("at least one date is required")
    compact = len(dates) > 7
    weekdays = ("Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom")
    columns = tuple(
        f"{day.day} {weekdays[day.weekday()][:1]}"
        if compact
        else f"{day.day} {weekdays[day.weekday()]}"
        for day in dates
    )

    specialist_values: list[str] = []
    operations_by_day: list[list[dict]] = []
    for day in dates:
        if day.weekday() >= 5:
            specialist_values.append("-")
            operations_by_day.append([])
            continue
        names = [
            value.strip()
            for value in model.get_specializzandi(day.isoformat()).splitlines()
            if value.strip()
        ]
        specialist_values.append(
            " / ".join(
                person_initials(value)
                if compact
                else resolve_resident_name(value, residents)
                for value in names
            )
            or "-"
        )
        operations_by_day.append(model.get_operazioni(day.isoformat()))

    rows = [
        CalendarPdfRow(
            label="Specializzandi",
            values=tuple(specialist_values),
            background="#ede9fe",
        )
    ]
    max_operations = max((len(operations) for operations in operations_by_day), default=0)
    for operation_index in range(max_operations):
        values: list[str] = []
        for operations in operations_by_day:
            if operation_index >= len(operations):
                values.append("-")
                continue
            operation = operations[operation_index]
            patient_name = operation.get("nome_paziente", "")
            room = operation.get("sala_operatoria", "")
            if compact:
                room_short = str(room).removeprefix("OR-")
                values.append(
                    " ".join(filter(None, (person_initials(patient_name), room_short)))
                )
            else:
                time_range = (
                    f"{operation.get('ora_inizio', '')}-{operation.get('ora_fine', '')}"
                ).strip("-")
                values.append(" · ".join(filter(None, (time_range, patient_name, room))))
        rows.append(
            CalendarPdfRow(
                label=f"Operazione {operation_index + 1}",
                values=tuple(values),
                background="#ffffff" if operation_index % 2 == 0 else "#f8fafc",
            )
        )

    period = f"{dates[0].strftime('%d/%m/%Y')} - {dates[-1].strftime('%d/%m/%Y')}"
    return CalendarPdfDocument(
        title="Programmazione sale operatorie",
        period=period,
        column_headers=columns,
        rows=tuple(rows),
        legend=tuple(resident_legend(residents).items()) if compact else (),
    )


def _get_lunedi(data: datetime.date) -> datetime.date:
    return data - datetime.timedelta(days=data.weekday())


def _finestra_giorno(data: datetime.date) -> tuple:
    """Ritorna (ora_inizio_str, ora_fine_str, minuti_tot) per il giorno."""
    return ("08:00", "18:00", 600)


def _str_to_min(s: str) -> int:
    h, m = map(int, s.split(":"))
    return h * 60 + m


def _min_to_str(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


class ControllerSaleOperatorie(QObject):
    """
    Tre modalità:
      STORICO       – lettura settimane passate convalidate
      CONSULTAZIONE – revisione e convalida del piano settimanale
      PIANIFICAZIONE – generazione e modifica del piano
    """

    planning_busy_changed = Signal(bool)

    def __init__(
        self,
        view,
        model,
        model_scadenzario=None,
        model_pazienti=None,
        model_libretto=None,
        *,
        project_root: str | Path | None = None,
        planning_service: PlanningService = plan_platform_week,
    ):
        super().__init__(view)
        self.view = view
        self.model = model
        self.model_scad = model_scadenzario
        self.model_paz = model_pazienti
        self.model_lib = model_libretto
        self._project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[2]
        )
        self._planning_service = planning_service
        self._planning_worker: PlatformPlanningWorker | None = None
        self._planning_cancel_event: Event | None = None
        self._planning_result = None
        self._planning_error: str | None = None
        self._planning_cancelled = False
        self._planning_button_text = self.view.btn_pianifica.text()
        self.modalita_corrente = None

        self.oggi = datetime.date.today()
        self.settimana_corrente = _get_lunedi(self.oggi)
        self.settimana_display = self.settimana_corrente
        self.visualizzazione = "SETTIMANA"
        self.mese_display = self.oggi.replace(day=1)
        self._display_dates: tuple[datetime.date, ...] = tuple(
            self.settimana_display + datetime.timedelta(days=offset)
            for offset in range(5)
        )

        self._settimane_convalidate: list[datetime.date] = []
        self._idx_storico: int = 0
        self._stato_corrente: str = "BOZZA"

        self._connect_signals()

    def _connect_signals(self):
        self.view.btn_storico.clicked.connect(
            lambda: self.apri_vista("STORICO"))
        self.view.btn_consultazione.clicked.connect(
            lambda: self.apri_vista("CONSULTAZIONE"))
        self.view.btn_pianificazione.clicked.connect(
            lambda: self.apri_vista("PIANIFICAZIONE"))
        self.view.btn_indietro.clicked.connect(self.torna_alla_dashboard)
        self.view.btn_prev.clicked.connect(self.settimana_precedente)
        self.view.btn_next.clicked.connect(self.settimana_successiva)
        self.view.btn_pianifica.clicked.connect(self.pianifica_settimana)
        self.view.btn_pulisci.clicked.connect(self.pulisci_settimana)
        self.view.btn_convalida.clicked.connect(self.convalida_settimana)
        self.view.tabella.cellChanged.connect(self.salva_modifica_cella)
        self.view.tabella.cellClicked.connect(self._on_cella_cliccata)
        self.view.tabella.operazione_spostata.connect(self._sposta_operazione)
        self.view.tabella.operazione_scambiata.connect(self._scambia_operazioni)
        if hasattr(self.view, "btn_vista_settimana"):
            self.view.btn_vista_settimana.clicked.connect(
                lambda: self.imposta_visualizzazione("SETTIMANA")
            )
            self.view.btn_vista_mese.clicked.connect(
                lambda: self.imposta_visualizzazione("MESE")
            )
            self.view.btn_esporta_pdf.clicked.connect(self.esporta_pdf)

    def apri_vista(self, modalita):
        self.modalita_corrente = modalita
        self.visualizzazione = "SETTIMANA"
        if hasattr(self.view, "set_month_mode"):
            self.view.set_month_mode(False)

        if modalita == "STORICO":
            self._settimane_convalidate = self.model.get_settimane_convalidate()
            if not self._settimane_convalidate:
                self._avviso(
                    "Nessuna settimana convalidata",
                    "Non ci sono ancora settimane convalidate nello storico.\n"
                    "Convalida una settimana dalla sezione Consultazione.",
                )
                return
            self._idx_storico = len(self._settimane_convalidate) - 1
            self.settimana_display = self._settimane_convalidate[self._idx_storico]
        elif modalita == "CONSULTAZIONE":
            self.settimana_display = self.settimana_corrente

        elif modalita == "PIANIFICAZIONE":
            self.settimana_display = self.settimana_corrente + datetime.timedelta(weeks=1)

        self.view.stacked_widget.setCurrentIndex(1)
        self.aggiorna_tabella()

    @staticmethod
    def _first_monday(year: int, month: int) -> datetime.date:
        first = datetime.date(year, month, 1)
        return first + datetime.timedelta(days=(-first.weekday()) % 7)

    def imposta_visualizzazione(self, mode: str) -> None:
        """Passa dalla vista settimanale a quella mensile."""

        if mode not in {"SETTIMANA", "MESE"}:
            raise ValueError(f"unsupported operating-room view mode: {mode}")
        self.visualizzazione = mode
        if mode == "MESE":
            self.mese_display = self.settimana_display.replace(day=1)
            self.view.set_month_mode(True)
        else:
            if self.modalita_corrente == "STORICO":
                matching_weeks = [
                    (index, monday)
                    for index, monday in enumerate(self._settimane_convalidate)
                    if any(
                        (monday + datetime.timedelta(days=offset)).replace(day=1)
                        == self.mese_display
                        for offset in range(5)
                    )
                ]
                if matching_weeks:
                    self._idx_storico, self.settimana_display = matching_weeks[0]
            elif not (
                self.settimana_display.year == self.mese_display.year
                and self.settimana_display.month == self.mese_display.month
            ):
                self.settimana_display = self._first_monday(
                    self.mese_display.year, self.mese_display.month
                )
            self.view.set_month_mode(False)
        self.aggiorna_tabella()

    def torna_alla_dashboard(self):
        self.modalita_corrente = None
        self.view.stacked_widget.setCurrentIndex(0)

    def settimana_precedente(self):
        if self.visualizzazione == "MESE":
            self._sposta_mese(-1)
            return
        if self.modalita_corrente == "STORICO":
            self._idx_storico -= 1
            self.settimana_display = self._settimane_convalidate[self._idx_storico]
        else:
            self.settimana_display -= datetime.timedelta(weeks=1)
        self.aggiorna_tabella()

    def settimana_successiva(self):
        if self.visualizzazione == "MESE":
            self._sposta_mese(1)
            return
        if self.modalita_corrente == "STORICO":
            self._idx_storico += 1
            self.settimana_display = self._settimane_convalidate[self._idx_storico]
        else:
            self.settimana_display += datetime.timedelta(weeks=1)
        self.aggiorna_tabella()

    def _mesi_storici(self) -> list[datetime.date]:
        return sorted(
            {
                (monday + datetime.timedelta(days=offset)).replace(day=1)
                for monday in self._settimane_convalidate
                for offset in range(5)
            }
        )

    def _sposta_mese(self, direction: int) -> None:
        if self.modalita_corrente == "STORICO":
            months = self._mesi_storici()
            if self.mese_display not in months:
                return
            index = months.index(self.mese_display) + direction
            if not 0 <= index < len(months):
                return
            self.mese_display = months[index]
        else:
            month_index = self.mese_display.year * 12 + self.mese_display.month - 1 + direction
            year, zero_based_month = divmod(month_index, 12)
            candidate = datetime.date(year, zero_based_month + 1, 1)
            minimum = (
                self.settimana_corrente + datetime.timedelta(weeks=1)
            ).replace(day=1)
            if self.modalita_corrente == "PIANIFICAZIONE" and candidate < minimum:
                return
            self.mese_display = candidate
        self.settimana_display = self._first_monday(
            self.mese_display.year, self.mese_display.month
        )
        self.aggiorna_tabella()

    def _label_settimana(self) -> str:
        lun = self.settimana_display
        ven = lun + datetime.timedelta(days=4)
        ml = MESI_ITA[lun.month - 1]
        mv = MESI_ITA[ven.month - 1]
        if lun.month == ven.month:
            return f"{lun.day}–{ven.day} {ml} {lun.year}"
        return f"{lun.day} {ml} – {ven.day} {mv} {lun.year}"

    def esporta_pdf(self) -> None:
        """Esporta il mese o una settimana in PDF."""

        anchor = (
            self.mese_display
            if self.visualizzazione == "MESE"
            else self.settimana_display.replace(day=1)
        )
        weeks = tuple(
            tuple(day for day in week if day.weekday() < 5)
            for week in month_weeks(anchor.year, anchor.month)
        )
        weeks = tuple(week for week in weeks if week)
        choices = ["Mese intero"] + [
            f"Settimana {index}: {week[0].strftime('%d/%m')} - {week[-1].strftime('%d/%m')}"
            for index, week in enumerate(weeks, 1)
        ]
        choice, accepted = QInputDialog.getItem(
            self.view,
            "Esporta sale operatorie",
            "Intervallo da esportare:",
            choices,
            0,
            False,
        )
        if not accepted:
            return
        if choice == choices[0]:
            dates = month_dates(anchor.year, anchor.month)
            scope = "mese"
        else:
            week_index = choices.index(choice) - 1
            dates = weeks[week_index]
            scope = f"settimana-{week_index + 1}"

        suggested = (
            f"sale-operatorie-{anchor.year:04d}-{anchor.month:02d}-{scope}.pdf"
        )
        path, _ = QFileDialog.getSaveFileName(
            self.view,
            "Salva calendario PDF",
            str(Path.home() / suggested),
            "Documento PDF (*.pdf)",
        )
        if not path:
            return
        residents = getattr(self.model_scad, "specializzandi", None)
        if residents is None:
            residents = getattr(self.model, "specializzandi", [])
        try:
            document = build_sale_operatorie_pdf_document(
                self.model,
                dates,
                residents,
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

    def _load_style(self):
        path = _os.path.join("asset", "styles", "pazienti.qss")
        return open(path, encoding="utf-8").read() if _os.path.exists(path) else ""

    def _avviso(self, titolo: str, messaggio: str, tipo: str = "info", parent=None):
        """Dialog informativo/warning coerente con lo stile app."""
        accent = "#d97706" if tipo == "warning" else "#0369a1"
        dlg = QDialog(parent or self.view)
        dlg.setWindowTitle(titolo)
        dlg.setModal(True)
        dlg.setMinimumWidth(420)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.setStyleSheet(self._load_style() + "\nQDialog { background-color: #ffffff; }")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        bar = QFrame()
        bar.setFixedHeight(5)
        bar.setStyleSheet(f"background-color:{accent}; border:none;")
        root.addWidget(bar)
        inner = QVBoxLayout()
        inner.setContentsMargins(30, 22, 30, 22)
        inner.setSpacing(10)
        root.addLayout(inner)
        lbl_t = QLabel(titolo)
        lbl_t.setObjectName("TitoloDialog")
        lbl_t.setStyleSheet(f"color:{accent};")
        inner.addWidget(lbl_t)
        lbl_m = QLabel(messaggio)
        lbl_m.setWordWrap(True)
        lbl_m.setStyleSheet("color:#334155; font-size:14px;")
        inner.addWidget(lbl_m)
        inner.addSpacing(6)
        btn = QPushButton("OK")
        btn.setObjectName("BtnSalvaDialog")
        btn.setFixedHeight(44)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(dlg.accept)
        inner.addWidget(btn)
        dlg.exec()

    def _conferma(self, titolo: str, messaggio: str,
                  testo_si: str = "Conferma", parent=None) -> bool:
        """Dialog Yes/No coerente con lo stile app. Ritorna True se confermato."""
        dlg = QDialog(parent or self.view)
        dlg.setWindowTitle(titolo)
        dlg.setModal(True)
        dlg.setMinimumWidth(420)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.setStyleSheet(self._load_style() + "\nQDialog { background-color: #ffffff; }")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        bar = QFrame()
        bar.setFixedHeight(5)
        bar.setStyleSheet("background-color:#0369a1; border:none;")
        root.addWidget(bar)
        inner = QVBoxLayout()
        inner.setContentsMargins(30, 22, 30, 22)
        inner.setSpacing(10)
        root.addLayout(inner)
        lbl_t = QLabel(titolo)
        lbl_t.setObjectName("TitoloDialog")
        inner.addWidget(lbl_t)
        lbl_m = QLabel(messaggio)
        lbl_m.setWordWrap(True)
        lbl_m.setStyleSheet("color:#334155; font-size:14px;")
        inner.addWidget(lbl_m)
        inner.addSpacing(6)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_no = QPushButton("Annulla")
        btn_no.setObjectName("BtnAnnullaDialog")
        btn_no.setFixedHeight(44)
        btn_no.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_no.clicked.connect(dlg.reject)
        btn_si = QPushButton(testo_si)
        btn_si.setObjectName("BtnSalvaDialog")
        btn_si.setFixedHeight(44)
        btn_si.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_si.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_no)
        btn_row.addWidget(btn_si)
        inner.addLayout(btn_row)
        return dlg.exec() == QDialog.DialogCode.Accepted

    def _gestisci_navigazione(self, stato: str):
        self.view.btn_prev.setVisible(True)
        self.view.btn_next.setVisible(True)

        if self.visualizzazione == "MESE":
            if self.modalita_corrente == "STORICO":
                months = self._mesi_storici()
                index = months.index(self.mese_display) if self.mese_display in months else -1
                self.view.btn_prev.setVisible(index > 0)
                self.view.btn_next.setVisible(0 <= index < len(months) - 1)
            elif self.modalita_corrente == "CONSULTAZIONE":
                self.view.btn_prev.setVisible(False)
                self.view.btn_next.setVisible(False)
            elif self.modalita_corrente == "PIANIFICAZIONE":
                minimum = (
                    self.settimana_corrente + datetime.timedelta(weeks=1)
                ).replace(day=1)
                self.view.btn_prev.setVisible(self.mese_display > minimum)
            self.view.btn_pianifica.setVisible(False)
            self.view.btn_pulisci.setVisible(False)
            self.view.btn_convalida.setVisible(False)
            return

        if self.modalita_corrente == "STORICO":
            self.view.btn_prev.setVisible(self._idx_storico > 0)
            self.view.btn_next.setVisible(
                self._idx_storico < len(self._settimane_convalidate) - 1
            )

        elif self.modalita_corrente == "CONSULTAZIONE":
            self.view.btn_prev.setVisible(False)
            self.view.btn_next.setVisible(False)

        elif self.modalita_corrente == "PIANIFICAZIONE":
            next_week = self.settimana_corrente + datetime.timedelta(weeks=1)
            if self.settimana_display <= next_week:
                self.view.btn_prev.setVisible(False)

        show_pianifica = (
            self.modalita_corrente in ("PIANIFICAZIONE", "CONSULTAZIONE")
            and stato != "CONVALIDATO"
        )
        self.view.btn_pianifica.setVisible(show_pianifica)
        self.view.btn_pulisci.setVisible(show_pianifica)

        show_convalida = (
            self.modalita_corrente == "CONSULTAZIONE"
            and stato == "BOZZA"
        )
        self.view.btn_convalida.setVisible(show_convalida)

    def aggiorna_tabella(self):
        self.view.tabella.blockSignals(True)
        month_mode = self.visualizzazione == "MESE"
        if month_mode:
            dates = month_dates(self.mese_display.year, self.mese_display.month)
            stato = "RIEPILOGO"
        else:
            dates = tuple(
                self.settimana_display + datetime.timedelta(days=offset)
                for offset in range(5)
            )
            stato = self.model.get_stato_settimana(self.settimana_display)
        self._display_dates = dates
        self._stato_corrente = stato
        self._gestisci_navigazione(stato)
        if month_mode:
            month_name = MESI_ITA_COMPLETI[self.mese_display.month - 1].upper()
            self.view.btn_mese_anno.setText(f"{month_name} {self.mese_display.year}")
        else:
            self.view.btn_mese_anno.setText(self._label_settimana())
        self.view.tabella.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.view.aggiorna_badge(self.modalita_corrente, stato)
        self.view.tabella.setColumnCount(len(dates))
        if month_mode:
            self.view.tabella.setHorizontalHeaderLabels([str(day.day) for day in dates])
        else:
            self.view.tabella.setHorizontalHeaderLabels(
                ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"]
            )

        can_edit = (
            not month_mode
            and
            self.modalita_corrente in ("PIANIFICAZIONE", "CONSULTAZIONE")
            and stato != "CONVALIDATO"
        )

        max_operations = max(
            (len(self.model.get_operazioni(day.isoformat())) for day in dates),
            default=0,
        )
        self.view.adatta_righe_operazioni(max_operations)

        drop_targets: dict = {}
        for col, data_col in enumerate(dates):
            data_str = data_col.strftime("%Y-%m-%d")
            is_oggi = (data_col == self.oggi)
            is_weekend = data_col.weekday() >= 5

            weekday = ("LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM")[
                data_col.weekday()
            ]
            giorno_label = f"{weekday}  {data_col.day} {MESI_ITA[data_col.month - 1]}"
            self.view.tabella.setItem(
                0,
                col,
                self.view.crea_item_giorno(giorno_label, is_weekend, is_oggi),
            )

            spec_val = "" if is_weekend else self.model.get_specializzandi(data_str)
            item_spec = self.view.crea_item_cella(
                spec_val,
                is_weekend,
                is_oggi,
                compact=month_mode,
            )
            item_spec.setFlags(item_spec.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.view.tabella.setItem(1, col, item_spec)

            operazioni = [] if is_weekend else self.model.get_operazioni(data_str)
            drop_targets[col] = 2 + len(operazioni)
            for op_idx in range(self.view.current_max_ops):
                row = op_idx + 2
                if op_idx < len(operazioni):
                    op = operazioni[op_idx]
                    ha_paziente = bool(op.get("nome_paziente"))
                    on_click = (lambda r=row, c=col: self._on_cella_cliccata(r, c)) if ha_paziente else None
                    widget = self.view.crea_widget_operazione(
                        op, is_oggi, on_click,
                        draggable=can_edit and ha_paziente,
                        col=col, op_idx=op_idx,
                        compact=month_mode,
                    )
                    self.view.tabella.setCellWidget(row, col, widget)
                else:
                    on_click_vuoto = None
                    if can_edit and op_idx == len(operazioni):
                        on_click_vuoto = (lambda r=row, c=col: self._on_slot_vuoto_cliccato(r, c))
                    self.view.tabella.setCellWidget(row, col, self.view.crea_widget_vuoto(is_oggi, on_click_vuoto))

        self.view.tabella.set_drop_targets(drop_targets if can_edit else {})
        self.view.tabella.blockSignals(False)

    def _ha_piano_esistente(self) -> bool:
        for col in range(5):
            data_col = self.settimana_display + datetime.timedelta(days=col)
            data_str = data_col.strftime("%Y-%m-%d")
            ops = self.model.get_operazioni(data_str)
            if any(op.get("nome_paziente") for op in ops):
                return True
        return False

    def pianifica_settimana(self):
        """Start or cooperatively cancel the Pyomo/HiGHS weekly planner."""
        if self._planning_worker is not None:
            self._request_planning_cancellation()
            return

        if not self.model_scad:
            self._avviso("Errore", "Dati scadenzario non disponibili.", tipo="warning")
            return

        overwrite = self._ha_piano_esistente()
        if overwrite and not self._conferma(
            "Ripianifica settimana",
            f"La settimana {self._label_settimana()} ha già un piano.\n\n"
            "Vuoi rigenerarlo sovrascrivendo i dati attuali?",
            testo_si="Rigenera",
        ):
            return

        self._start_planning_worker(self.settimana_display, overwrite=overwrite)

    def _start_planning_worker(self, monday: datetime.date, *, overwrite: bool) -> None:
        cancel_event = Event()
        worker = PlatformPlanningWorker(
            self._project_root,
            monday,
            overwrite=overwrite,
            cancel_event=cancel_event,
            planning_service=self._planning_service,
            parent=self,
        )

        worker.succeeded.connect(self._record_planning_success)
        worker.failed.connect(self._record_planning_failure)
        worker.cancelled.connect(self._record_planning_cancellation)
        worker.finished.connect(self._finish_planning)

        self._planning_worker = worker
        self._planning_cancel_event = cancel_event
        self._planning_result = None
        self._planning_error = None
        self._planning_cancelled = False
        self._set_planning_busy(True)
        worker.start()

    def _request_planning_cancellation(self) -> None:
        if self._planning_cancel_event is None:
            return
        self._planning_cancel_event.set()
        self.view.btn_pianifica.setText("ANNULLAMENTO IN CORSO…")
        self.view.btn_pianifica.setEnabled(False)

    @Slot(object)
    def _record_planning_success(self, result) -> None:
        self._planning_result = result

    @Slot(str)
    def _record_planning_failure(self, message: str) -> None:
        self._planning_error = message

    @Slot()
    def _record_planning_cancellation(self) -> None:
        self._planning_cancelled = True

    @Slot()
    def _finish_planning(self) -> None:
        finished_worker = self._planning_worker
        result = self._planning_result
        error = self._planning_error
        was_cancelled = self._planning_cancelled

        self._planning_worker = None
        self._planning_cancel_event = None
        self._planning_result = None
        self._planning_error = None
        self._planning_cancelled = False
        try:
            self._set_planning_busy(False)

            if result is not None:
                self.model.invalidate_cache()
                self.aggiorna_tabella()
                objective = result.result.objective
                objective_text = (
                    f"\nValore obiettivo: {objective.weighted_total:.3f}"
                    if objective is not None
                    else ""
                )
                self._avviso(
                    "Pianificazione completata",
                    f"Piano settimanale salvato correttamente.\n"
                    f"Interventi pianificati: {len(result.result.schedule)}.\n"
                    f"Stato solver: {result.result.status.value}."
                    f"{objective_text}",
                )
            elif was_cancelled:
                self._avviso(
                    "Pianificazione annullata",
                    "Il calcolo è stato interrotto e il piano precedente non è stato modificato.",
                )
            else:
                self._avviso(
                    "Impossibile pianificare",
                    error or "La pianificazione non è stata completata.",
                    tipo="warning",
                )
        finally:
            if finished_worker is not None:
                finished_worker.deleteLater()

    def _set_planning_busy(self, busy: bool) -> None:
        for control in (
            self.view.btn_indietro,
            self.view.btn_prev,
            self.view.btn_next,
            self.view.btn_pulisci,
            self.view.btn_convalida,
            self.view.tabella,
        ):
            control.setEnabled(not busy)
        self.view.btn_pianifica.setEnabled(True)
        self.view.btn_pianifica.setText(
            "ANNULLA PIANIFICAZIONE" if busy else self._planning_button_text
        )
        self.planning_busy_changed.emit(busy)

    def shutdown_planning(self, timeout_ms: int = 10_000) -> bool:
        """Cancel an active solve and wait briefly before the application exits."""
        worker = self._planning_worker
        if worker is None or not worker.isRunning():
            return True
        if self._planning_cancel_event is not None:
            self._planning_cancel_event.set()
        worker.requestInterruption()
        return worker.wait(timeout_ms)

    def pulisci_settimana(self):
        if not self._conferma(
            "Pulisci piano",
            f"Vuoi eliminare tutte le assegnazioni di pazienti\n"
            f"per la settimana {self._label_settimana()}?\n\n"
            "Gli specializzandi rimarranno invariati.",
            testo_si="Pulisci",
        ):
            return

        for col in range(5):
            data_col = self.settimana_display + datetime.timedelta(days=col)
            data_str = data_col.strftime("%Y-%m-%d")
            self.model.set_operazioni(data_str, [])

        self.aggiorna_tabella()

    def convalida_settimana(self):
        if not self._conferma(
            "Convalida settimana",
            f"Confermi la convalida definitiva della settimana\n"
            f"{self._label_settimana()}?\n\n"
            "L'operazione non sarà reversibile.",
            testo_si="Convalida",
        ):
            return

        self.model.set_stato_settimana(self.settimana_display, "CONVALIDATO")
        self._registra_in_libretti()
        self._segna_pazienti_completati()
        self.aggiorna_tabella()

        self._avviso(
            "Convalida effettuata",
            f"La settimana {self._label_settimana()} è stata convalidata.\n"
            "Le attività operative sono state registrate nei libretti.",
        )

    def _segna_pazienti_completati(self):
        """Segna come Completato ogni paziente che ha un'operazione nella settimana appena convalidata."""
        if not self.model_paz:
            return
        for col in range(5):
            data_col = self.settimana_display + datetime.timedelta(days=col)
            data_str = data_col.strftime("%Y-%m-%d")
            for op in self.model.get_operazioni(data_str):
                paz_id = op.get("id_paziente", "")
                if paz_id:
                    self.model_paz.aggiorna_stato_paziente(paz_id, "Completato")

    def _registra_in_libretti(self):
        """
        Dopo la convalida, legge le operazioni della settimana e scrive un record
        nel libretto dello specializzando assegnato dal planner. I piani legacy,
        privi dei nuovi campi per-intervento, mantengono il comportamento storico.
        """
        if not self.model_lib:
            return
        attivita_per_spec: dict[str, list] = {}
        for col in range(5):
            data_col = self.settimana_display + datetime.timedelta(days=col)
            data_str = data_col.strftime("%Y-%m-%d")
            dati_mese = self.model.load_mese(data_col.year, data_col.month)
            turno = dati_mese.get("turni", {}).get(data_str, {})
            spec_giorno = turno.get("specializzandi", {})
            or1 = spec_giorno.get("OR I", "")
            or2 = spec_giorno.get("OR II", "")
            for op in self.model.get_operazioni(data_str):
                if not op.get("nome_paziente"):
                    continue
                complessita = op.get("complessita", "")
                tipo_chirurgia = op.get("tipo_chirurgia", "")
                if (not complessita or not tipo_chirurgia) and self.model_paz:
                    paz = self.model_paz.get_paziente_by_id(op.get("id_paziente", ""))
                    if paz:
                        complessita = complessita or paz.get("complessita", "")
                        tipo_chirurgia = tipo_chirurgia or paz.get("tipo_chirurgia", "")
                base_att = {
                    "data": data_str,
                    "slot": op.get("ora_inizio", "08:00"),
                    "nome_paziente": op.get("nome_paziente", ""),
                    "id_paziente": op.get("id_paziente", ""),
                    "diagnosi": op.get("diagnosi", ""),
                    "intervento": op.get("intervento", ""),
                    "codice_intervento": op.get("codice_intervento", ""),
                    "interventi": op.get("interventi", []),
                    "chirurgo": op.get("chirurgo", ""),
                    "complessita": complessita,
                    "tipo_chirurgia": tipo_chirurgia,
                    "ora_inizio": op.get("ora_inizio", "08:00"),
                    "ora_fine": op.get("ora_fine", "18:00"),
                    "durata": op.get("durata", 90),
                }
                has_individual_assignment = any(
                    key in op
                    for key in (
                        "id_specializzando",
                        "specializzando",
                        "ruolo_specializzando",
                    )
                )
                if has_individual_assignment:
                    targets = [
                        (
                            op.get("ruolo_specializzando", ""),
                            op.get("specializzando", ""),
                        )
                    ]
                else:
                    targets = [("OR I", or1), ("OR II", or2)]
                for ruolo, nome_spec in targets:
                    if not nome_spec:
                        continue
                    att = {**base_att, "ruolo": ruolo}
                    attivita_per_spec.setdefault(nome_spec, []).append(att)
        if attivita_per_spec:
            self.model_lib.registra_attivita_settimana(attivita_per_spec)

    def _ricalcola_orari(self, operazioni: list):
        """Recalculate two independent room timelines including changeover."""

        min_corrente = {room_id: _str_to_min("08:00") for room_id in ROOM_IDS}
        for op in operazioni:
            room_id = self._room_id(op)
            durata = int(op.get("durata", 0))
            op["sala_operatoria"] = room_id
            op["ora_inizio"] = _min_to_str(min_corrente[room_id])
            op["ora_fine"] = _min_to_str(min_corrente[room_id] + durata)
            min_corrente[room_id] += durata + CHANGEOVER_MINUTES

    @staticmethod
    def _room_id(operation: dict) -> str:
        room_id = operation.get("sala_operatoria")
        return room_id if room_id in ROOM_IDS else ROOM_IDS[0]

    def _capacity_for_room(self, day: datetime.date, room_id: str) -> int:
        """Read v[k,t] from the monthly schedule, with a legacy-safe fallback."""

        if getattr(self, "model_scad", None) is None:
            return _finestra_giorno(day)[2]
        month_data = self.model_scad.load_mese(day.year, day.month)
        configuration = month_data.get(OPTIMIZATION_KEY, {})
        rooms = configuration.get("sale_operatorie", {})
        default_capacity = rooms.get(room_id, {}).get("capacita_minuti", 600)
        overrides = configuration.get("capacita_sessioni", {})
        return overrides.get(day.isoformat(), {}).get(room_id, default_capacity)

    def _next_room_start(self, operations: list[dict], room_id: str) -> int:
        room_operations = [op for op in operations if self._room_id(op) == room_id]
        if not room_operations:
            return _str_to_min("08:00")
        return _str_to_min(room_operations[-1]["ora_fine"]) + CHANGEOVER_MINUTES

    def _scambia_operazioni(self, col: int, src_idx: int, dst_idx: int):
        """Swap di due operazioni nello stesso giorno, con conferma modal."""
        if (self.modalita_corrente not in ("PIANIFICAZIONE", "CONSULTAZIONE")
                or self._stato_corrente == "CONVALIDATO"):
            return
        if not (0 <= col < len(GIORNI_ITA) and src_idx >= 0 and dst_idx >= 0):
            return

        data_col = self.settimana_display + datetime.timedelta(days=col)
        data_str = data_col.strftime("%Y-%m-%d")
        operazioni = copy.deepcopy(self.model.get_operazioni(data_str))

        if src_idx >= len(operazioni) or dst_idx >= len(operazioni):
            return

        nome_src = operazioni[src_idx].get("nome_paziente", "—")
        nome_dst = operazioni[dst_idx].get("nome_paziente", "—")
        giorno = GIORNI_ITA[col]
        mese = MESI_ITA[data_col.month - 1]

        if not self._conferma(
            "Scambia operazioni",
            f"Vuoi scambiare l'ordine di queste due operazioni\n"
            f"del {giorno} {data_col.day} {mese}?\n\n"
            f"  • {nome_src}\n"
            f"  • {nome_dst}\n\n"
            "Gli orari verranno ricalcolati automaticamente.",
            testo_si="Scambia",
        ):
            self.aggiorna_tabella()
            return

        operazioni[src_idx], operazioni[dst_idx] = operazioni[dst_idx], operazioni[src_idx]
        self._ricalcola_orari(operazioni)
        self.model.set_operazioni(data_str, operazioni)
        self.aggiorna_tabella()

    def _sposta_operazione(self, src_col: int, src_op_idx: int, dst_col: int):
        """Sposta un'operazione da un giorno a un altro (in coda) e salva il JSON."""
        if (self.modalita_corrente not in ("PIANIFICAZIONE", "CONSULTAZIONE")
                or self._stato_corrente == "CONVALIDATO"):
            return
        if not (0 <= src_col < len(GIORNI_ITA)
                and 0 <= dst_col < len(GIORNI_ITA)
                and src_col != dst_col
                and src_op_idx >= 0):
            return

        src_date = self.settimana_display + datetime.timedelta(days=src_col)
        dst_date = self.settimana_display + datetime.timedelta(days=dst_col)
        src_str = src_date.strftime("%Y-%m-%d")
        dst_str = dst_date.strftime("%Y-%m-%d")

        original_src_ops = copy.deepcopy(self.model.get_operazioni(src_str))
        original_dst_ops = copy.deepcopy(self.model.get_operazioni(dst_str))

        if src_op_idx >= len(original_src_ops):
            return

        moved_room = self._room_id(original_src_ops[src_op_idx])
        destination_room_ops = [
            operation
            for operation in original_dst_ops
            if self._room_id(operation) == moved_room
        ]
        if len(destination_room_ops) >= MAX_OPERATIONS_PER_ROOM:
            self._avviso(
                "Sala completa",
                f"Non è possibile inserire più di {MAX_OPERATIONS_PER_ROOM} "
                f"operazioni in {moved_room} nello stesso giorno.",
                tipo="warning",
            )
            return

        try:
            durate_destinazione = [
                int(op.get("durata", 0)) for op in destination_room_ops
            ]
            durata_spostata = int(original_src_ops[src_op_idx].get("durata", 0))
        except (TypeError, ValueError):
            self._avviso(
                "Durata non valida",
                "Lo spostamento non può essere eseguito perché una durata non è valida.",
                tipo="warning",
            )
            return

        if durata_spostata <= 0 or any(durata <= 0 for durata in durate_destinazione):
            self._avviso(
                "Durata non valida",
                "Lo spostamento non può essere eseguito perché una durata non è positiva.",
                tipo="warning",
            )
            return

        capacita_giorno = self._capacity_for_room(dst_date, moved_room)
        nuovo_numero_operazioni = len(durate_destinazione) + 1
        minuti_occupati = sum(durate_destinazione) + durata_spostata
        minuti_occupati += CHANGEOVER_MINUTES * max(0, nuovo_numero_operazioni - 1)
        if minuti_occupati > capacita_giorno:
            self._avviso(
                "Capacità giornaliera superata",
                f"Lo spostamento supererebbe la capacità di {moved_room}.",
                tipo="warning",
            )
            return

        src_ops = copy.deepcopy(original_src_ops)
        dst_ops = copy.deepcopy(original_dst_ops)
        op = src_ops.pop(src_op_idx)
        op["sala_operatoria"] = moved_room
        if any(
            key in op
            for key in ("id_specializzando", "specializzando", "ruolo_specializzando")
        ):
            op["id_specializzando"] = ""
            op["specializzando"] = ""
            op["ruolo_specializzando"] = ""
        dst_ops.append(op)

        self._ricalcola_orari(src_ops)
        self._ricalcola_orari(dst_ops)

        try:
            self.model.set_operazioni(src_str, src_ops)
            self.model.set_operazioni(dst_str, dst_ops)
        except Exception:
            _LOGGER.exception("Errore durante la persistenza dello spostamento")
            try:
                self.model.set_operazioni(src_str, original_src_ops)
                self.model.set_operazioni(dst_str, original_dst_ops)
            except Exception:
                _LOGGER.exception("Impossibile ripristinare il piano dopo un errore di salvataggio")
            self._avviso(
                "Spostamento non salvato",
                "Si è verificato un errore durante il salvataggio. Il piano è stato ripristinato.",
                tipo="warning",
            )
            self.aggiorna_tabella()
            return

        self.aggiorna_tabella()

    def _rimuovi_paziente_da_slot(self, dialog, data_str: str, op_idx: int):
        if not self._conferma(
            "Rimuovi paziente",
            "Vuoi rimuovere questo paziente dal piano?\n\nIl paziente tornerà in lista d'attesa.",
            testo_si="Rimuovi",
            parent=dialog,
        ):
            return
        operazioni = self.model.get_operazioni(data_str)
        if op_idx < len(operazioni):
            operazioni.pop(op_idx)
            self._ricalcola_orari(operazioni)
            self.model.set_operazioni(data_str, operazioni)
            self.aggiorna_tabella()
        dialog.accept()

    def _mostra_dialog_inserimento_manuale(
        self,
        data_str: str,
        data_col: datetime.date,
        starts_by_room: dict[str, int],
    ):
        if not self.model_paz:
            self._avviso("Errore", "Dati pazienti non disponibili.", tipo="warning")
            return

        gia_pianificati = self.model.get_pazienti_pianificati_ids()
        disponibili = [
            p for p in self.model_paz.get_pazienti_in_attesa()
            if p.get("id") not in gia_pianificati
        ]
        if not disponibili:
            self._avviso(
                "Nessun paziente disponibile",
                "Non ci sono pazienti in lista d'attesa da inserire.",
            )
            return

        dialog = QDialog(self.view)
        giorno_nome = GIORNI_ITA[data_col.weekday()]
        mese_nome   = MESI_ITA[data_col.month - 1]
        dialog.setWindowTitle(f"Inserimento manuale — {giorno_nome} {data_col.day} {mese_nome}")
        dialog.setModal(True)
        dialog.setMinimumWidth(560)
        dialog.setMinimumHeight(540)
        dialog.setSizeGripEnabled(True)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        dialog.setStyleSheet(self._load_style() + "\nQDialog { background-color: #f8fafc; }")

        root = QVBoxLayout(dialog)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        lbl_titolo = QLabel("Inserimento manuale")
        lbl_titolo.setObjectName("TitoloDialog")
        root.addWidget(lbl_titolo)

        lbl_sub = QLabel(
            f"Seleziona un paziente da aggiungere — "
            f"{giorno_nome} {data_col.day} {mese_nome} {data_col.year}"
        )
        lbl_sub.setObjectName("SottoTitoloDialog")
        root.addWidget(lbl_sub)

        sep = QFrame()
        sep.setObjectName("SeparatoreDialog")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        lbl_room = QLabel("SALA OPERATORIA")
        lbl_room.setObjectName("LblCampo")
        root.addWidget(lbl_room)
        combo_room = QComboBox()
        combo_room.setObjectName("ComboDialog")
        combo_room.addItems(ROOM_IDS)
        combo_room.setFixedHeight(40)
        first_room = min(ROOM_IDS, key=lambda room_id: (starts_by_room[room_id], room_id))
        combo_room.setCurrentText(first_room)
        root.addWidget(combo_room)

        lbl_lista = QLabel("PAZIENTI IN LISTA D'ATTESA")
        lbl_lista.setObjectName("LblCampo")
        root.addWidget(lbl_lista)

        lista_widget = QListWidget()
        lista_widget.setObjectName("ListaRisultati")
        lista_widget.setSpacing(4)
        root.addWidget(lista_widget, 1)

        _COLORI_URG = {
            "Alta":  ("#fee2e2", "#dc2626"),
            "Media": ("#fef9c3", "#d97706"),
            "Bassa": ("#dcfce7", "#15803d"),
        }
        for paz in disponibili:
            interventi = paz.get("interventi", [])
            codici = [i.get("codice", "") for i in interventi if i.get("codice")]
            cod_text = "  ·  ".join(codici) if codici else paz.get("codice_intervento", "N/D")
            durata = paz.get("durata_intervento", 90)
            urg = paz.get("urgenza", "")
            bg_u, fg_u = _COLORI_URG.get(urg, ("#f1f5f9", "#475569"))

            item_frame = QFrame()
            item_frame.setObjectName("ItemCard")
            item_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            row_lay = QHBoxLayout(item_frame)
            row_lay.setContentsMargins(14, 10, 14, 10)
            row_lay.setSpacing(12)

            badge_u = QLabel(urg or "–")
            badge_u.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge_u.setFixedWidth(56)
            badge_u.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            badge_u.setStyleSheet(
                f"background-color:{bg_u}; color:{fg_u}; font-weight:bold; "
                f"font-size:11px; padding:3px 6px; border-radius:10px; border:1px solid {fg_u}50;"
            )

            txt = QVBoxLayout()
            txt.setSpacing(2)
            lbl_np = QLabel(f"{paz.get('cognome','').upper()} {paz.get('nome','')}")
            lbl_np.setObjectName("ItemNome")
            lbl_np.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            lbl_cp = QLabel(f"{cod_text}  ·  {durata} min")
            lbl_cp.setObjectName("ItemMatricola")
            lbl_cp.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            txt.addWidget(lbl_np)
            txt.addWidget(lbl_cp)

            row_lay.addWidget(badge_u)
            row_lay.addLayout(txt, 1)

            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 62))
            item.setData(Qt.ItemDataRole.UserRole, paz.get("id"))
            lista_widget.addItem(item)
            lista_widget.setItemWidget(item, item_frame)

        lbl_timing = QLabel("Seleziona un paziente per vedere l'orario proposto")
        lbl_timing.setObjectName("SottoTitoloDialog")
        lbl_timing.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_timing.setFixedHeight(38)
        root.addWidget(lbl_timing)

        sep2 = QFrame()
        sep2.setObjectName("SeparatoreDialog")
        sep2.setFixedHeight(1)
        root.addWidget(sep2)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_annulla = QPushButton("Annulla")
        btn_annulla.setObjectName("BtnAnnullaDialog")
        btn_annulla.setFixedHeight(44)
        btn_annulla.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_annulla.clicked.connect(dialog.reject)
        btn_inserisci = QPushButton("Inserisci")
        btn_inserisci.setObjectName("BtnSalvaDialog")
        btn_inserisci.setFixedHeight(44)
        btn_inserisci.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_inserisci.setEnabled(False)
        btn_row.addWidget(btn_annulla)
        btn_row.addWidget(btn_inserisci)
        root.addLayout(btn_row)

        paz_sel = [None]

        def _on_selezione():
            for i in range(lista_widget.count()):
                w = lista_widget.itemWidget(lista_widget.item(i))
                if w:
                    w.setProperty("selected", False)
                    w.style().unpolish(w)
                    w.style().polish(w)
                    w.update()

            items = lista_widget.selectedItems()
            if not items:
                lbl_timing.setText("Seleziona un paziente per vedere l'orario proposto")
                lbl_timing.setStyleSheet("")
                btn_inserisci.setEnabled(False)
                paz_sel[0] = None
                return

            sel_widget = lista_widget.itemWidget(items[0])
            if sel_widget:
                sel_widget.setProperty("selected", True)
                sel_widget.style().unpolish(sel_widget)
                sel_widget.style().polish(sel_widget)
                sel_widget.update()

            paz_id = items[0].data(Qt.ItemDataRole.UserRole)
            paz = next((p for p in disponibili if p.get("id") == paz_id), None)
            if not paz:
                return
            paz_sel[0] = paz
            durata = paz.get("durata_intervento", 90)
            room_id = combo_room.currentText()
            ora_inizio_min = starts_by_room[room_id]
            ora_fine_min = ora_inizio_min + durata
            ora_i = _min_to_str(ora_inizio_min)
            ora_f = _min_to_str(ora_fine_min)
            session_end = _str_to_min("08:00") + self._capacity_for_room(data_col, room_id)
            if ora_fine_min <= session_end:
                lbl_timing.setText(
                    f"✓  {room_id} · {ora_i} – {ora_f}  ({durata} min)"
                )
                lbl_timing.setStyleSheet(
                    "color:#16a34a; font-weight:bold; font-size:14px;"
                )
                btn_inserisci.setEnabled(True)
            else:
                eccedenza = ora_fine_min - session_end
                lbl_timing.setText(
                    f"✗  {room_id} supera la capacità di {eccedenza} min"
                )
                lbl_timing.setStyleSheet(
                    "color:#dc2626; font-weight:bold; font-size:14px;"
                )
                btn_inserisci.setEnabled(False)

        lista_widget.itemSelectionChanged.connect(_on_selezione)
        combo_room.currentTextChanged.connect(lambda _value: _on_selezione())

        def _on_inserisci():
            paz = paz_sel[0]
            if paz:
                room_id = combo_room.currentText()
                self._inserisci_paziente_manuale(
                    dialog,
                    paz,
                    data_str,
                    starts_by_room[room_id],
                    room_id,
                )

        btn_inserisci.clicked.connect(_on_inserisci)
        dialog.exec()

    def _inserisci_paziente_manuale(
        self,
        dialog,
        paz: dict,
        data_str: str,
        ora_inizio_min: int,
        room_id: str,
    ):
        import random as _rnd
        operazioni = self.model.get_operazioni(data_str)
        if sum(self._room_id(operation) == room_id for operation in operazioni) >= (
            MAX_OPERATIONS_PER_ROOM
        ):
            self._avviso(
                "Sala completa",
                f"{room_id} contiene già {MAX_OPERATIONS_PER_ROOM} operazioni.",
                tipo="warning",
                parent=dialog,
            )
            return
        durata = paz.get("durata_intervento", 90)
        ora_fine_min = ora_inizio_min + durata
        day = datetime.date.fromisoformat(data_str)
        session_end = _str_to_min("08:00") + self._capacity_for_room(day, room_id)
        if ora_fine_min > session_end:
            self._avviso(
                "Errore",
                f"L'operazione supera la capacità di {room_id}.",
                tipo="warning",
                parent=dialog,
            )
            return
        interventi_paz = paz.get("interventi") or [{
            "codice":       paz.get("codice_intervento", ""),
            "descrizione":  paz.get("descrizione_intervento", ""),
            "durata":       durata,
        }]
        chirurgo = _rnd.choice(CHIRURGHI_MOCK)
        op = {
            "nome_paziente":    f"{paz.get('cognome','')} {paz.get('nome','')}",
            "id_paziente":      paz.get("id", ""),
            "diagnosi":         paz.get("diagnosi", ""),
            "intervento":       interventi_paz[0].get("descrizione", "") if interventi_paz else "",
            "codice_intervento":interventi_paz[0].get("codice", "") if interventi_paz else "",
            "interventi":       interventi_paz,
            "chirurgo":         chirurgo,
            "complessita":      paz.get("complessita", ""),
            "tipo_chirurgia":   paz.get("tipo_chirurgia", ""),
            "durata":           durata,
            "ora_inizio":       _min_to_str(ora_inizio_min),
            "ora_fine":         _min_to_str(ora_fine_min),
            "sala_operatoria":  room_id,
            "id_specializzando": "",
            "specializzando": "",
            "ruolo_specializzando": "",
        }
        operazioni.append(op)
        operazioni.sort(
            key=lambda operation: (
                operation.get("ora_inizio", ""),
                self._room_id(operation),
            )
        )
        self._ricalcola_orari(operazioni)
        self.model.set_operazioni(data_str, operazioni)
        self.aggiorna_tabella()
        dialog.accept()

    def salva_modifica_cella(self, riga, colonna):
        pass

    def _date_for_column(self, column: int) -> datetime.date:
        dates = getattr(self, "_display_dates", ())
        if 0 <= column < len(dates):
            return dates[column]
        return self.settimana_display + datetime.timedelta(days=column)

    def _on_cella_cliccata(self, riga, colonna):
        """Apre il popup con i dettagli del paziente se la cella contiene un'assegnazione."""
        data_col = self._date_for_column(colonna)
        if riga == 1 and self.visualizzazione == "MESE":
            item = self.view.tabella.item(riga, colonna)
            raw_names = item.data(Qt.ItemDataRole.UserRole) if item else ""
            full_names = [
                resolve_resident_name(value, getattr(self.model_scad, "specializzandi", []))
                for value in str(raw_names or "").splitlines()
                if value.strip()
            ]
            self.view.lbl_dettaglio_cella.setText(
                f"{data_col.strftime('%d/%m/%Y')} · Specializzandi: "
                + (" / ".join(full_names) if full_names else "—")
            )
            return
        if riga < 2:
            return
        op_idx = riga - 2
        data_str = data_col.strftime("%Y-%m-%d")
        operazioni = self.model.get_operazioni(data_str)
        if op_idx >= len(operazioni):
            return
        op = operazioni[op_idx]
        if not op.get("nome_paziente"):
            return
        paz_full = None
        if self.model_paz and op.get("id_paziente"):
            paz_full = self.model_paz.get_paziente_by_id(op["id_paziente"])
        self._mostra_popup_paziente(op, paz_full, data_str=data_str, op_idx=op_idx)

    def _on_slot_vuoto_cliccato(self, riga, colonna):
        """Apre il dialog di inserimento manuale per il primo slot libero del giorno."""
        if self.visualizzazione == "MESE":
            return
        data_col = self._date_for_column(colonna)
        data_str = data_col.strftime("%Y-%m-%d")
        operazioni = self.model.get_operazioni(data_str)
        starts_by_room = {
            room_id: self._next_room_start(operazioni, room_id) for room_id in ROOM_IDS
        }
        self._mostra_dialog_inserimento_manuale(data_str, data_col, starts_by_room)

    def _mostra_popup_paziente(self, slot: dict, paz_full: dict | None,
                               data_str: str = None, op_idx: int = None):
        dialog = QDialog(self.view)
        dialog.setWindowTitle("Dettagli Paziente")
        dialog.setModal(True)
        dialog.setMinimumWidth(500)
        dialog.setSizeGripEnabled(False)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setStyleSheet(self._load_style() + "\nQDialog { background-color: #f8fafc; }")

        root = QVBoxLayout(dialog)
        root.setContentsMargins(30, 30, 30, 30)
        root.setSpacing(16)

        lbl_titolo = QLabel(slot.get("nome_paziente", "—"))
        lbl_titolo.setObjectName("TitoloDialog")
        lbl_titolo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(lbl_titolo)

        lbl_sub = QLabel("Scheda paziente")
        lbl_sub.setObjectName("SottoTitoloDialog")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(lbl_sub)

        sep = QFrame()
        sep.setObjectName("SeparatoreDialog")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        def _riga(etichetta: str, valore: str):
            row = QHBoxLayout()
            row.setSpacing(12)
            lbl_k = QLabel(etichetta.upper())
            lbl_k.setObjectName("LblCampo")
            lbl_k.setFixedWidth(175)
            lbl_v = QLabel(valore or "—")
            lbl_v.setWordWrap(True)
            lbl_v.setStyleSheet("color: #1e293b; font-size: 14px;")
            row.addWidget(lbl_k)
            row.addWidget(lbl_v, 1)
            root.addLayout(row)

        ora_i = slot.get("ora_inizio", "")
        ora_f = slot.get("ora_fine", "")
        durata = slot.get("durata", "")
        if data_str:
            try:
                data_operazione = datetime.date.fromisoformat(data_str).strftime("%d/%m/%Y")
            except ValueError:
                data_operazione = data_str
            _riga("Data operazione", data_operazione)
        if ora_i and ora_f:
            _riga("Orario", f"{ora_i} – {ora_f}  ({durata} min)" if durata else f"{ora_i} – {ora_f}")

        _riga("Sala operatoria", slot.get("sala_operatoria", "OR-1"))
        specializzandi = []
        if slot.get("specializzando"):
            specializzandi.append(
                f"{slot.get('specializzando')} · {slot.get('ruolo_specializzando', '')}".strip(
                    " ·"
                )
            )
        elif data_str:
            specializzandi.extend(
                value.strip()
                for value in self.model.get_specializzandi(data_str).splitlines()
                if value.strip()
            )
        if specializzandi:
            _riga("Specializzandi", "\n".join(dict.fromkeys(specializzandi)))

        if paz_full and (
            paz_full.get("codice_diagnosi") or paz_full.get("descrizione_diagnosi")
        ):
            _riga("Codice ICD-9-CM", paz_full.get("codice_diagnosi", ""))
            _riga(
                "Descrizione diagnosi",
                paz_full.get("descrizione_diagnosi", "")
                or paz_full.get("diagnosi", ""),
            )
        else:
            _riga("Diagnosi", slot.get("diagnosi", ""))
        interventi_list = slot.get("interventi", [])
        if interventi_list:
            for idx_i, inv in enumerate(interventi_list, 1):
                cod_i = inv.get("codice", "")
                desc_i = inv.get("descrizione", "")
                dur_i = inv.get("durata", "")
                label_i = f"Intervento {idx_i}" if len(interventi_list) > 1 else "Intervento"
                val_i = f"[{cod_i}]  {desc_i}" if cod_i else desc_i
                if dur_i:
                    val_i += f"  ({dur_i} min)"
                _riga(label_i, val_i)
        else:
            cod = slot.get("codice_intervento", "")
            inter = slot.get("intervento", "")
            _riga("Intervento", f"[{cod}]  {inter}" if cod else inter)

        if paz_full:
            _riga("Tipo chirurgia", paz_full.get("tipo_chirurgia", ""))
            _riga("Complessità", paz_full.get("complessita", ""))

            urgenza = paz_full.get("urgenza", "")
            colori_urg = {"Alta": "#dc2626", "Media": "#d97706", "Bassa": "#16a34a"}
            lbl_urg_row = QHBoxLayout()
            lbl_urg_row.setSpacing(12)
            lbl_urg_k = QLabel("URGENZA")
            lbl_urg_k.setObjectName("LblCampo")
            lbl_urg_k.setFixedWidth(175)
            lbl_urg_v = QLabel(urgenza or "—")
            lbl_urg_v.setStyleSheet(
                f"color: {colori_urg.get(urgenza, '#334155')}; "
                "font-size: 14px; font-weight: bold;"
            )
            lbl_urg_row.addWidget(lbl_urg_k)
            lbl_urg_row.addWidget(lbl_urg_v, 1)
            root.addLayout(lbl_urg_row)

        _riga("Chirurgo", slot.get("chirurgo", ""))

        if paz_full:
            _riga("Data inserimento", paz_full.get("data_inserimento", ""))
            note = paz_full.get("note", "").strip()
            if note:
                _riga("Note cliniche", note)

        sep_btn = QFrame()
        sep_btn.setObjectName("SeparatoreDialog")
        sep_btn.setFixedHeight(1)
        root.addWidget(sep_btn)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        if (self.modalita_corrente in ("PIANIFICAZIONE", "CONSULTAZIONE")
                and self._stato_corrente != "CONVALIDATO"
                and data_str is not None and op_idx is not None):
            btn_rimuovi = QPushButton("Rimuovi dal piano")
            btn_rimuovi.setObjectName("BtnElimina")
            btn_rimuovi.setFixedHeight(44)
            btn_rimuovi.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_rimuovi.clicked.connect(
                lambda: self._rimuovi_paziente_da_slot(dialog, data_str, op_idx)
            )
            btn_row.addWidget(btn_rimuovi)

        btn_chiudi = QPushButton("Chiudi")
        btn_chiudi.setObjectName("BtnAnnullaDialog")
        btn_chiudi.setFixedHeight(44)
        btn_chiudi.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_chiudi.clicked.connect(dialog.accept)
        btn_row.addWidget(btn_chiudi)

        root.addLayout(btn_row)

        dialog.exec()
