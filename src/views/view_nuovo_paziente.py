import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QMessageBox, QTextEdit
)
from PySide6.QtCore import Qt

class DialogNuovoPaziente(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nuovo Paziente")
        self.setFixedSize(450, 600) 
        self.setup_ui()
        self.load_styles()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        lbl_titolo = QLabel("Aggiungi Paziente")
        lbl_titolo.setObjectName("TitoloDialog")
        lbl_titolo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titolo)

        self.input_nome = QLineEdit()
        self.input_nome.setObjectName("InputDialog")
        self.input_nome.setPlaceholderText("Nome")
        layout.addWidget(self.input_nome)

        self.input_cognome = QLineEdit()
        self.input_cognome.setObjectName("InputDialog")
        self.input_cognome.setPlaceholderText("Cognome")
        layout.addWidget(self.input_cognome)

        self.input_codice = QLineEdit()
        self.input_codice.setObjectName("InputDialog")
        self.input_codice.setPlaceholderText("Codice Intervento (es. 38.12 TEA)")
        layout.addWidget(self.input_codice)

        self.combo_urgenza = QComboBox()
        self.combo_urgenza.setObjectName("ComboDialog")
        self.combo_urgenza.addItems(["Alta", "Media", "Bassa"])
        layout.addWidget(self.combo_urgenza)

        self.input_note = QTextEdit()
        self.input_note.setObjectName("InputNoteDialog")
        self.input_note.setPlaceholderText("Note Cliniche (Opzionale)...")
        layout.addWidget(self.input_note)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)

        self.btn_annulla = QPushButton("Annulla")
        self.btn_annulla.setObjectName("BtnAnnullaDialog")
        self.btn_annulla.setFixedHeight(45)
        self.btn_annulla.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_annulla.clicked.connect(self.reject)

        self.btn_salva = QPushButton("Salva")
        self.btn_salva.setObjectName("BtnSalvaDialog")
        self.btn_salva.setFixedHeight(45)
        self.btn_salva.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_salva.clicked.connect(self.valida_e_salva)

        btn_layout.addWidget(self.btn_annulla)
        btn_layout.addWidget(self.btn_salva)
        
        layout.addLayout(btn_layout)
        
    def valida_e_salva(self):
        """Valida i campi prima di permettere la chiusura del dialog"""
        nome = self.input_nome.text().strip()
        cognome = self.input_cognome.text().strip()
        codice = self.input_codice.text().strip()

        if not nome or not cognome or not codice:
            QMessageBox.warning(self, "Campi Incompleti", "Attenzione: Nome, Cognome e Codice Intervento sono campi obbligatori.")
            return 

        self.accept()

    def get_dati(self):
        """Ritorna un dizionario con i dati inseriti nel form"""
        return {
            "nome": self.input_nome.text().strip(),
            "cognome": self.input_cognome.text().strip(),
            "codice_intervento": self.input_codice.text().strip(),
            "urgenza": self.combo_urgenza.currentText(),
            "note": self.input_note.toPlainText().strip()
        }

    def load_styles(self):
        style_path = os.path.join("asset", "styles", "pazienti.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
