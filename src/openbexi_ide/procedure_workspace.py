"""Procedure history and execution presentation for optional runtime backends."""
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import re
import tokenize

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QRadioButton,
    QScrollArea, QSplitter, QTableView, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from .fonts import fixed_font


@dataclass(eq=False)
class ProcedureRun:
    project: Path
    script: Path
    mode: str
    started: datetime = field(default_factory=lambda: datetime.now().astimezone())
    status: str = 'Starting'
    active: bool = True
    aborted: bool = False
    root_id: str = ''
    sources: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)
    current: dict = field(default_factory=dict)
    current_path: Path | None = None
    output: str = ''
    prompt: dict | None = None
    answering: bool = False
    error: str = ''
    reminder: bool = False

    def source_path(self, source):
        raw = source.get('path', '')
        if not raw:
            return None
        path = Path(raw).resolve()
        return path if path.is_relative_to(self.project) else None

    def apply(self, event):
        if not self.active:
            return
        kind = event.get('kind')
        self.root_id = event.get('rootProcedureId') or self.root_id
        if kind == 'source':
            path = self.source_path(event.get('source', {}))
            if path is None:
                return
            offset = event.get('offset', 0)
            previous = '' if offset == 0 else self.sources.get(path, '')
            # Never concatenate reordered chunks or display unbounded source.
            if offset == len(previous) and len(previous) + len(event['text']) <= 2 * 1024 * 1024:
                self.sources[path] = previous + event['text']
        elif kind == 'line':
            path = self.source_path(event.get('source', {}))
            line = event.get('line')
            if path not in self.sources or type(line) is not int or not 1 <= line <= len(self.sources[path].splitlines()):
                return
            row = self.results.setdefault(path, {}).setdefault(line, {})
            if event.get('current'):
                self.current[path] = line
                self.current_path = path
                row.setdefault('status', 'Reached')
            if event.get('status') or event.get('item') or event.get('value'):
                row.update({key: event.get(key, '') for key in ('timestamp', 'item', 'value', 'status', 'details')})
            elif not row.get('timestamp'):
                row['timestamp'] = event.get('timestamp', '')
        elif kind == 'status':
            if event.get('procedureId') == self.root_id:
                self.status = event.get('status') or self.status
            if (self.prompt and event.get('procedureId') == self.prompt.get('procedureId')
                    and event.get('status') != 'PROMPT'):
                self.prompt = None
                self.answering = False
        elif kind == 'prompt':
            self.prompt = dict(event)
            self.answering = self.reminder = False
            self.error = ''
        elif kind == 'promptClosed' and self.prompt and event.get('promptId') == self.prompt.get('promptId'):
            self.prompt = None
            self.answering = False
        elif kind == 'reminder' and self.prompt and event.get('promptId') in ('', None, self.prompt.get('promptId')):
            self.reminder = True


class CodeResultsModel(QAbstractTableModel):
    columns = ('Line', 'Procedure code', 'Native date & time', 'Item', 'Value', 'Result')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.run = None
        self.path = None
        self.lines = []

    def display(self, run, path):
        lines = run.sources.get(path, '').splitlines() if run else []
        if run is not self.run or path != self.path or lines != self.lines:
            self.beginResetModel()
            self.run, self.path, self.lines = run, path, lines
            self.endResetModel()
        elif self.lines:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.lines) - 1, 5))

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.lines)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columns[section]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or self.run is None:
            return None
        line, column = index.row() + 1, index.column()
        row = self.run.results.get(self.path, {}).get(line, {})
        if role == Qt.DisplayRole:
            if column == 0:
                return str(line)
            if column == 1:
                return self.lines[index.row()]
            return str(row.get(('timestamp', 'item', 'value', 'status')[column - 2], '')).replace('\4', ' · ')
        if role == Qt.FontRole and column == 1:
            return fixed_font()
        if role == Qt.BackgroundRole and self.run.active and self.run.current.get(self.path) == line:
            return self.parent().palette().highlight().color()
        if role == Qt.ToolTipRole:
            return self.lines[index.row()] if column == 1 else json.dumps(row.get('details', {}), ensure_ascii=False, indent=2)


