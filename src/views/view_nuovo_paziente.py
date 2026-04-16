import os
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QLineEdit, QComboBox, QPushButton, QMessageBox, QTextEdit
)
from PySide6.QtCore import Qt


class DialogNuovoPaziente(QDialog):
    def __init__(self, parent=None, paziente_dati=None):
        super().__init__(parent)
        self._paz_dati = paziente_dati
        self._edit_mode = paziente_dati is not None
        self.setWindowTitle("Modifica Paziente" if self._edit_mode else "Nuovo Paziente")
        self.setMinimumWidth(500)
        self.setSizeGripEnabled(False)
        self.setup_ui()
        if self._edit_mode:
            self._precompila()
        self.load_styles()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(16)

        # Titolo
        lbl_titolo = QLabel("Modifica Paziente" if self._edit_mode else "Aggiungi Paziente")
        lbl_titolo.setObjectName("TitoloDialog")
        lbl_titolo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titolo)

        lbl_sub = QLabel(
            "Modifica le informazioni del paziente." if self._edit_mode
            else "Inserisci i dati del nuovo paziente in lista d'attesa."
        )
        lbl_sub.setObjectName("SottoTitoloDialog")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_sub)

        sep = QFrame()
        sep.setObjectName("SeparatoreDialog")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # Campi
        layout.addWidget(self._campo("NOME", "input_nome", "Es. Mario"))
        layout.addWidget(self._campo("COGNOME", "input_cognome", "Es. Rossi"))
        layout.addWidget(self._campo("CODICE INTERVENTO", "input_codice", "Es. 38.12 TEA carotidea"))

        # Combo urgenza + stato (riga affiancata)
        urg_stato_row = QHBoxLayout()
        urg_stato_row.setSpacing(16)

        grp_urg = QVBoxLayout()
        grp_urg.setSpacing(4)
        lbl_urg = QLabel("CLASSE DI URGENZA")
        lbl_urg.setObjectName("LblCampo")
        self.combo_urgenza = QComboBox()
        self.combo_urgenza.setObjectName("ComboDialog")
        self.combo_urgenza.addItems(["Alta", "Media", "Bassa"])
        self.combo_urgenza.setFixedHeight(44)
        grp_urg.addWidget(lbl_urg)
        grp_urg.addWidget(self.combo_urgenza)

        grp_sta = QVBoxLayout()
        grp_sta.setSpacing(4)
        lbl_sta = QLabel("STATO")
        lbl_sta.setObjectName("LblCampo")
        self.combo_stato = QComboBox()
        self.combo_stato.setObjectName("ComboDialog")
        self.combo_stato.addItems(["In Attesa", "Completato"])
        self.combo_stato.setFixedHeight(44)
        grp_sta.addWidget(lbl_sta)
        grp_sta.addWidget(self.combo_stato)

        urg_stato_row.addLayout(grp_urg)
        urg_stato_row.addLayout(grp_sta)
        layout.addLayout(urg_stato_row)

        # Note
        grp_note = QVBoxLayout()
        grp_note.setSpacing(4)
        lbl_note = QLabel("NOTE CLINICHE (opzionale)")
        lbl_note.setObjectName("LblCampo")
        self.input_note = QTextEdit()
        self.input_note.setObjectName("NoteDialog")
        self.input_note.setPlaceholderText("Preparazione, allergie, note operative...")
        self.input_note.setFixedHeight(90)
        grp_note.addWidget(lbl_note)
        grp_note.addWidget(self.input_note)
        layout.addLayout(grp_note)

        # Bottoni
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_annulla = QPushButton("Annulla")
        self.btn_annulla.setObjectName("BtnAnnullaDialog")
        self.btn_annulla.setFixedHeight(44)
        self.btn_annulla.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_annulla.clicked.connect(self.reject)

        self.btn_salva = QPushButton(
            "Salva Modifiche" if self._edit_mode else "Salva Paziente"
        )
        self.btn_salva.setObjectName("BtnSalvaDialog")
        self.btn_salva.setFixedHeight(44)
        self.btn_salva.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_salva.clicked.connect(self._valida_e_salva)

        btn_layout.addWidget(self.btn_annulla)
        btn_layout.addWidget(self.btn_salva)
        layout.addLayout(btn_layout)

    def _campo(self, etichetta, attr_name, placeholder):
        grp = QWidget()
        grp_layout = QVBoxLayout(grp)
        grp_layout.setContentsMargins(0, 0, 0, 0)
        grp_layout.setSpacing(4)
        lbl = QLabel(etichetta)
        lbl.setObjectName("LblCampo")
        inp = QLineEdit()
        inp.setObjectName("InputDialog")
        inp.setPlaceholderText(placeholder)
        inp.setFixedHeight(44)
        setattr(self, attr_name, inp)
        grp_layout.addWidget(lbl)
        grp_layout.addWidget(inp)
        return grp

    def _precompila(self):
        self.input_nome.setText(self._paz_dati.get("nome", ""))
        self.input_cognome.setText(self._paz_dati.get("cognome", ""))
        self.input_codice.setText(self._paz_dati.get("codice_intervento", ""))
        idx = self.combo_urgenza.findText(self._paz_dati.get("urgenza", ""))
        if idx >= 0:
            self.combo_urgenza.setCurrentIndex(idx)
        idx2 = self.combo_stato.findText(self._paz_dati.get("stato", "In Attesa"))
        if idx2 >= 0:
            self.combo_stato.setCurrentIndex(idx2)
        self.input_note.setPlainText(self._paz_dati.get("note", ""))

    def _valida_e_salva(self):
        nome = self.input_nome.text().strip()
        cognome = self.input_cognome.text().strip()
        codice = self.input_codice.text().strip()
        if not nome or not cognome or not codice:
            QMessageBox.warning(
                self, "Campi Incompleti",
                "Nome, Cognome e Codice Intervento sono obbligatori."
            )
            return
        self.accept()

    def get_dati(self):
        return {
            "nome": self.input_nome.text().strip(),
            "cognome": self.input_cognome.text().strip(),
            "codice_intervento": self.input_codice.text().strip(),
            "urgenza": self.combo_urgenza.currentText(),
            "stato": self.combo_stato.currentText(),
            "note": self.input_note.toPlainText().strip(),
        }

    def load_styles(self):
        style_path = os.path.join("asset", "styles", "pazienti.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
