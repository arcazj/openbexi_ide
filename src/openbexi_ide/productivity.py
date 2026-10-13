"""Worker and small Qt views for source-only editor assistance."""
from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Qt, Signal
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from .navigation import ProjectIndex


class AnalysisSignals(QObject):
    finished = Signal(int, str, object, str)


class AnalysisJob(QRunnable):
    def __init__(self, number, kind, project, buffers, path, source, line, column):
        super().__init__()
        self.signals = AnalysisSignals()
        self.number, self.kind = number, kind
        self.project, self.buffers = project, buffers
        self.path, self.source, self.line, self.column = path, source, line, column

    def run(self):
        result, message = None, ""
        try:
            index = ProjectIndex(self.project, self.buffers)
            if self.kind == "symbols":
                result = index.symbols()
            elif self.kind == "definition":
                result = index.definition(self.path, self.source, self.line, self.column)
            else:
                result = index.complete(self.path, self.source, self.line, self.column)
            if index.limited:
                message = "Analysis limit reached; results cover part of this project."
        except Exception as error:
            message = "Python source analysis failed: " + str(error)[:200]
        self.signals.finished.emit(self.number, self.kind, result, message)


class SymbolDialog(QDialog):
    selected = Signal(object)

    def __init__(self, project, symbols, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Project symbols")
        self.resize(680, 420)
        self.project, self.symbols = project, symbols
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setObjectName("symbolSearch")
        self.search.setPlaceholderText("Search functions, classes and variables")
        layout.addWidget(self.search)
        self.results = QListWidget()
        self.results.setObjectName("symbolResults")
        layout.addWidget(self.results)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.search.textChanged.connect(self.filter)
        self.search.returnPressed.connect(self.activate_current)
        self.results.itemActivated.connect(lambda _item: self.activate_current())
        self.filter("")

    def filter(self, query):
        self.results.clear()
        terms = query.casefold().split()
        matches = [symbol for symbol in self.symbols
                   if all(term in (symbol.qualified_name + " " + str(symbol.path.relative_to(self.project))).casefold()
                          for term in terms)]
        for symbol in matches[:500]:
            location = symbol.path.relative_to(self.project).as_posix()
            item = QListWidgetItem(f"{symbol.qualified_name}  ·  {symbol.kind}  ·  {location}:{symbol.line}")
            item.setData(Qt.UserRole, symbol)
            self.results.addItem(item)
        if matches:
            self.results.setCurrentRow(0)
        self.summary.setText(f"{len(matches)} symbols" + (" · First 500 shown; refine your search" if len(matches) > 500 else ""))

    def activate_current(self):
        item = self.results.currentItem()
        if item:
            self.selected.emit(item.data(Qt.UserRole))
            self.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Down and self.search.hasFocus():
            self.results.setFocus()
            event.accept()
        else:
            super().keyPressEvent(event)
