from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class ViewLibretto(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        titolo = QLabel("TODO")
        titolo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titolo.setStyleSheet("font-size: 24px; font-weight: bold; color: #333;")
        layout.addWidget(titolo)
