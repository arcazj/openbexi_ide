"""Bounded output that lets readers stay on older text while a script runs."""
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QPlainTextEdit


class OutputConsole(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)

    def show_latest(self):
        cursor = self.textCursor()
        cursor.clearSelection()
        cursor.movePosition(QTextCursor.End)
        self.setTextCursor(cursor)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def append_output(self, content):
        vertical, horizontal = self.verticalScrollBar(), self.horizontalScrollBar()
        selection = self.textCursor()
        following = vertical.value() >= vertical.maximum() - 1 and not selection.hasSelection()
        old_scroll, old_horizontal = vertical.value(), horizontal.value()
        # Cursors track positions as the bounded document drops its oldest text.
        first = QTextCursor(self.firstVisibleBlock())
        old_block = first.blockNumber()
        selection.setKeepPositionOnInsert(True)
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(content)
        if self.document().characterCount() > 500_000:
            cursor.setPosition(0)
            cursor.setPosition(self.document().characterCount() - 400_000, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
        if following:
            self.show_latest()
        else:
            self.setTextCursor(selection)
            vertical.setValue(max(0, old_scroll - max(0, old_block - first.blockNumber())))
            horizontal.setValue(old_horizontal)
