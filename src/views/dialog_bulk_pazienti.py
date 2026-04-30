import os
import csv
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QComboBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

_CAMPI_CSV = [
    "nome", "cognome", "diagnosi",
    "codice_intervento", "descrizione_intervento",
    "tipo_chirurgia", "complessita", "urgenza",
]

_HEADERS = [
    "Nome", "Cognome", "Diagnosi",
    "Cod. ICD-9", "Desc. Intervento",
    "Tipo Chir.", "Complessità", "Urgenza", "Durata",
]

_COL_NOME       = 0
_COL_COGNOME    = 1
_COL_DIAGNOSI   = 2
_COL_CODICE     = 3
_COL_INTERVENTO = 4
_COL_TIPO       = 5
_COL_CPX        = 6
_COL_URG        = 7
_COL_DUR        = 8

_DURATE_OPTIONS = ["30 min", "45 min", "60 min", "90 min", "120 min", "150 min", "180 min"]

_COMBO_DEFS = {
    _COL_TIPO: (["Aperta", "Endovascolare"], "Aperta"),
    _COL_CPX:  (["Alta", "Media", "Bassa"],  "Media"),
    _COL_URG:  (["Alta", "Media", "Bassa"],  "Media"),
}

_BG_OK  = QColor("#ffffff")
_BG_ERR = QColor("#fef2f2")
_FG_ERR = QColor("#b91c1c")
_FG_OK  = QColor("#1e293b")


