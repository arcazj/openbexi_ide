"""Native text editor with line numbers, breakpoints and existing Python lexer."""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import tempfile
import tokenize
import stat
import re

from pygments.lexers import PythonLexer
from pygments.token import Token
from PySide6.QtCore import QRect, QSize, QStringListModel, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QColor, QPainter, QPen, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QTextFormat
from PySide6.QtWidgets import QCompleter, QPlainTextEdit, QTextEdit, QWidget
from .fonts import fixed_font
from .navigation import word_at
from .productivity import AnalysisJob, SymbolDialog


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
        if getattr(self.editor, 'source_snapshot', False):
            return
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
    navigation_requested = Signal(str, int, int)
    productivity_message = Signal(str)

    def __init__(self, path: Path, colors, parent=None, *, payload=None, encoding=None):
        super().__init__(parent)
        self.path = path.resolve()
        self.source_snapshot = payload is not None
        payload = self.path.read_bytes() if payload is None else payload
        if len(payload) > 2_000_000:
            raise ValueError("This editor supports text files up to 2 MB")
        self.encoding = encoding or tokenize.detect_encoding(io.BytesIO(payload).readline)[0]
        self.newline = "\r\n" if b"\r\n" in payload else "\n"
        self.disk_hash = hashlib.sha256(payload).digest()
        self.colors = colors
        self.breakpoints: set[int] = set()
        self.verified_breakpoints: dict[int, bool] = {}
        self.execution_line: int | None = None
        self.project = self.path.parent
        self._buffers = None
        self._analysis_number = 0
        self._analysis_stamp = None
        self._analysis_jobs = {}
        self._queued_analysis = None
        self.symbol_dialog = None
        self.completion_model = QStringListModel(self)
        self.completer = QCompleter(self.completion_model, self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitive)
        self.completer.activated.connect(self._insert_completion)
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
        self.cursorPositionChanged.connect(self._hide_completion)
        self.textChanged.connect(self._hide_completion)
        self.update_margin()
        self.highlight_line()

    def configure_project(self, project: Path, buffers=None):
        """Provide the project root and an optional GUI-thread buffer snapshot callback."""
        self.project = Path(project).resolve()
        self._buffers = buffers
        self._analysis_number += 1
        self._queued_analysis = None
        self._hide_completion()
        if self.symbol_dialog:
            self.symbol_dialog.close()

    def _hide_completion(self):
        self.completer.popup().hide()

    def hideEvent(self, event):
        self._analysis_number += 1
        self._queued_analysis = None
        self._hide_completion()
        if self.symbol_dialog:
            self.symbol_dialog.close()
        super().hideEvent(event)

    def setReadOnly(self, read_only):
        super().setReadOnly(read_only)
        if read_only and hasattr(self, "completer"):
            self._hide_completion()

    def _cursor_coordinates(self):
        cursor = self.textCursor()
        # Qt positions count UTF-16 code units, including two for astral chars.
        column = len(cursor.block().text().encode("utf-16-le")[:cursor.positionInBlock() * 2].decode("utf-16-le"))
        return cursor.blockNumber() + 1, column

    def _request_analysis(self, kind):
        if self.path.suffix not in {".py", ".pyi"}:
            self.productivity_message.emit("Python source assistance is available in .py and .pyi files.")
            return
        if kind == "completion" and self.isReadOnly():
            self.productivity_message.emit("Completion is unavailable while this editor is read-only.")
            return
        self._hide_completion()
        self._analysis_number += 1
        number = self._analysis_number
        source = self.toPlainText()
        buffers = dict(self._buffers()) if self._buffers else {}
        buffers[self.path] = source
        self._analysis_stamp = (self.document().revision(), self.textCursor().position())
        line, column = self._cursor_coordinates()
        job = AnalysisJob(number, kind, self.project, buffers, self.path, source, line, column)
        job.signals.finished.connect(self._analysis_finished)
        self.productivity_message.emit("Reading Python source…")
        # Repeated shortcuts keep at most one running and one latest request.
        # A large project must not queue an unbounded number of source copies.
        if self._analysis_jobs:
            self._queued_analysis = job
        else:
            self._start_analysis(job)

    def _start_analysis(self, job):
        self._analysis_jobs[job.number] = job
        QThreadPool.globalInstance().start(job)

    def request_completion(self):
        self._request_analysis("completion")

    def go_to_definition(self):
        self._request_analysis("definition")

    def show_symbols(self):
        self._request_analysis("symbols")

    @Slot(int, str, object, str)
    def _analysis_finished(self, number, kind, result, message):
        self._analysis_jobs.pop(number, None)
        if self._queued_analysis:
            pending, self._queued_analysis = self._queued_analysis, None
            self._start_analysis(pending)
        if number != self._analysis_number:
            return
        if not self.isVisible():
            return
        if kind != "symbols" and self._analysis_stamp != (self.document().revision(), self.textCursor().position()):
            return
        if message:
            self.productivity_message.emit(message)
        if kind == "completion":
            if self.isReadOnly():
                return
            if not result:
                self.productivity_message.emit(message or "No static Python completions at this position.")
                return
            self.completion_model.setStringList([completion.name for completion in result])
            line, column = self._cursor_coordinates()
            prefix = word_at(self.toPlainText(), line, column, before=True).rsplit(".", 1)[-1]
            self.completer.setCompletionPrefix(prefix)
            self.completer.popup().setCurrentIndex(self.completer.completionModel().index(0, 0))
            rect = self.cursorRect()
            rect.setWidth(max(240, self.completer.popup().sizeHintForColumn(0) + 30))
            self.completer.complete(rect)
            self.productivity_message.emit(message or "Choose a completion with ↑/↓, then Enter or Tab. Escape closes.")
        elif kind == "definition":
            if result:
                self._navigate(result)
                self.productivity_message.emit(message or f"{result.path.name}:{result.line}")
            else:
                self.productivity_message.emit(message or "No static definition found inside this project.")
        elif result is not None:
            if self.symbol_dialog:
                self.symbol_dialog.close()
            self.symbol_dialog = SymbolDialog(self.project, result, self)
            self.symbol_dialog.selected.connect(self._navigate)
            dialog = self.symbol_dialog
            dialog.destroyed.connect(lambda _object=None: self._symbol_dialog_closed(dialog))
            self.symbol_dialog.show()
            self.symbol_dialog.search.setFocus()
            self.productivity_message.emit(message or "Project symbols are ready.")

    def _symbol_dialog_closed(self, dialog):
        if self.symbol_dialog is dialog:
            self.symbol_dialog = None

    def _navigate(self, symbol):
        if symbol.path.is_relative_to(self.project):
            self.navigation_requested.emit(str(symbol.path), symbol.line, symbol.column)

    def goto_location(self, line, column=0):
        block = self.document().findBlockByNumber(max(0, min(line - 1, self.blockCount() - 1)))
        column = max(0, min(column, len(block.text())))
        utf16_column = len(block.text()[:column].encode("utf-16-le")) // 2
        cursor = self.textCursor()
        cursor.setPosition(block.position() + utf16_column)
        self.setTextCursor(cursor)
        self.centerCursor()
        self.setFocus()

    def _insert_completion(self, completion):
        if self.isReadOnly() or self._analysis_stamp != (self.document().revision(), self.textCursor().position()):
            self._hide_completion()
            return
        cursor = self.textCursor()
        line, column = self._cursor_coordinates()
        current = cursor.block().text()
        prefix = word_at(self.toPlainText(), line, column, before=True).rsplit(".", 1)[-1]
        suffix = re.match(r"\w*", current[column:]).group()
        start = cursor.position() - len(prefix.encode("utf-16-le")) // 2
        end = cursor.position() + len(suffix.encode("utf-16-le")) // 2
        cursor.beginEditBlock()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.insertText(completion)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self._hide_completion()

    def keyPressEvent(self, event):
        if self.completer.popup().isVisible():
            if event.key() in {Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab}:
                completion = self.completer.popup().currentIndex().data()
                if completion:
                    self._insert_completion(completion)
                event.accept()
                return
            if event.key() == Qt.Key_Escape:
                self._hide_completion()
                event.accept()
                return
        if event.key() == Qt.Key_Space and event.modifiers() == Qt.ControlModifier:
            self.request_completion()
            event.accept()
        elif event.key() == Qt.Key_F12 and event.modifiers() == Qt.NoModifier:
            self.go_to_definition()
            event.accept()
        elif event.key() == Qt.Key_O and event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier):
            self.show_symbols()
            event.accept()
        else:
            super().keyPressEvent(event)

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
