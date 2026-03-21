import calendar
import datetime
from PySide6.QtWidgets import (
    QTableWidgetItem, QDialog, QVBoxLayout, QHBoxLayout,
    QComboBox, QSpinBox, QPushButton, QTableWidget, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont

from src.views.components.combo_delegate import ComboBoxDelegate


class ControllerSaleOperatorie:
    def __init__(self, view, model):
        self.view = view
        self.model = model
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

        self.view.btn_prev.clicked.connect(self.mese_precedente)
        self.view.btn_next.clicked.connect(self.mese_successivo)
        self.view.btn_mese_anno.clicked.connect(self.scegli_mese_anno)

        self.view.tabella.cellChanged.connect(self.salva_modifica_cella)

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

        elif modalita in ["CORRENTE", "PIANIFICAZIONE"]:
            self.anno_corrente = self.real_anno
            self.mese_corrente = self.real_mese

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
            if view_date <= real_date:
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
        delegate_spec = ComboBoxDelegate(specializzandi_attivi, self.view.tabella)

        for riga in range(2, len(self.view.row_labels)):
            self.view.tabella.setItemDelegateForRow(riga, delegate_spec)

    def aggiorna_tabella(self):
        self.view.tabella.blockSignals(True)

        self.gestisci_navigazione()

        stato_json = self.model.get_stato_mese(self.anno_corrente, self.mese_corrente)

        if self.modalita_corrente == "STORICO":
            self.view.tabella.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            self.view.btn_convalida.setVisible(False)

        elif self.modalita_corrente == "PIANIFICAZIONE":
            self.view.tabella.setEditTriggers(QTableWidget.EditTrigger.AllEditTriggers)
            self.view.btn_convalida.setVisible(False)

        elif self.modalita_corrente == "CORRENTE":
            self.view.tabella.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            if stato_json == "CONVALIDATO":
                self.view.btn_convalida.setVisible(False)
            else:
                self.view.btn_convalida.setVisible(True)

        self.view.lbl_modalita.setText(f"MODALITÀ: {self.modalita_corrente}  |  STATO: {stato_json}")

        nome_mese = self.mesi_ita[self.mese_corrente - 1].upper()
        self.view.btn_mese_anno.setText(f"{nome_mese} {self.anno_corrente}")

        num_giorni = 7

        self.view.tabella.setColumnCount(num_giorni)
        self.view.tabella.setHorizontalHeaderLabels([str(i) for i in range(1, num_giorni + 1)])

        colore_festivo = QColor("#f1f5f9")
        colore_normale = QColor(Qt.GlobalColor.transparent)

        font_giorni = QFont("Segoe UI", 11, QFont.Weight.Bold)
        font_celle = QFont("Segoe UI", 13, QFont.Weight.DemiBold)

        for giorno in range(1, num_giorni + 1):
            data_corrente = datetime.date(self.anno_corrente, self.mese_corrente, giorno)
            data_str = data_corrente.strftime("%Y-%m-%d")

            giorno_settimana = data_corrente.weekday()
            is_festivo = giorno_settimana in (5, 6)

            nome_giorno = self.giorni_ita[giorno_settimana].upper()
            item_giorno = QTableWidgetItem(nome_giorno)
            item_giorno.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_giorno.setFlags(item_giorno.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_giorno.setBackground(colore_festivo if is_festivo else colore_normale)
            item_giorno.setFont(font_giorni)
            item_giorno.setForeground(QColor("#64748b"))
            self.view.tabella.setItem(0, giorno - 1, item_giorno)

            for riga in range(1, len(self.view.row_labels)):
                nome_riga = self.view.row_labels[riga]

                if is_festivo:
                    item = QTableWidgetItem("-")
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item.setForeground(QColor("#cbd5e1"))

                else:
                    if riga == 1:
                        nome_specializzandi = self.model.get_specializzandi(data_str)
                        item = QTableWidgetItem(nome_specializzandi)

                    else:
                        contenuto = self.model.get_slot(data_str, nome_riga)
                        item = QTableWidgetItem(contenuto)

                    item.setForeground(QColor("#1e293b"))

                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setBackground(colore_festivo if is_festivo else colore_normale)
                item.setFont(font_celle)

                self.view.tabella.setItem(riga, giorno - 1, item)

        self.view.tabella.blockSignals(False)

    def salva_modifica_cella(self, riga, colonna):
        if riga == 0 or self.modalita_corrente in ["STORICO", "CORRENTE"]:
            return

        if self.model.get_stato_mese(self.anno_corrente, self.mese_corrente) == "CONVALIDATO":
            return

        giorno = colonna + 1
        data_corrente = datetime.date(self.anno_corrente, self.mese_corrente, giorno)
        data_str = data_corrente.strftime("%Y-%m-%d")

        nome_riga = self.view.row_labels[riga]
        item = self.view.tabella.item(riga, colonna)
        nuovo_valore = item.text() if item else ""

        self.model.set_valore_cella(data_str, nome_riga, nuovo_valore)

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
        dialog = QDialog(self.view)
        dialog.setWindowTitle("Vai a...")
        dialog.setFixedSize(300, 120)
        dialog.setStyleSheet("""
            QComboBox, QSpinBox { font-size: 16px; padding: 5px; }
            QPushButton { background-color: #0d6efd; color: white; font-weight: bold; border-radius: 5px; padding: 8px; 
            font-size: 14px; }
            QPushButton:hover { background-color: #0b5ed7; }
        """)

        layout = QVBoxLayout(dialog)
        h_layout = QHBoxLayout()

        combo_mesi = QComboBox()
        combo_mesi.addItems(self.mesi_ita)
        combo_mesi.setCurrentIndex(self.mese_corrente - 1)

        spin_anno = QSpinBox()
        spin_anno.setRange(2020, 2050)
        spin_anno.setValue(self.anno_corrente)

        h_layout.addWidget(combo_mesi)
        h_layout.addWidget(spin_anno)
        layout.addLayout(h_layout)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Conferma")
        btn_ok.clicked.connect(dialog.accept)
        btn_cancel = QPushButton("Annulla")
        btn_cancel.setStyleSheet("background-color: #6c757d;")
        btn_cancel.clicked.connect(dialog.reject)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_mese = combo_mesi.currentIndex() + 1
            selected_anno = spin_anno.value()
            selected_date = datetime.date(selected_anno, selected_mese, 1)
            real_date = datetime.date(self.real_anno, self.real_mese, 1)

            if self.modalita_corrente == "PIANIFICAZIONE" and selected_date < real_date:
                self.mese_corrente = self.real_mese
                self.anno_corrente = self.real_anno

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
