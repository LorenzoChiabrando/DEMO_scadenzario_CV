import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QComboBox, QScroller,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from src.importers.patient_csv import PatientCsvError, read_patient_csv

_HEADERS = [
    "Nome", "Cognome", "Cod. diagnosi", "Descrizione diagnosi",
    "Cod. ICD-9", "Desc. intervento", "Tipo chir.", "Complessità",
    "Urgenza", "Durata [minuti]",
]

_COL_NOME = 0
_COL_COGNOME = 1
_COL_DIAG_CODICE = 2
_COL_DIAG_DESCRIZIONE = 3
_COL_CODICE = 4
_COL_INTERVENTO = 5
_COL_TIPO = 6
_COL_CPX = 7
_COL_URG = 8
_COL_DUR = 9

_DURATE_OPTIONS = ["30 min", "45 min", "60 min", "90 min", "120 min", "150 min", "180 min"]

_COMBO_DEFS = {
    _COL_TIPO: (["Da classificare", "Aperta", "Endovascolare"], "Da classificare"),
    _COL_CPX: (["Da classificare", "Alta", "Media", "Bassa"], "Da classificare"),
    _COL_URG: (["Alta", "Media", "Bassa"], "Media"),
}

_BG_OK  = QColor("#ffffff")
_BG_ERR = QColor("#fef2f2")
_FG_ERR = QColor("#b91c1c")
_FG_OK  = QColor("#1e293b")