class DialogBulkPazienti(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Importa Pazienti da CSV")
        self.setMinimumWidth(1060)
        self.setMinimumHeight(560)
        self.setSizeGripEnabled(True)
        self.setup_ui()
        self.load_styles()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)

        lbl_titolo = QLabel("Importa Pazienti da CSV")
        lbl_titolo.setObjectName("TitoloDialog")
        lbl_titolo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titolo)

        lbl_sub = QLabel(
            "Seleziona un file CSV con intestazione. "
            "Colonne richieste: "
            "<b>nome, cognome, diagnosi, codice_intervento, "
            "descrizione_intervento, tipo_chirurgia, complessita, urgenza</b>. "
            "Le celle in rosso indicano valori mancanti o non validi: modificale direttamente prima di importare."
        )
        lbl_sub.setObjectName("SottoTitoloDialog")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_sub.setWordWrap(True)
        layout.addWidget(lbl_sub)

        sep = QFrame()
        sep.setObjectName("SeparatoreDialog")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        file_row = QHBoxLayout()
        self.lbl_file = QLabel("Nessun file selezionato")
        self.lbl_file.setObjectName("LblFileCSV")
        self.lbl_file.setFixedHeight(32)

        self.btn_sfoglia = QPushButton("Sfoglia…")
        self.btn_sfoglia.setObjectName("BtnAnnullaDialog")
        self.btn_sfoglia.setFixedSize(110, 36)
        self.btn_sfoglia.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sfoglia.clicked.connect(self._scegli_file)

        file_row.addWidget(self.lbl_file, stretch=1)
        file_row.addWidget(self.btn_sfoglia)
        layout.addLayout(file_row)

        self.lbl_stato = QLabel("")
        self.lbl_stato.setObjectName("LblStatoCSV")
        layout.addWidget(self.lbl_stato)

        self.tabella = QTableWidget(0, len(_HEADERS))
        self.tabella.setObjectName("TabellaBulk")
        self.tabella.setHorizontalHeaderLabels(_HEADERS)

        hh = self.tabella.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setMinimumSectionSize(70)
        for col, w in [
            (_COL_NOME,       120),
            (_COL_COGNOME,    120),
            (_COL_DIAGNOSI,   200),
            (_COL_CODICE,      80),
            (_COL_INTERVENTO, 200),
            (_COL_TIPO,       110),
            (_COL_CPX,        100),
            (_COL_URG,         85),
            (_COL_DUR,         90),
        ]:
            self.tabella.setColumnWidth(col, w)

        self.tabella.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.tabella.verticalHeader().setDefaultSectionSize(40)
        self.tabella.verticalHeader().setVisible(False)
        self.tabella.setAlternatingRowColors(False)
        self.tabella.setShowGrid(True)
        self.tabella.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        # cellChanged si connette dopo il caricamento per evitare loop
        layout.addWidget(self.tabella)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_annulla = QPushButton("Annulla")
        self.btn_annulla.setObjectName("BtnAnnullaDialog")
        self.btn_annulla.setFixedHeight(44)
        self.btn_annulla.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_annulla.clicked.connect(self.reject)

        self.btn_importa = QPushButton("Importa Pazienti")
        self.btn_importa.setObjectName("BtnSalvaDialog")
        self.btn_importa.setFixedHeight(44)
        self.btn_importa.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_importa.setEnabled(False)
        self.btn_importa.clicked.connect(self._conferma_importazione)

        btn_layout.addWidget(self.btn_annulla)
        btn_layout.addWidget(self.btn_importa)
        layout.addLayout(btn_layout)

    def _scegli_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona file CSV", "", "File CSV (*.csv)"
        )
        if not path:
            return
        self.lbl_file.setText(os.path.basename(path))
        self._carica_csv(path)

    def _carica_csv(self, path: str):
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                righe = list(csv.DictReader(f))
        except Exception as e:
            QMessageBox.critical(self, "Errore lettura file",
                                 f"Impossibile leggere il file:\n{e}")
            return

        if not righe:
            self.lbl_stato.setText("Il file è vuoto.")
            return

        intestazioni = {k.strip().lower() for k in righe[0].keys()}
        mancanti = [c for c in _CAMPI_CSV if c not in intestazioni]
        if mancanti:
            QMessageBox.warning(
                self, "Colonne mancanti",
                "Il file CSV non contiene le colonne richieste:\n"
                + ", ".join(mancanti)
            )
            return

        self.tabella.blockSignals(True)
        self.tabella.setRowCount(0)

        for riga in righe:
            r = {k.strip().lower(): v.strip() for k, v in riga.items()}
            self._inserisci_riga(r)

        self.tabella.blockSignals(False)

        self.tabella.cellChanged.connect(self._on_cella_cambiata)

        self._aggiorna_stato()

    def _inserisci_riga(self, r: dict):
        row = self.tabella.rowCount()
        self.tabella.insertRow(row)

        for col in [_COL_NOME, _COL_COGNOME, _COL_DIAGNOSI,
                    _COL_CODICE, _COL_INTERVENTO]:
            item = QTableWidgetItem(r.get(_CAMPI_CSV[col], ""))
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                                  if col in (_COL_DIAGNOSI, _COL_INTERVENTO)
                                  else Qt.AlignmentFlag.AlignCenter)
            self.tabella.setItem(row, col, item)

        for col, (opzioni, default) in _COMBO_DEFS.items():
            combo = self._crea_combo(opzioni)
            val = r.get(_CAMPI_CSV[col], "").capitalize()
            idx = combo.findText(val)
            combo.setCurrentIndex(idx if idx >= 0 else combo.findText(default))
            combo.currentIndexChanged.connect(
                lambda _idx, c=col, rw=row: self._valida_riga(rw)
            )
            self.tabella.setCellWidget(row, col, combo)

        combo_dur = self._crea_combo(_DURATE_OPTIONS)
        try:
            dur_val = int(str(r.get("durata_intervento", "90")).split()[0])
            dur_idx = combo_dur.findText(f"{dur_val} min")
            combo_dur.setCurrentIndex(dur_idx if dur_idx >= 0 else 3)
        except (ValueError, AttributeError):
            combo_dur.setCurrentIndex(3)  # default 90 min
        self.tabella.setCellWidget(row, _COL_DUR, combo_dur)

        self._valida_riga(row)

    def _crea_combo(self, opzioni: list) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName("ComboDialog")
        combo.addItems(opzioni)
        return combo

    def _valida_riga(self, row: int):
        errori_col = set()

        nome_item = self.tabella.item(row, _COL_NOME)
        cogn_item = self.tabella.item(row, _COL_COGNOME)
        if not (nome_item and nome_item.text().strip()):
            errori_col.add(_COL_NOME)
        if not (cogn_item and cogn_item.text().strip()):
            errori_col.add(_COL_COGNOME)

        for col in [_COL_NOME, _COL_COGNOME, _COL_DIAGNOSI,
                    _COL_CODICE, _COL_INTERVENTO]:
            item = self.tabella.item(row, col)
            if not item:
                continue
            if col in errori_col:
                item.setBackground(_BG_ERR)
                item.setForeground(_FG_ERR)
            else:
                item.setBackground(_BG_OK)
                item.setForeground(_FG_OK)

        self._aggiorna_stato()

    def _on_cella_cambiata(self, row: int, _col: int):
        self._valida_riga(row)

    def _conta_righe_valide(self) -> int:
        valide = 0
        for row in range(self.tabella.rowCount()):
            nome_item = self.tabella.item(row, _COL_NOME)
            cogn_item = self.tabella.item(row, _COL_COGNOME)
            nome = nome_item.text().strip() if nome_item else ""
            cogn = cogn_item.text().strip() if cogn_item else ""
            if nome and cogn:
                valide += 1
        return valide

    def _aggiorna_stato(self):
        totale = self.tabella.rowCount()
        if totale == 0:
            self.lbl_stato.setText("")
            self.btn_importa.setEnabled(False)
            return

        valide = self._conta_righe_valide()
        n_err  = totale - valide

        if n_err == 0:
            self.lbl_stato.setStyleSheet("font-size:13px; font-weight:bold; color:#15803d;")
            self.lbl_stato.setText(f"{totale} righe pronte per l'importazione")
        else:
            self.lbl_stato.setStyleSheet("font-size:13px; font-weight:bold; color:#b45309;")
            self.lbl_stato.setText(
                f"{valide} righe valide, {n_err} con nome o cognome mancante "
                f"(in rosso). Le righe incomplete verranno saltate."
            )

        self.btn_importa.setEnabled(valide > 0)

    def _conferma_importazione(self):
        pazienti = self.get_pazienti()
        if not pazienti:
            QMessageBox.warning(self, "Nessun paziente valido",
                                "Nessuna riga ha nome e cognome compilati.")
            return
        self.accept()

    def get_pazienti(self) -> list[dict]:
        pazienti = []
        for row in range(self.tabella.rowCount()):
            nome_item = self.tabella.item(row, _COL_NOME)
            cogn_item = self.tabella.item(row, _COL_COGNOME)
            nome    = nome_item.text().strip() if nome_item else ""
            cognome = cogn_item.text().strip() if cogn_item else ""
            if not nome or not cognome:
                continue

            def _txt(col):
                it = self.tabella.item(row, col)
                return it.text().strip() if it else ""

            def _combo(col):
                w = self.tabella.cellWidget(row, col)
                return w.currentText() if w else ""

            durata_str = _combo(_COL_DUR)
            try:
                durata = int(durata_str.split()[0])
            except (ValueError, IndexError):
                durata = 90

            codice = _txt(_COL_CODICE)
            desc = _txt(_COL_INTERVENTO)

            pazienti.append({
                "nome":                   nome,
                "cognome":                cognome,
                "diagnosi":               _txt(_COL_DIAGNOSI),
                "codice_intervento":      codice,
                "descrizione_intervento": desc,
                "interventi": [{"codice": codice, "descrizione": desc, "durata": durata}],
                "durata_intervento":      durata,
                "tipo_chirurgia":         _combo(_COL_TIPO),
                "complessita":            _combo(_COL_CPX),
                "urgenza":                _combo(_COL_URG),
                "stato":                  "In Attesa",
                "note":                   "",
            })
        return pazienti

    def load_styles(self):
        style_path = os.path.join("asset", "styles", "pazienti.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
