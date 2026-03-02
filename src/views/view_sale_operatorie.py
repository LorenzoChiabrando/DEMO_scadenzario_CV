from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QHeaderView, QTableWidgetItem
from PySide6.QtCore import Qt


class ViewSaleOperatorie(QWidget):
    def __init__(self):
        super().__init__()
        # give the widget a styled background so style sheets apply
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(20)

        titolo = QLabel("Sale Operatorie Settimanali")
        titolo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(titolo)

        # table representing weekly operating room schedule
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        headers = [
            "Lunedì\nSpecializzando A\nSpecializzando B",
            "Martedì\nSpecializzando C\nSpecializzando D",
            "Mercoledì\nSpecializzando A\nSpecializzando B",
            "Giovedì\nSpecializzando F\nSpecializzando E",
            "Venerdì\nSpecializzando C\nSpecializzando E",
        ]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)

        # three example time slots pulled from the image
        self.table.setRowCount(6)

        # make headers stretch to fill available space
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.table.setWordWrap(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.table.setRowHeight(0, 120)
        self.table.setRowHeight(1, 120)
        self.table.setRowHeight(2, 170)
        self.table.setRowHeight(3, 80)
        self.table.setRowHeight(4, 100)
        self.table.setRowHeight(5, 90)

        # Colonna 0 (Lunedì)
        # La prima cella copre riga 0 e 1
        self.table.setSpan(0, 3, 2, 1)

        # populate some cells with the example text
        self.table.setItem(0, 0, QTableWidgetItem("8-10: paziente A\ndiagnosi 1\nintervento x.y\nchirurgo R"))
        self.table.setItem(1, 0, QTableWidgetItem("10-12: paziente B\ndiagnosi 4\nintervento xx.yy\nchirurgo S"))

        self.table.setItem(0, 1, QTableWidgetItem("8-10: paziente C\ndiagnosi 2\nintervento z.x\nchirurgo S"))
        self.table.setItem(1, 1, QTableWidgetItem("10-12: paziente D\ndiagnosi 2\nintervento x.z\nchirurgo S"))
        self.table.setItem(2, 1, QTableWidgetItem("14-16: paziente E\ndiagnosi 1\nintervento x.y\nchirurgo T"))

        self.table.setItem(0, 2, QTableWidgetItem("8-10: paziente G\ndiagnosi 4\nintervento x.z\nchirurgo S"))
        self.table.setItem(1, 2, QTableWidgetItem("10-12: paziente H\ndiagnosi 3\nintervento x.y\nchirurgo R"))

        main_layout.addWidget(self.table)

        # apply the same stylesheet used by the scadenzario view
        self.load_styles()

    def load_styles(self):
        import os
        style_path = os.path.join("asset", "styles", "scadenzario.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        else:
            print(f"Warning: Unable to find the style file at {style_path}")
