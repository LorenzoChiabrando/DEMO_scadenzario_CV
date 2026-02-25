import os
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QSizePolicy
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt


class Sidebar(QWidget):
    def __init__(self):
        super().__init__()

        self.setFixedWidth(250)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: #2b3035;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 15)
        layout.setSpacing(0)

        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 30, 10, 30)

        self.logo_label = QLabel()
        logo_path = os.path.join("asset", "images", "logo_sigillo.svg")
        logo_pixmap = QPixmap(logo_path)

        if not logo_pixmap.isNull():
            scaled_pixmap = logo_pixmap.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(scaled_pixmap)
        else:
            self.logo_label.setText("[ LOGO ]")
            self.logo_label.setStyleSheet("color: #86b7fe; font-weight: bold; font-size: 16px;")

        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.logo_label)

        self.title_label = QLabel("CV - Demo Mockup")
        self.title_label.setStyleSheet("color: white; font-size: 18px; font-weight: bold; margin-top: 15px;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.title_label)

        layout.addWidget(header_widget)

        self.menu_list = QListWidget()
        self.menu_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        style_path = os.path.join("asset", "styles", "sidebar.qss")
        if os.path.exists(style_path):
            with open(style_path, "r") as f:
                self.menu_list.setStyleSheet(f.read())
        else:
            print(f"Attenzione: Impossibile trovare il file di stile in {style_path}")

        self.menu_list.addItems([
            "Scadenzario Mensile",
            "Sale Operatorie",
            "Libretto Carriere"
        ])

        layout.addWidget(self.menu_list)

        self.footer_label = QLabel("@UNITO 2026")
        self.footer_label.setStyleSheet("color: #6c757d; font-size: 12px;")
        self.footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.footer_label)

    @property
    def currentRowChanged(self):
        return self.menu_list.currentRowChanged

    def setCurrentRow(self, row):
        self.menu_list.setCurrentRow(row)
