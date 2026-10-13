"""A read-only copy of shared debugger source, separate from editable files."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from .editor import CodeEditor


class SourceView(QDialog):
    def __init__(self, result, colors, line, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(('Captured source' if result['captured'] else 'Shared source copy')
                            + ' · ' + result['path'])
        self.resize(840, 620)
        layout = QVBoxLayout(self)
        label = QLabel('Read-only source from this procedure. SHA-256: ' + result['sha256'])
        label.setTextFormat(Qt.PlainText)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.editor = CodeEditor(Path(result['path']), colors,
                                 payload=result['text'].encode('utf-8'), encoding='utf-8')
        # HTTP decoded the declared Python encoding; the view itself is UTF-8.
        self.editor.setPlainText(result['text'].replace('\r\n', '\n'))
        self.editor.document().setModified(False)
        self.editor.setReadOnly(True)
        self.editor.show_execution_line(line)
        layout.addWidget(self.editor)
        close = QPushButton('Close')
        close.clicked.connect(self.close)
        layout.addWidget(close)
