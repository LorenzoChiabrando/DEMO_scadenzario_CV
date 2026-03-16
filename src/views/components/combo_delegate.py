from PySide6.QtWidgets import QStyledItemDelegate, QComboBox
from PySide6.QtCore import Qt, QTimer

class ComboBoxDelegate(QStyledItemDelegate):
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.addItem("-")
        editor.addItems(self.items)
				# forza massimo 5 elementi visibili
        editor.setMaxVisibleItems(5)

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
                
        QTimer.singleShot(50, editor.showPopup)

    def setModelData(self, editor: QComboBox, model, index):
        selected_text = editor.currentText()
        if selected_text == "-":
            selected_text = ""
        model.setData(index, selected_text, Qt.ItemDataRole.EditRole)

    def commit_and_close(self, editor: QComboBox):
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QStyledItemDelegate.EndEditHint.NoHint)
