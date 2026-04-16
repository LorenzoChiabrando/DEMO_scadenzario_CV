import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QScroller,
    QStackedWidget, QLabel, QSizePolicy, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QColor, QFont


class ViewSaleOperatorie(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.row_labels = [
            "Giorno", "Specializzandi", "8.00-10.00", "10.00-12.00", "14.00-16.00", "16.00-18.00"
        ]

        self.setup_ui()
        self.load_styles()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        self.page_selezione = QWidget()
        selezione_layout = QVBoxLayout(self.page_selezione)
        selezione_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        selezione_layout.setSpacing(50)
        selezione_layout.setContentsMargins(50, 50, 50, 50)

        titolo_selezione = QLabel("GESTIONE SALE OPERATORIE")
        titolo_selezione.setObjectName("TitoloSelezione")
        titolo_selezione.setAlignment(Qt.AlignmentFlag.AlignCenter)
        selezione_layout.addWidget(titolo_selezione)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(40)
        cards_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_storico = self.crea_card(
            "Storico",
            "Consultazione settimane passate e consolidate\n(Sola lettura)",
            "asset/images/scadenzario/icona_storico.png"
        )
        self.btn_corrente = self.crea_card(
            "Settimana Corrente",
            "Pianificazione settimana\nproposta",
            "asset/images/scadenzario/icona_corrente.png"
        )
        self.btn_pianificazione = self.crea_card(
            "Pianificazione",
            "Eventuali modifiche per\n la settimana corrente",
            "asset/images/scadenzario/icona_pianificazione.png"
        )

        cards_layout.addWidget(self.btn_storico)
        cards_layout.addWidget(self.btn_corrente)
        cards_layout.addWidget(self.btn_pianificazione)

        selezione_layout.addLayout(cards_layout)
        self.stacked_widget.addWidget(self.page_selezione)

        self.page_calendario = QWidget()
        calendario_layout = QVBoxLayout(self.page_calendario)
        calendario_layout.setContentsMargins(30, 20, 30, 30)
        calendario_layout.setSpacing(20)

        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(0, 0, 0, 10)

        self.btn_indietro = QPushButton("Indietro")
        self.btn_indietro.setObjectName("BtnIndietroSaleOperatorie")
        self.btn_indietro.setFixedSize(220, 45)
        self.btn_indietro.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_prev = QPushButton("<")
        self.btn_prev.setObjectName("btnNav")
        self.btn_prev.setFixedSize(50, 50)
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        sp_prev = self.btn_prev.sizePolicy()
        sp_prev.setRetainSizeWhenHidden(True)
        self.btn_prev.setSizePolicy(sp_prev)

        self.btn_mese_anno = QPushButton()
        self.btn_mese_anno.setObjectName("btnMeseAnno")
        self.btn_mese_anno.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_next = QPushButton(">")
        self.btn_next.setObjectName("btnNav")
        self.btn_next.setFixedSize(50, 50)
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        sp_next = self.btn_next.sizePolicy()
        sp_next.setRetainSizeWhenHidden(True)
        self.btn_next.setSizePolicy(sp_next)

        self.lbl_modalita = QLabel("")
        self.lbl_modalita.setObjectName("LblModalita")
        self.lbl_modalita.setAlignment(Qt.AlignmentFlag.AlignCenter)

        nav_layout.addWidget(self.btn_indietro)
        nav_layout.addStretch()
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_mese_anno)
        nav_layout.addWidget(self.btn_next)
        nav_layout.addStretch()
        nav_layout.addWidget(self.lbl_modalita)

        calendario_layout.addLayout(nav_layout)

        self.tabella = QTableWidget()
        self.tabella.setRowCount(len(self.row_labels))
        self.tabella.setVerticalHeaderLabels(self.row_labels)

        self.tabella.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.tabella.horizontalHeader().setDefaultSectionSize(240)

        self.tabella.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabella.verticalHeader().setMinimumSectionSize(55)

        self.tabella.horizontalHeader().setSectionsClickable(False)
        self.tabella.verticalHeader().setSectionsClickable(False)
        self.tabella.horizontalHeader().setHighlightSections(False)
        self.tabella.verticalHeader().setHighlightSections(False)
        self.tabella.setCornerButtonEnabled(False)

        self.tabella.setWordWrap(True)
        self.tabella.setAlternatingRowColors(True)

        QScroller.grabGesture(self.tabella.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        self.tabella.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.tabella.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)

        calendario_layout.addWidget(self.tabella)

        self.stacked_widget.addWidget(self.page_calendario)

    def crea_card(self, titolo, descrizione, icon_path):
        btn = QPushButton()
        btn.setObjectName("CardButton")
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        btn.setMinimumSize(250, 250)
        btn.setMaximumSize(400, 350)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 30))
        shadow.setOffset(0, 10)
        btn.setGraphicsEffect(shadow)

        layout = QVBoxLayout(btn)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(20, 30, 20, 30)
        layout.setSpacing(15)

        lbl_icona = QLabel()
        lbl_icona.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            pixmap = pixmap.scaled(90, 90, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            lbl_icona.setPixmap(pixmap)

        lbl_titolo = QLabel(titolo)
        lbl_titolo.setObjectName("CardTitolo")
        lbl_titolo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_desc = QLabel(descrizione)
        lbl_desc.setObjectName("CardDescrizione")
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_desc.setWordWrap(True)

        layout.addStretch()
        layout.addWidget(lbl_icona)
        layout.addWidget(lbl_titolo)
        layout.addWidget(lbl_desc)
        layout.addStretch()

        return btn

    def crea_item_giorno(self, nome_giorno, is_festivo):
        """Restituisce un QTableWidgetItem stilizzato per la riga del giorno."""
        item = QTableWidgetItem(nome_giorno)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setBackground(QColor("#f1f5f9") if is_festivo else QColor(Qt.GlobalColor.transparent))
        item.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        item.setForeground(QColor("#64748b"))
        return item

    def crea_item_cella(self, valore, is_festivo):
        """Restituisce un QTableWidgetItem stilizzato per una cella dati."""
        item = QTableWidgetItem(valore)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setBackground(QColor("#f1f5f9") if is_festivo else QColor(Qt.GlobalColor.transparent))
        item.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        if is_festivo:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setForeground(QColor("#cbd5e1"))
        else:
            item.setForeground(QColor("#1e293b"))
        return item

    def load_styles(self):
        style_path = os.path.join("asset", "styles", "sale_operatorie.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(self.styleSheet() + "\n" + f.read())

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if hasattr(self, 'tabella'):
            self.tabella.viewport().update()
            self.tabella.horizontalHeader().viewport().update()
            self.tabella.verticalHeader().viewport().update()
