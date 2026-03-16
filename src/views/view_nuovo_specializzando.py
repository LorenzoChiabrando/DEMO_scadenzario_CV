import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt

class DialogNuovoSpecializzando(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nuovo Specializzando")
        self.setFixedSize(450, 550) 
        self.setup_ui()
        self.load_styles()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # Titolo senza stili inline
        lbl_titolo = QLabel("Aggiungi Specializzando")
        lbl_titolo.setObjectName("TitoloDialog")
        lbl_titolo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titolo)

        # Nuovo Campo Matricola
        self.input_matricola = QLineEdit()
        self.input_matricola.setObjectName("InputDialog")
        self.input_matricola.setPlaceholderText("Matricola")
        layout.addWidget(self.input_matricola)

        # Campo Nome
        self.input_nome = QLineEdit()
        self.input_nome.setObjectName("InputDialog")
        self.input_nome.setPlaceholderText("Nome")
        layout.addWidget(self.input_nome)

        # Campo Cognome
        self.input_cognome = QLineEdit()
        self.input_cognome.setObjectName("InputDialog")
        self.input_cognome.setPlaceholderText("Cognome")
        layout.addWidget(self.input_cognome)

        # Menu a tendina Livello
        self.combo_livello = QComboBox()
        self.combo_livello.setObjectName("ComboDialog")
        self.combo_livello.addItems(["Junior", "Senior"])
        layout.addWidget(self.combo_livello)

        # Menu a tendina Stato
        self.combo_stato = QComboBox()
        self.combo_stato.setObjectName("ComboDialog")
        self.combo_stato.addItems(["Molinette", "Altra Sede", "Storico"])
        layout.addWidget(self.combo_stato)

        layout.addStretch()

        # Bottoni
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
        matricola = self.input_matricola.text().strip()
        nome = self.input_nome.text().strip()
        cognome = self.input_cognome.text().strip()

        if not matricola or not nome or not cognome:
            QMessageBox.warning(self, "Campi Incompleti", "Attenzione: Nome, Cognome e Matricola sono campi obbligatori.")
            return 

        self.accept()

    def get_dati(self):
        """Ritorna un dizionario con i dati inseriti nel form"""
        return {
            "matricola": self.input_matricola.text().strip(),
            "nome": self.input_nome.text().strip(),
            "cognome": self.input_cognome.text().strip(),
            "livello": self.combo_livello.currentText(),
            "stato": self.combo_stato.currentText()
        }

    def load_styles(self):
        style_path = os.path.join("asset", "styles", "libretto.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
