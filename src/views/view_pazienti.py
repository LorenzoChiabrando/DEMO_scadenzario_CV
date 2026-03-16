import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QCheckBox, QListWidget, QPushButton, QFrame, QGraphicsDropShadowEffect,
    QStackedWidget, QGridLayout, QTextEdit
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor, QIcon, QPixmap

class ViewPazienti(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setup_ui()
        self.load_styles()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        self.page_lista = QWidget()
        lista_layout = QVBoxLayout(self.page_lista)
        lista_layout.setContentsMargins(40, 40, 40, 40)
        lista_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.card_container = QFrame()
        self.card_container.setObjectName("MainCard")
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 20))
        shadow.setOffset(0, 5)
        self.card_container.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.card_container)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(20) 

        titolo = QLabel("Pazienti in Lista d'Attesa")
        titolo.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        titolo.setStyleSheet("color: #1e293b; letter-spacing: 1px;")
        card_layout.addWidget(titolo)

        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 15, 0, 20)
        
        self.search_container = QFrame()
        self.search_container.setObjectName("SearchContainer")
        self.search_container.setFixedHeight(75) 
        
        container_layout = QHBoxLayout(self.search_container)
        container_layout.setContentsMargins(25, 0, 20, 0) 
        container_layout.setSpacing(15)

        self.lbl_search_icon = QLabel()
        self.lbl_search_icon.setObjectName("SearchIcon")
        if os.path.exists("asset/images/libretto/search.png"):
            pixmap = QPixmap("asset/images/libretto/search.png").scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.lbl_search_icon.setPixmap(pixmap)
        else:
            self.lbl_search_icon.setText("Cerca:")
            self.lbl_search_icon.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))

        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("SearchBar")
        self.search_bar.setPlaceholderText("Cerca per nome, cognome o codice intervento...")
        
        container_layout.addWidget(self.lbl_search_icon)
        container_layout.addWidget(self.search_bar)
        
        search_layout.addWidget(self.search_container)
        card_layout.addLayout(search_layout)

        filtri_layout = QHBoxLayout()
        filtri_layout.setSpacing(20)
        
        lbl_filtri = QLabel("Filtra per urgenza:")
        lbl_filtri.setObjectName("LblFiltri")
        filtri_layout.addWidget(lbl_filtri)

        self.chk_urg_alta = QCheckBox("Alta (A)")
        self.chk_urg_media = QCheckBox("Media (B)")
        self.chk_urg_bassa = QCheckBox("Bassa (C)")

        for chk in [self.chk_urg_alta, self.chk_urg_media, self.chk_urg_bassa]:
            chk.setCursor(Qt.CursorShape.PointingHandCursor)
            chk.setChecked(True) 
            filtri_layout.addWidget(chk)

        filtri_layout.addStretch()
        card_layout.addLayout(filtri_layout)

        card_layout.addSpacing(10)

        body_layout = QHBoxLayout()
        body_layout.setSpacing(30)

        self.lista_risultati = QListWidget()
        self.lista_risultati.setObjectName("ListaRisultati")
        self.lista_risultati.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lista_risultati.setSpacing(8)
        
        self._original_list_mousePressEvent = self.lista_risultati.mousePressEvent
        def custom_list_mousePressEvent(event):
            if not self.lista_risultati.itemAt(event.pos()):
                self.lista_risultati.clearSelection()
            self._original_list_mousePressEvent(event)
        self.lista_risultati.mousePressEvent = custom_list_mousePressEvent

        body_layout.addWidget(self.lista_risultati, stretch=7)

        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(20)

        self.btn_apri = QPushButton("Dettaglio Paziente")
        self.btn_apri.setObjectName("BtnApri")
        self.btn_apri.setFixedHeight(60)
        self.btn_apri.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apri.setEnabled(False)

        self.btn_aggiungi = QPushButton(" Nuovo Paziente")
        self.btn_aggiungi.setObjectName("BtnAggiungi")
        self.btn_aggiungi.setFixedHeight(60)
        self.btn_aggiungi.setCursor(Qt.CursorShape.PointingHandCursor)
        
        icona_plus = QIcon("asset/images/libretto/plus.png") 
        self.btn_aggiungi.setIcon(icona_plus)
        self.btn_aggiungi.setIconSize(QSize(28, 28))

        btn_layout.addWidget(self.btn_apri)
        btn_layout.addWidget(self.btn_aggiungi)
        btn_layout.addStretch()

        body_layout.addLayout(btn_layout, stretch=3)
        card_layout.addLayout(body_layout)
        lista_layout.addWidget(self.card_container)
        
        self.stacked_widget.addWidget(self.page_lista)

        self.page_dettaglio = QWidget()
        dettaglio_layout = QVBoxLayout(self.page_dettaglio)
        dettaglio_layout.setContentsMargins(40, 30, 40, 30)
        dettaglio_layout.setSpacing(20)

        nav_layout = QHBoxLayout()
        self.btn_indietro = QPushButton("Indietro")
        self.btn_indietro.setObjectName("BtnIndietro")
        self.btn_indietro.setFixedSize(220, 45)
        self.btn_indietro.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.lbl_nome_paziente = QLabel("Dettaglio Paziente")
        self.lbl_nome_paziente.setObjectName("TitoloPagina")
        self.lbl_nome_paziente.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        nav_layout.addWidget(self.btn_indietro)
        nav_layout.addStretch()
        nav_layout.addWidget(self.lbl_nome_paziente)

        dettaglio_layout.addLayout(nav_layout)

        card_dettaglio = QFrame()
        card_dettaglio.setObjectName("CardDettaglio")
        card_dettaglio_layout = QVBoxLayout(card_dettaglio)
        card_dettaglio_layout.setContentsMargins(40, 40, 40, 40)
        card_dettaglio_layout.setSpacing(25)

        grid_info = QGridLayout()
        grid_info.setSpacing(20)

        lbl_codice = QLabel("Codice Intervento:")
        lbl_codice.setObjectName("LblInfo")
        self.val_codice = QLabel("-")
        self.val_codice.setObjectName("ValInfo")

        lbl_urgenza = QLabel("Classe di Urgenza:")
        lbl_urgenza.setObjectName("LblInfo")
        self.val_urgenza = QLabel("-")
        self.val_urgenza.setObjectName("ValInfoUrgenza")

        lbl_data = QLabel("Data Inserimento in Lista:")
        lbl_data.setObjectName("LblInfo")
        self.val_data = QLabel("-")
        self.val_data.setObjectName("ValInfo")

        grid_info.addWidget(lbl_codice, 0, 0)
        grid_info.addWidget(self.val_codice, 0, 1)
        grid_info.addWidget(lbl_urgenza, 1, 0)
        grid_info.addWidget(self.val_urgenza, 1, 1)
        grid_info.addWidget(lbl_data, 2, 0)
        grid_info.addWidget(self.val_data, 2, 1)

        card_dettaglio_layout.addLayout(grid_info)

        lbl_note = QLabel("Note Cliniche / Preparazione:")
        lbl_note.setObjectName("LblInfo")
        card_dettaglio_layout.addWidget(lbl_note)

        self.txt_note = QTextEdit()
        self.txt_note.setObjectName("TxtNote")
        self.txt_note.setReadOnly(True)
        card_dettaglio_layout.addWidget(self.txt_note)

        dettaglio_layout.addWidget(card_dettaglio)
        self.stacked_widget.addWidget(self.page_dettaglio)

    def load_styles(self):
        style_path = os.path.join("asset", "styles", "pazienti.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(self.styleSheet() + "\n" + f.read())

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self.stacked_widget.currentIndex() == 0:
            self.lista_risultati.clearSelection()
