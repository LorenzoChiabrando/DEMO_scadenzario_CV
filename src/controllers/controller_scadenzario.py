import calendar
import datetime
from PySide6.QtWidgets import QTableWidgetItem, QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QSpinBox, QPushButton
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from src.views.view_scadenzario import ComboBoxDelegate


class ControllerScadenzario:
    def __init__(self, view, model):
        self.view = view
        self.model = model

        self.mesi_ita = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                         "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
        self.giorni_ita = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]

        oggi = datetime.date.today()
        self.anno_corrente = oggi.year
        self.mese_corrente = oggi.month

        self.setup_delegates()

        self.view.btn_prev.clicked.connect(self.mese_precedente)
        self.view.btn_next.clicked.connect(self.mese_successivo)
        self.view.btn_mese_anno.clicked.connect(self.scegli_mese_anno)

        self.view.tabella.cellChanged.connect(self.salva_modifica_cella)

        self.aggiorna_tabella()

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

        nome_mese = self.mesi_ita[self.mese_corrente - 1].upper()
        self.view.btn_mese_anno.setText(f"{nome_mese} {self.anno_corrente}")

        _, num_giorni = calendar.monthrange(self.anno_corrente, self.mese_corrente)

        self.view.tabella.setColumnCount(num_giorni)
        self.view.tabella.setHorizontalHeaderLabels([str(i) for i in range(1, num_giorni + 1)])

        colore_festivo = QColor("#e2e3e5")
        colore_normale = QColor(Qt.GlobalColor.transparent)

        for giorno in range(1, num_giorni + 1):
            data_corrente = datetime.date(self.anno_corrente, self.mese_corrente, giorno)
            data_str = data_corrente.strftime("%Y-%m-%d")

            giorno_settimana = data_corrente.weekday()
            is_festivo = giorno_settimana in (5, 6)

            nome_giorno = self.giorni_ita[giorno_settimana]
            item_giorno = QTableWidgetItem(nome_giorno)
            item_giorno.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_giorno.setFlags(item_giorno.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_giorno.setBackground(colore_festivo if is_festivo else colore_normale)
            self.view.tabella.setItem(0, giorno - 1, item_giorno)

            for riga in range(1, len(self.view.row_labels)):
                nome_riga = self.view.row_labels[riga]

                if is_festivo:
                    item = QTableWidgetItem("-")
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                else:
                    valore_salvato = self.model.get_valore_cella(data_str, nome_riga)
                    item = QTableWidgetItem(valore_salvato)

                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setBackground(colore_festivo if is_festivo else colore_normale)

                self.view.tabella.setItem(riga, giorno - 1, item)

        self.view.tabella.blockSignals(False)

    def salva_modifica_cella(self, riga, colonna):
        if riga == 0:
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
            self.mese_corrente = combo_mesi.currentIndex() + 1
            self.anno_corrente = spin_anno.value()
            self.aggiorna_tabella()
