import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QStackedWidget
from src.views.view_sidebar import Sidebar
from src.views.view_scadenzario import ViewScadenzario
from src.views.view_sale_operatorie import ViewSaleOperatorie
from src.views.view_libretto import ViewLibretto
from src.models.data_manager import DataManager
from src.controllers.controller_scadenzario import ControllerScadenzario


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.view_scad = None
        self.controller_scad = None
        self.data_manager = None
        self.setWindowTitle("MMSD CV - Demo Mockup")
        self.resize(1024, 768)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = Sidebar()
        main_layout.addWidget(self.sidebar)

        self.body_stack = QStackedWidget()
        main_layout.addWidget(self.body_stack)

        self.init_pages()

        self.sidebar.currentRowChanged.connect(self.body_stack.setCurrentIndex)
        self.sidebar.setCurrentRow(0)

    def init_pages(self):
        self.data_manager = DataManager()
        self.view_scad = ViewScadenzario()
        self.controller_scad = ControllerScadenzario(self.view_scad, self.data_manager)

        self.body_stack.addWidget(self.view_scad)
        self.body_stack.addWidget(ViewSaleOperatorie())
        self.body_stack.addWidget(ViewLibretto())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
