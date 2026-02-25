import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QHeaderView, QScroller,
    QStyledItemDelegate, QComboBox
)
from PySide6.QtCore import Qt, QTimer


class ComboBoxDelegate(QStyledItemDelegate):
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.addItem("-")
        editor.addItems(self.items)

        editor.setMaxVisibleItems(5)

        editor.setStyleSheet("""
            QComboBox {
                combobox-popup: 0; 

                background-color: #ffffff;
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 4px 8px;
                color: #212529;
                font-size: 15px;
            }
            QComboBox:focus {
                border: 2px solid #86b7fe;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
            }
            QComboBox QAbstractItemView {
                background-color: white;
                border: 1px solid #86b7fe;
                selection-background-color: #0d6efd;
                selection-color: white;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                min-height: 35px; 
                padding-left: 5px;
            }

            QComboBox QAbstractItemView QScrollBar:vertical {
                border: none;
                background: #f4f6f9;
                width: 10px;
                margin: 0px;
                border-radius: 5px;
            }
            QComboBox QAbstractItemView QScrollBar::handle:vertical {
                background: #adb5bd;
                min-height: 20px;
                border-radius: 5px;
            }
            QComboBox QAbstractItemView QScrollBar::handle:vertical:hover {
                background: #6c757d;
            }
            QComboBox QAbstractItemView QScrollBar::add-line:vertical, 
            QComboBox QAbstractItemView QScrollBar::sub-line:vertical {
                border: none;
                background: none;
                height: 0px;
            }
        """)

        editor.activated.connect(lambda: self.commit_and_close(editor))
        return editor

    def setEditorData(self, editor: QComboBox, index):
        cell_text = index.model().data(index, Qt.ItemDataRole.EditRole)

        if not cell_text or cell_text == "-":
            editor.setCurrentIndex(0)
        else:
            text_index = editor.findText(cell_text)
            if text_index >= 0:
                editor.setCurrentIndex(text_index)
            else:
                editor.setCurrentIndex(0)

        QTimer.singleShot(0, editor.showPopup)

    def setModelData(self, editor: QComboBox, model, index):
        selected_text = editor.currentText()
        if selected_text == "-":
            selected_text = ""

        model.setData(index, selected_text, Qt.ItemDataRole.EditRole)

    def commit_and_close(self, editor: QComboBox):
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QStyledItemDelegate.EndEditHint.NoHint)


class ViewScadenzario(QWidget):
    def __init__(self):
        super().__init__()

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.row_labels = [
            "Day", "Type", "Ward Shift I", "Ward Shift II",
            "OR I", "OR II", "Ward Round",
            "Day Hospital", "Day Surgery"
        ]

        self.btn_prev = None
        self.btn_mese_anno = None
        self.btn_next = None
        self.tabella = None

        self.setup_ui()
        self.load_styles()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(20)

        nav_layout = QHBoxLayout()

        self.btn_prev = QPushButton("❮")
        self.btn_prev.setObjectName("btnNav")
        self.btn_prev.setFixedSize(50, 50)
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_mese_anno = QPushButton()
        self.btn_mese_anno.setObjectName("btnMeseAnno")
        self.btn_mese_anno.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_next = QPushButton("❯")
        self.btn_next.setObjectName("btnNav")
        self.btn_next.setFixedSize(50, 50)
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)

        nav_layout.addStretch()
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_mese_anno)
        nav_layout.addWidget(self.btn_next)
        nav_layout.addStretch()

        main_layout.addLayout(nav_layout)

        self.tabella = QTableWidget()
        self.tabella.setRowCount(len(self.row_labels))
        self.tabella.setVerticalHeaderLabels(self.row_labels)

        self.tabella.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.tabella.horizontalHeader().setDefaultSectionSize(120)
        self.tabella.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.tabella.setWordWrap(True)
        self.tabella.setAlternatingRowColors(True)
        self.tabella.setEditTriggers(QTableWidget.EditTrigger.AllEditTriggers)

        QScroller.grabGesture(self.tabella.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)

        self.tabella.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.tabella.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)

        main_layout.addWidget(self.tabella)

    def load_styles(self):
        style_path = os.path.join("asset", "styles", "scadenzario.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        else:
            print(f"Warning: Unable to find the style file at {style_path}")
