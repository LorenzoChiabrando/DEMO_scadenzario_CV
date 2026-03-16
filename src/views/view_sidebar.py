import os
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QSizePolicy, QListWidgetItem
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtCore import Qt

class Sidebar(QWidget):
    def __init__(self):
        super().__init__()

        self.setObjectName("SidebarMain")
        self.setFixedWidth(270)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 20)
        layout.setSpacing(0)

        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(15, 40, 15, 30)
        header_layout.setSpacing(15)

        self.logo_label = QLabel()
        logo_path = os.path.join("asset", "images", "logo_sigillo.svg")
        logo_pixmap = QPixmap(logo_path)

        if not logo_pixmap.isNull():
            scaled_pixmap = logo_pixmap.scaled(110, 110, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(scaled_pixmap)

        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.logo_label)

        self.title_label = QLabel("MMSD CV\nDemo Mockup")
        self.title_label.setObjectName("SidebarTitle")
        self.title_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.title_label)

        layout.addWidget(header_widget)

        self.menu_list = QListWidget()
        self.menu_list.setObjectName("SidebarMenu")
        self.menu_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.menu_list.setCursor(Qt.CursorShape.PointingHandCursor)

        voci_menu = [
            "Scadenzario Mensile",
            "Sale Operatorie",
            "Libretto Carriere",
            "Lista Pazienti"
        ]

        for voce in voci_menu:
            item = QListWidgetItem(voce)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.menu_list.addItem(item)

        layout.addWidget(self.menu_list)

        self.footer_label = QLabel("© UNITO 2026\nChirurgia Vascolare")
        self.footer_label.setObjectName("SidebarFooter")
        self.footer_label.setFont(QFont("Segoe UI", 11))
        self.footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.footer_label)

        self.load_styles()

    @property
    def currentRowChanged(self):
        return self.menu_list.currentRowChanged

    def setCurrentRow(self, row):
        self.menu_list.setCurrentRow(row)

    def load_styles(self):
        style_path = os.path.join("asset", "styles", "sidebar.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(self.styleSheet() + "\n" + f.read())
