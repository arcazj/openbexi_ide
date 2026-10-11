"""Native text editor with line numbers, breakpoints and existing Python lexer."""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import tempfile
import tokenize
import stat

from pygments.lexers import PythonLexer
from pygments.token import Token
from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QSyntaxHighlighter, QTextCharFormat, QTextFormat
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget
from .fonts import fixed_font


class FileConflictError(OSError):
    """The file changed outside this editor since it was opened or saved."""


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document, colors):
        super().__init__(document)
        self.colors = colors
        self.lexer = PythonLexer()

    def highlightBlock(self, text):
        for offset, kind, value in self.lexer.get_tokens_unprocessed(text):
            key = ("keyword" if kind in Token.Keyword else "string" if kind in Token.Literal.String
                   else "comment" if kind in Token.Comment else "number" if kind in Token.Literal.Number
                   else None)
            if key:
                fmt = QTextCharFormat()
                fmt.setForeground(QColor(self.colors[key]))
                self.setFormat(offset, len(value), fmt)


class Gutter(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_gutter(event)

    def mousePressEvent(self, event):
        block = self.editor.firstVisibleBlock()
        while block.isValid():
            top = self.editor.blockBoundingGeometry(block).translated(self.editor.contentOffset()).top()
            height = self.editor.blockBoundingRect(block).height()
            if top <= event.position().y() < top + height:
                self.editor.toggle_breakpoint(block.blockNumber() + 1)
                return
            block = block.next()


class CodeEditor(QPlainTextEdit):
    breakpoints_changed = Signal()

    def __init__(self, path: Path, colors, parent=None):
        super().__init__(parent)
        self.path = path.resolve()
        payload = self.path.read_bytes()
        if len(payload) > 2_000_000:
            raise ValueError("This editor supports text files up to 2 MB")
        self.encoding = tokenize.detect_encoding(io.BytesIO(payload).readline)[0]
        self.newline = "\r\n" if b"\r\n" in payload else "\n"
        self.disk_hash = hashlib.sha256(payload).digest()
        self.colors = colors
        self.breakpoints: set[int] = set()
        self.verified_breakpoints: dict[int, bool] = {}
        self.execution_line: int | None = None
        self.gutter = Gutter(self)
        self.setFont(fixed_font())
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setPlainText(payload.decode(self.encoding).replace("\r\n", "\n"))
        self.document().setModified(False)
        self.highlighter = PythonHighlighter(self.document(), colors)
        self.blockCountChanged.connect(self.update_margin)
        self.updateRequest.connect(self.update_gutter)
        self.cursorPositionChanged.connect(self.highlight_line)
        self.update_margin()
        self.highlight_line()

    def gutter_width(self):
        return 28 + self.fontMetrics().horizontalAdvance("9") * max(2, len(str(self.blockCount())))

    def update_margin(self, *_):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def update_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_margin()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = self.contentsRect()
        self.gutter.setGeometry(QRect(rect.left(), rect.top(), self.gutter_width(), rect.height()))

    def paint_gutter(self, event):
        painter = QPainter(self.gutter)
        painter.fillRect(event.rect(), QColor(self.colors["gutter"]))
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height = round(self.blockBoundingRect(block).height())
            number = block.blockNumber() + 1
            if block.isVisible() and top + height >= event.rect().top():
                painter.setPen(QColor(self.colors["muted"]))
                painter.drawText(20, top, self.gutter.width() - 25, height, Qt.AlignRight, str(number))
                if number in self.breakpoints:
                    if self.verified_breakpoints.get(number) is False:
                        painter.setBrush(Qt.NoBrush); painter.setPen(QPen(QColor("#dc626a"), 1.5))
                    else:
                        painter.setBrush(QColor("#dc626a")); painter.setPen(Qt.NoPen)
                    painter.drawEllipse(6, top + max(2, (height - 9) // 2), 9, 9)
                if number == self.execution_line:
                    painter.setPen(QColor(self.colors["accent"]))
                    painter.drawText(3, top, 16, height, Qt.AlignCenter, "›")
            block = block.next()
            top += height

    def toggle_breakpoint(self, line: int):
        if line in self.breakpoints:
            self.breakpoints.remove(line)
        else:
            self.breakpoints.add(line)
        self.gutter.update()
        self.breakpoints_changed.emit()

    def highlight_line(self):
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor(self.colors["selected"]))
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])

    def show_execution_line(self, line: int | None):
        self.execution_line = line
        if line:
            cursor = self.textCursor()
            cursor.setPosition(self.document().findBlockByNumber(line - 1).position())
            self.setTextCursor(cursor)
            self.centerCursor()
        self.gutter.update()

    def set_colors(self, colors):
        self.colors = colors
        self.highlighter.colors = colors
        self.highlighter.rehighlight()
        self.highlight_line()
        self.gutter.update()

    def save(self, force=False):
        if not force and (not self.path.exists() or hashlib.sha256(self.path.read_bytes()).digest() != self.disk_hash):
            raise FileConflictError("The file changed outside the IDE. Review before overwriting.")
        payload = self.toPlainText().replace("\n", self.newline).encode(self.encoding)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as stream:
                temp_path = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if self.path.exists():
                os.chmod(temp_path, stat.S_IMODE(self.path.stat().st_mode))
            os.replace(temp_path, self.path)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()
        self.disk_hash = hashlib.sha256(payload).digest()
        self.document().setModified(False)