class DialogBulkPazienti(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._interventi_per_riga: dict[int, list] = {}
        self._cell_changed_connected = False
        self._import_context = ""
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
            "Seleziona un CSV dello Scadenziario o un'esportazione TrackCare. "
            "Separatore, codifica e intestazioni vengono riconosciuti automaticamente. "
            "La diagnosi viene divisa in <b>codice ICD-9-CM</b> e <b>descrizione</b>. "
            "La durata opzionale può essere <i>90</i> oppure <i>60;90</i> per più interventi. "
            "Usa il punto e virgola (<b>;</b>) per separare più codici, descrizioni e durate nello stesso paziente. "
            "I dati non disponibili in TrackCare restano visibili come <b>Da classificare</b>."
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
        self.lbl_stato.setWordWrap(True)
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
            (_COL_DIAG_CODICE, 100),
            (_COL_DIAG_DESCRIZIONE, 220),
            (_COL_CODICE,      80),
            (_COL_INTERVENTO, 200),
            (_COL_TIPO,       110),
            (_COL_CPX,        100),
            (_COL_URG,         85),
            (_COL_DUR,         90),
        ]:
            self.tabella.setColumnWidth(col, w)

        self.tabella.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.tabella.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.tabella.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.tabella.verticalHeader().setDefaultSectionSize(40)
        self.tabella.verticalHeader().setVisible(False)
        self.tabella.setAlternatingRowColors(False)
        self.tabella.setShowGrid(True)
        self.tabella.setWordWrap(False)
        self.tabella.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        QScroller.grabGesture(
            self.tabella.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture
        )

        # Evita cellChanged durante il caricamento iniziale.
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
            result = read_patient_csv(path)
        except PatientCsvError as error:
            QMessageBox.critical(self, "Errore lettura file", str(error))
            return

        if not result.rows:
            self.lbl_stato.setText("Il file è vuoto.")
            self.btn_importa.setEnabled(False)
            return

        self.tabella.blockSignals(True)
        self.tabella.setRowCount(0)
        self._interventi_per_riga.clear()
        self._import_context = f"Formato {result.source_format}."
        if result.warnings:
            self._import_context += " " + " ".join(result.warnings)

        for row in result.rows:
            self._inserisci_riga(row)

        self.tabella.blockSignals(False)

        if not self._cell_changed_connected:
            self.tabella.cellChanged.connect(self._on_cella_cambiata)
            self._cell_changed_connected = True

        self._aggiorna_stato()
        if result.warnings:
            self.lbl_stato.setStyleSheet(
                "font-size:13px; font-weight:bold; color:#b45309;"
            )

    def _inserisci_riga(self, r: dict):
        row = self.tabella.rowCount()
        self.tabella.insertRow(row)

        text_fields = {
            _COL_NOME: "nome",
            _COL_COGNOME: "cognome",
            _COL_DIAG_CODICE: "codice_diagnosi",
            _COL_DIAG_DESCRIZIONE: "descrizione_diagnosi",
        }
        for col, field in text_fields.items():
            item = QTableWidgetItem(r.get(field, ""))
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                if col == _COL_DIAG_DESCRIZIONE else Qt.AlignmentFlag.AlignCenter
            )
            self.tabella.setItem(row, col, item)

        def _split(val: str) -> list[str]:
            return [v.strip() for v in val.split(";") if v.strip()]

        codici   = _split(r.get("codice_intervento", ""))
        descrizi = _split(r.get("descrizione_intervento", ""))
        dur_raw  = r.get("durata_intervento", "")

        if ";" in dur_raw:
            durate = []
            for d in dur_raw.split(";"):
                try:
                    parsed = int(d.strip())
                    durate.append(parsed if parsed > 0 else 90)
                except ValueError:
                    durate.append(90)
        else:
            try:
                d = int(dur_raw.split()[0]) if dur_raw.strip() else 90
            except (ValueError, AttributeError):
                d = 90
            if d <= 0:
                d = 90
            durate = [d]

        n = max(len(codici), len(descrizi), 1)
        while len(codici)   < n: codici.append("")
        while len(descrizi) < n: descrizi.append("")
        if len(durate) == 1 and n > 1:
            per_op, resto = divmod(max(durate[0], n), n)
            durate = [per_op + (1 if i < resto else 0) for i in range(n)]
        while len(durate) < n: durate.append(90)

        interventi = [
            {"codice": codici[i], "descrizione": descrizi[i], "durata": durate[i]}
            for i in range(n)
        ]
        self._interventi_per_riga[row] = interventi
        total_dur = sum(iv["durata"] for iv in interventi)

        cod_text  = " ; ".join(c for c in codici)  if codici  else ""
        desc_text = " ; ".join(d for d in descrizi) if descrizi else ""

        item_cod = QTableWidgetItem(cod_text)
        item_cod.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if len(codici) > 1:
            item_cod.setToolTip(cod_text.replace(" ; ", "\n"))
        self.tabella.setItem(row, _COL_CODICE, item_cod)

        item_desc = QTableWidgetItem(desc_text)
        item_desc.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        if desc_text:
            item_desc.setToolTip(desc_text.replace(" ; ", "\n"))
        self.tabella.setItem(row, _COL_INTERVENTO, item_desc)

        for col, (opzioni, default) in _COMBO_DEFS.items():
            combo = self._crea_combo(opzioni)
            field = {
                _COL_TIPO: "tipo_chirurgia",
                _COL_CPX: "complessita",
                _COL_URG: "urgenza",
            }[col]
            val = r.get(field, "").strip()
            idx = combo.findText(val)
            combo.setCurrentIndex(idx if idx >= 0 else combo.findText(default))
            combo.currentIndexChanged.connect(
                lambda _idx, c=col, rw=row: self._valida_riga(rw)
            )
            self.tabella.setCellWidget(row, col, combo)

        combo_dur = self._crea_combo(_DURATE_OPTIONS)
        dur_str = f"{total_dur} min"
        idx_dur = combo_dur.findText(dur_str)
        if idx_dur >= 0:
            combo_dur.setCurrentIndex(idx_dur)
        else:
            combo_dur.insertItem(0, dur_str)
            combo_dur.setCurrentIndex(0)
        combo_dur.currentTextChanged.connect(
            lambda text, rw=row: self._on_durata_totale_cambiata(rw, text)
        )
        self.tabella.setCellWidget(row, _COL_DUR, combo_dur)

        self._valida_riga(row)

    def _crea_combo(self, opzioni: list) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName("ComboDialog")
        combo.addItems(opzioni)
        return combo

    def _on_durata_totale_cambiata(self, row: int, text: str):
        """Mantiene coerenti durata totale e dettagli multi-intervento."""
        try:
            durata_totale = int(text.split()[0])
        except (ValueError, IndexError):
            return

        interventi = self._interventi_per_riga.get(row)
        if not interventi or durata_totale < len(interventi):
            return

        per_intervento, resto = divmod(durata_totale, len(interventi))
        for indice, intervento in enumerate(interventi):
            intervento["durata"] = per_intervento + (1 if indice < resto else 0)

    def _valida_riga(self, row: int):
        errori_col = set()

        nome_item = self.tabella.item(row, _COL_NOME)
        cogn_item = self.tabella.item(row, _COL_COGNOME)
        if not (nome_item and nome_item.text().strip()):
            errori_col.add(_COL_NOME)
        if not (cogn_item and cogn_item.text().strip()):
            errori_col.add(_COL_COGNOME)

        for col in [
            _COL_NOME,
            _COL_COGNOME,
            _COL_DIAG_CODICE,
            _COL_DIAG_DESCRIZIONE,
            _COL_CODICE,
            _COL_INTERVENTO,
        ]:
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

    def _on_cella_cambiata(self, row: int, col: int):
        if col in (_COL_CODICE, _COL_INTERVENTO):
            self._interventi_per_riga.pop(row, None)
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
            message = f"{totale} righe pronte per l'importazione"
        else:
            self.lbl_stato.setStyleSheet("font-size:13px; font-weight:bold; color:#b45309;")
            message = (
                f"{valide} righe valide, {n_err} con nome o cognome mancante "
                f"(in rosso). Le righe incomplete verranno saltate."
            )

        if self._import_context:
            message += f"\n{self._import_context}"
        self.lbl_stato.setText(message)

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

            def _txt(col, _row=row):
                it = self.tabella.item(_row, col)
                return it.text().strip() if it else ""

            def _combo(col, _row=row):
                w = self.tabella.cellWidget(_row, col)
                return w.currentText() if w else ""

            durata_str = _combo(_COL_DUR)
            try:
                durata = int(durata_str.split()[0])
            except (ValueError, IndexError):
                durata = 90

            # Ricostruisce dalle celle se l'anteprima è stata modificata.
            interventi = self._interventi_per_riga.get(row)
            if not interventi:
                codice = _txt(_COL_CODICE)
                desc   = _txt(_COL_INTERVENTO)
                codici   = [c.strip() for c in codice.split(";") if c.strip()]
                descrizi = [d.strip() for d in desc.split(";")   if d.strip()]
                n = max(len(codici), len(descrizi), 1)
                while len(codici)   < n: codici.append("")
                while len(descrizi) < n: descrizi.append("")
                dur_each, resto = divmod(max(durata, n), n)
                interventi = [
                    {
                        "codice": codici[i],
                        "descrizione": descrizi[i],
                        "durata": dur_each + (1 if i < resto else 0),
                    }
                    for i in range(n)
                ]

            primo = interventi[0] if interventi else {}

            pazienti.append({
                "nome":                   nome,
                "cognome":                cognome,
                "codice_diagnosi":        _txt(_COL_DIAG_CODICE),
                "descrizione_diagnosi":   _txt(_COL_DIAG_DESCRIZIONE),
                "diagnosi":               _txt(_COL_DIAG_DESCRIZIONE),
                "codice_intervento":      primo.get("codice", ""),
                "descrizione_intervento": primo.get("descrizione", ""),
                "interventi":             interventi,
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