class ProcedureWorkspace(QWidget):
    attention = Signal()
    navigate = Signal(object, int)
    location_changed = Signal(object, int)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.runs = []
        self.active_run = self.selected = None
        self.rendered_prompt = None
        self.last_location = None
        self.answer_field = None
        self.choices = None
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(40)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.refresh)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 10)
        heading = QHBoxLayout()
        self.title = QLabel('Procedure workspace')
        self.title.setTextFormat(Qt.PlainText)
        font = self.title.font(); font.setBold(True); self.title.setFont(font)
        self.state = QLabel('Ready'); self.state.setTextFormat(Qt.PlainText)
        heading.addWidget(self.title); heading.addStretch(); heading.addWidget(self.state)
        layout.addLayout(heading)
        self.history = QTreeWidget()
        self.history.setHeaderLabels(['Procedure', 'Started (local)', 'Mode', 'Result'])
        self.history.setRootIsDecorated(False)
        self.history.setUniformRowHeights(True)
        self.history.setColumnWidth(0, 240); self.history.setColumnWidth(1, 210)
        self.history.currentItemChanged.connect(self.select_run)
        self.history.setMinimumHeight(65)
        content = QWidget(); content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        source_row = QHBoxLayout()
        self.source_choice = QComboBox()
        self.source_choice.setMinimumContentsLength(18)
        self.source_choice.currentIndexChanged.connect(self.refresh)
        self.follow = QCheckBox('Follow current line'); self.follow.setChecked(True)
        source_row.addWidget(self.source_choice, 1); source_row.addWidget(self.follow)
        content_layout.addLayout(source_row)
        self.code = QTableView()
        self.model = CodeResultsModel(self.code); self.code.setModel(self.model)
        self.code.setShowGrid(False)
        self.code.verticalHeader().hide()
        self.code.verticalHeader().setDefaultSectionSize(25)
        self.code.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.code.setSelectionMode(QAbstractItemView.SingleSelection)
        self.code.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.code.setWordWrap(False)
        self.code.horizontalHeader().setStretchLastSection(True)
        for column, width in enumerate((48, 430, 220, 140, 140, 100)):
            self.code.setColumnWidth(column, width)
        self.code.doubleClicked.connect(lambda index: self.navigate.emit(self.model.path, index.row() + 1))
        code_page = QWidget(); code_layout = QVBoxLayout(code_page)
        code_layout.setContentsMargins(0, 0, 0, 0); code_layout.addWidget(self.code)
        note = QLabel('Results appear when reported by the runtime. History lasts for this IDE session.')
        note.setObjectName('muted'); code_layout.addWidget(note)
        self.output = QPlainTextEdit(); self.output.setReadOnly(True); self.output.setFont(fixed_font())
        self.tabs = QTabWidget()
        self.tabs.addTab(code_page, 'Code && results'); self.tabs.addTab(self.output, 'Output')
        content_layout.addWidget(self.tabs)
        split = QSplitter(Qt.Vertical); split.addWidget(self.history); split.addWidget(content)
        split.setSizes([90, 350]); split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)
        self.prompt_panel = QFrame(); self.prompt_panel.setFrameShape(QFrame.StyledPanel)
        prompt_layout = QVBoxLayout(self.prompt_panel)
        self.question = QLabel(); self.question.setWordWrap(True); self.question.setTextFormat(Qt.PlainText)
        prompt_layout.addWidget(self.question)
        self.prompt_body = QWidget(); self.prompt_body_layout = QVBoxLayout(self.prompt_body)
        self.prompt_body_layout.setContentsMargins(0, 0, 0, 0)
        self.prompt_scroll = QScrollArea(); self.prompt_scroll.setWidgetResizable(True)
        self.prompt_scroll.setWidget(self.prompt_body); self.prompt_scroll.setFrameShape(QFrame.NoFrame)
        self.prompt_scroll.setMaximumHeight(115); prompt_layout.addWidget(self.prompt_scroll)
        buttons = QHBoxLayout()
        self.commit = QPushButton('Commit'); self.reset = QPushButton('Reset'); self.abort = QPushButton('Abort procedure')
        self.commit.setStyleSheet('QPushButton { background: #3976dd; color: white; border: 1px solid #3976dd; } QPushButton:disabled { background: #747781; }')
        for button in (self.reset, self.abort):
            button.setStyleSheet('QPushButton { border: 1px solid palette(mid); }')
        for button in (self.commit, self.reset, self.abort):
            buttons.addWidget(button)
        buttons.addStretch(); prompt_layout.addLayout(buttons)
        self.prompt_message = QLabel(); self.prompt_message.setWordWrap(True); self.prompt_message.setTextFormat(Qt.PlainText)
        prompt_layout.addWidget(self.prompt_message)
        layout.addWidget(self.prompt_panel); self.prompt_panel.hide()
        self.commit.clicked.connect(self.submit); self.reset.clicked.connect(self.reset_answer)
        self.abort.clicked.connect(self.stop_selected)
        controller.procedure_event.connect(self.receive_event)
        controller.prompt_answered.connect(self.answered)
        controller.output.connect(self.append_output)
        controller.finished.connect(self.finish)

    def begin(self, spec, mode):
        run = ProcedureRun(spec.project.resolve(), spec.script.resolve(), mode)
        with tokenize.open(spec.script) as stream:
            run.sources[run.script] = stream.read()
        self.runs.insert(0, run)
        self.runs[:] = self.runs[:100]
        self.active_run = self.selected = run
        self.history.blockSignals(True)
        item = QTreeWidgetItem([run.script.name, run.started.strftime('%Y-%m-%d %H:%M:%S %Z'), mode, run.status])
        item.setData(0, Qt.UserRole, run)
        self.history.insertTopLevelItem(0, item); self.history.setCurrentItem(item)
        while self.history.topLevelItemCount() > 100:
            self.history.takeTopLevelItem(100)
        self.history.blockSignals(False)
        self.refresh()
        self.attention.emit()

    def select_run(self, item, _previous):
        self.selected = item.data(0, Qt.UserRole) if item else None
        self.refresh()

    def receive_event(self, event):
        run = self.active_run
        if run is None or not run.active:
            return
        run.apply(event)
        if event.get('kind') == 'prompt':
            self.history.setCurrentItem(self.history.topLevelItem(0))
            self.refresh(); self.attention.emit()
        elif not self.refresh_timer.isActive():
            self.refresh_timer.start()

    def append_output(self, text):
        if self.active_run and self.active_run.active:
            self.active_run.output = (self.active_run.output + text)[-524288:]
            if not self.refresh_timer.isActive():
                self.refresh_timer.start()

    def finish(self, code):
        if self.active_run and self.active_run.active:
            run = self.active_run
            run.active = False; run.prompt = None; run.answering = False
            run.status = 'Aborted' if run.aborted or code == 130 else f'Finished ({code})' if code == 0 else f'Failed ({code})'
            self.refresh()
        self.active_run = None

    def stop_selected(self):
        if self.selected is self.active_run and self.selected and self.selected.active:
            self.selected.aborted = True
            self.selected.status = 'Stopping'; self.selected.prompt = None
            self.controller.stop(); self.refresh()

    def refresh(self, *_):
        run = self.selected
        for index in range(self.history.topLevelItemCount()):
            item = self.history.topLevelItem(index); item.setText(3, item.data(0, Qt.UserRole).status)
        self.title.setText(run.script.name if run else 'Procedure workspace')
        self.state.setText(('Waiting for input · ' if run and run.prompt else '') + (run.status if run else 'Ready'))
        paths = list(run.sources) if run else []
        existing = [self.source_choice.itemData(i) for i in range(self.source_choice.count())]
        if paths != existing:
            previous = self.source_choice.currentData()
            self.source_choice.blockSignals(True); self.source_choice.clear()
            for path in paths:
                self.source_choice.addItem(path.relative_to(run.project).as_posix(), path)
            if previous in paths:
                self.source_choice.setCurrentIndex(paths.index(previous))
            self.source_choice.blockSignals(False)
        if run and run.active and self.follow.isChecked() and run.current_path in paths:
            self.source_choice.blockSignals(True)
            self.source_choice.setCurrentIndex(paths.index(run.current_path))
            self.source_choice.blockSignals(False)
        path = self.source_choice.currentData()
        self.model.display(run, path)
        if run and path in run.current and run.active:
            location = (id(run), path, run.current[path])
            if self.follow.isChecked():
                self.code.scrollTo(self.model.index(run.current[path] - 1, 0), QAbstractItemView.PositionAtCenter)
            if location != self.last_location:
                self.last_location = location
                self.location_changed.emit(path, run.current[path])
        output = run.output if run else ''
        if self.output.toPlainText() != output:
            bar = self.output.verticalScrollBar(); position = bar.value(); follow = position == bar.maximum()
            self.output.setPlainText(output)
            bar.setValue(bar.maximum() if follow else position)
        self.render_prompt(run)

    def render_prompt(self, run):
        prompt = run.prompt if run and run.active else None
        self.prompt_panel.setVisible(prompt is not None)
        if prompt is None:
            self.rendered_prompt = None
            if self.answer_field:
                self.answer_field.clear()
            return
        identity = (id(run), prompt['promptId'])
        if identity != self.rendered_prompt:
            self.rendered_prompt = identity
            while self.prompt_body_layout.count():
                widget = self.prompt_body_layout.takeAt(0).widget()
                if widget:
                    widget.deleteLater()
            if self.choices:
                self.choices.deleteLater()
            self.choices = self.answer_field = None
            owner = prompt.get('procedureId', '')
            self.question.setText(prompt.get('text', '') + (f'\nProcedure: {owner}' if owner and owner != run.root_id else ''))
            if prompt.get('choices'):
                self.choices = QButtonGroup(self)
                for index, choice in enumerate(prompt['choices']):
                    button = QRadioButton(choice['label'] or '(empty value)')
                    button.setProperty('wire_value', choice['value'])
                    self.choices.addButton(button, index); self.prompt_body_layout.addWidget(button)
            else:
                self.answer_field = QLineEdit()
                self.answer_field.setAccessibleName('Procedure prompt answer')
                input_type = prompt.get('inputType')
                self.answer_field.setEchoMode(QLineEdit.Password if input_type == 'password' else QLineEdit.Normal)
                self.answer_field.setPlaceholderText('Enter a number' if input_type == 'number' else
                    'Enter a date, e.g. 17-Oct-2026 14:30:00' if input_type == 'date' else 'Enter your answer')
                self.answer_field.returnPressed.connect(self.submit)
                self.prompt_body_layout.addWidget(self.answer_field)
                self.answer_field.setFocus()
        enabled = run is self.active_run and not run.answering
        self.commit.setEnabled(enabled); self.reset.setEnabled(enabled); self.abort.setEnabled(run is self.active_run)
        self.prompt_body.setEnabled(enabled)
        message = run.error or ('Submitting answer…' if run.answering else 'The procedure is waiting for your answer.' if run.reminder else '')
        if not message and 'defaultHint' in prompt:
            message = 'Procedure default: ' + str(prompt['defaultHint'])
        self.prompt_message.setText(message)

    def reset_answer(self):
        if self.choices:
            self.choices.setExclusive(False)
            for button in self.choices.buttons():
                button.setChecked(False)
            self.choices.setExclusive(True)
        if self.answer_field:
            self.answer_field.clear(); self.answer_field.setFocus()
        if self.selected:
            self.selected.error = ''
        self.prompt_message.clear()

    def submit(self):
        run = self.selected
        if run is not self.active_run or not run or not run.active or not run.prompt or run.answering:
            return
        if self.choices:
            button = self.choices.checkedButton()
            if button is None:
                run.error = 'Select an answer first.'; self.refresh(); return
            answer = button.property('wire_value')
        else:
            answer = self.answer_field.text()
            if run.prompt.get('inputType') == 'number' and not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', answer):
                run.error = 'Enter a valid number before committing.'; self.refresh(); return
        if len(answer.encode('utf-8')) > 65536:
            run.error = 'The answer must be smaller than 64 KiB.'; self.refresh(); return
        if self.controller.answer_prompt(run.prompt['promptId'], answer):
            run.answering = True; run.error = ''
        else:
            run.error = 'This prompt is no longer accepting an answer.'
        self.refresh()

    def answered(self, identifier, error):
        run = self.active_run
        if run and run.prompt and run.prompt['promptId'] == identifier:
            run.answering = False; run.error = error
            if not error:
                run.prompt = None
            self.refresh()
