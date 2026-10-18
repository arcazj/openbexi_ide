"""Procedure history and execution presentation for optional runtime backends."""
import json
from pathlib import Path
import re
import tokenize

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, Signal, QUrl
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QRadioButton,
    QScrollArea, QSplitter, QTabBar, QTableView, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from .fonts import fixed_font
from openbexi_runtime.procedure_model import ProcedureRun, notification_items
from openbexi_runtime.procedure_records import ProcedureRecords
from openbexi_runtime.procedure_colors import procedure_color, result_color, CURRENT_LINE
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTableWidget, QTableWidgetItem, QFileDialog




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
        if role == Qt.BackgroundRole:
            if column == 5 and result_color(row.get('status', '')):
                return QColor(result_color(row['status']))
            if self.run.active and self.run.current.get(self.path) == line:
                return QColor(CURRENT_LINE)
            return QColor(procedure_color(self.run.status))
        if role == Qt.ForegroundRole:
            return QColor('white' if self.run.active and self.run.current.get(self.path) == line
                          and not (column == 5 and result_color(row.get('status', ''))) else 'black')
        if role == Qt.ToolTipRole:
            return self.lines[index.row()] if column == 1 else json.dumps(row.get('details', {}), ensure_ascii=False, indent=2)


class ProcedureWorkspace(QWidget):
    attention = Signal()
    navigate = Signal(object, int)
    location_changed = Signal(object, int)
    selection_changed = Signal()
    open_instance = Signal(object)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.runs = []
        self.journal = None
        self.journal_project = None
        self.active_run = self.selected = None
        self.connection_worker = None
        self.service_records = None
        self.controllers = {}
        self.max_instances = 8
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
        self.procedure_tabs = QTabBar()
        self.procedure_tabs.setExpanding(False); self.procedure_tabs.setUsesScrollButtons(True)
        self.procedure_tabs.setAccessibleName('Procedure instances and history')
        self.procedure_tabs.currentChanged.connect(self.select_tab)
        layout.addWidget(self.procedure_tabs)
        heading = QHBoxLayout()
        self.title = QLabel('Procedure workspace')
        self.title.setTextFormat(Qt.PlainText)
        font = self.title.font(); font.setBold(True); self.title.setFont(font)
        self.state = QLabel('Ready'); self.state.setTextFormat(Qt.PlainText)
        heading.addWidget(self.title); heading.addStretch(); heading.addWidget(self.state)
        layout.addLayout(heading)
        controls = QHBoxLayout()
        self.open_procedure = QPushButton('Open procedure')
        self.open_procedure.clicked.connect(self.choose_procedure); controls.addWidget(self.open_procedure)
        self.control_buttons = {}
        for label, command in [('Run / Continue', 'continue'), ('Pause', 'pause'), ('Step', 'stepIn'), ('Step over', 'next')]:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, c=command: self.control(c))
            self.control_buttons[command] = button; controls.addWidget(button)
        stop = QPushButton('Abort'); stop.clicked.connect(self.stop_selected)
        self.control_buttons['abort'] = stop; controls.addWidget(stop)
        self.claim = QPushButton('Take control'); self.claim.clicked.connect(lambda: self.service_control('openbexi/claim'))
        self.release = QPushButton('Release control'); self.release.clicked.connect(lambda: self.service_control('openbexi/release'))
        self.browser = QPushButton('Web workspace'); self.browser.clicked.connect(self.open_browser)
        self.export_record = QPushButton('Export As-Run'); self.export_record.clicked.connect(self.save_record)
        controls.addWidget(self.export_record)
        for button in (self.claim, self.release, self.browser):
            button.hide(); controls.addWidget(button)
        self.service_endpoint = None
        self.role = QLabel('CTRL'); self.role.setStyleSheet('color: #008000; font-weight: bold;')
        controls.addWidget(self.role)
        self.connection = QLabel('Local'); controls.addWidget(self.connection)
        controls.addStretch()
        self.history_toggle = QCheckBox('Procedure list')
        controls.addWidget(self.history_toggle); layout.addLayout(controls)
        self.history = QTreeWidget()
        self.history.setHeaderLabels(['Procedure', 'Started (local)', 'Mode', 'Result'])
        self.history.setRootIsDecorated(False)
        self.history.setUniformRowHeights(True)
        self.history.setColumnWidth(0, 240); self.history.setColumnWidth(1, 210)
        self.history.currentItemChanged.connect(self.select_run)
        self.history.setMinimumHeight(65)
        self.history.hide(); self.history_toggle.toggled.connect(self.history.setVisible)
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
        self.code.doubleClicked.connect(self.show_item_information)
        code_page = QWidget(); code_layout = QVBoxLayout(code_page)
        code_layout.setContentsMargins(0, 0, 0, 0); code_layout.addWidget(self.code)
        note = QLabel('Results appear when reported by the runtime. Double-click a result for item information. Execution records are saved with the project.')
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
        self.bind_controller(controller)

    def bind_controller(self, controller):
        self.controllers[controller] = None
        controller.procedure_event.connect(lambda event: self.receive_event(event, self.controllers.get(controller)))
        controller.prompt_answered.connect(lambda identifier, error: self.answered(identifier, error, self.controllers.get(controller)))
        controller.output.connect(lambda text: self.append_output(text, self.controllers.get(controller)))
        controller.finished.connect(lambda code: self.finish(code, self.controllers.get(controller)))
        if hasattr(controller, 'procedure_state'):
            controller.procedure_state.connect(lambda state: self.receive_state(state, self.controllers.get(controller)))
            controller.stopped.connect(self.refresh); controller.continued.connect(self.refresh)
            controller.state_changed.connect(self.refresh)

    def receive_state(self, state, run=None):
        run = run or self.active_run
        if state['event'] == 'openbexi/service':
            self.service_endpoint = Path(state['endpoint'])
            if run:
                run.service_id = state['id']; run.persist()
            self.connect_service()
            self.browser.show(); self.claim.show(); self.release.show()
        elif run:
            run.server_revision = state.get('revision', -1)
            run.server_instance = state.get('service_instance', '')
            run.controlling = state.get('controlling', False)
            run.bridge_controlling = run.controlling
            run.controller = state.get('controller', '')
            run.pending = state.get('pending', '')
            run.status = state.get('status', run.status)
        self.refresh()

    def service_control(self, command):
        run = self.selected
        controller = self.run_controller(run)
        if controller:
            controller.request(command)
        elif run and self.connection_worker:
            self.service_request('/api/control', dict(id=run.service_id,
                release=command == 'openbexi/release'), run)

    def run_controller(self, run):
        return next((controller for controller, candidate in self.controllers.items()
                     if candidate is run and getattr(controller, 'active', False)), None)

    def service_request(self, path, data, run, callback=None):
        if not self.connection_worker:
            return
        run.pending = 'Awaiting acknowledgement'; self.refresh()
        def complete(result, error):
            run.pending = ''; run.error = error
            if callback:
                callback(result, error)
            self.refresh()
        self.connection_worker.request(path, data, complete)

    def connect_service(self):
        if self.connection_worker and self.connection_worker.endpoint == self.service_endpoint:
            return
        if self.connection_worker:
            self.connection_worker.close()
        if self.service_records:
            self.service_records.close()
        self.service_records = ProcedureRecords(self.service_endpoint.parent / 'records.sqlite3')
        from .procedure_connection import ProcedureConnection
        worker = self.connection_worker = ProcedureConnection(self.service_endpoint, self)
        worker.snapshot.connect(lambda state: self.synchronize(state) if worker is self.connection_worker else None)
        worker.completed.connect(lambda callback, result, error: callback(result, error)
                                 if callback and worker is self.connection_worker else None)
        worker.disconnected.connect(lambda error: self.connection_lost(error) if worker is self.connection_worker else None)

    def connection_lost(self, error):
        for run in self.runs:
            if run.service_id and run.active:
                run.connection = 'Disconnected'; run.controlling = False
        self.refresh(); self.selection_changed.emit()

    def synchronize(self, state):
        self.max_instances = state['capabilities']['maxInstances']
        for data in reversed(state['runs']):
            run = next((r for r in self.runs if (r.service_id or r.identifier) == data['id']), None)
            if run is None and any(r.active and not r.service_id and r.script == Path(data['script']) for r in self.runs):
                # The launch response assigns the ID after native startup.
                continue
            same_service = run and state.get('instance', '') == getattr(run, 'server_instance', '')
            if same_service and state['revision'] < getattr(run, 'server_revision', -1):
                continue
            if run is None:
                run = ProcedureRun.restore(data); run.service_id = data['id']; run.journal = self.journal
                self.journal.create(run.project, run.script, run.mode, run.identifier)
                self.runs.insert(0, run)
                item = QTreeWidgetItem([run.script.name, run.started.strftime('%Y-%m-%d %H:%M:%S %Z'), run.mode, run.status])
                item.setData(0, Qt.UserRole, run); self.history.insertTopLevelItem(0, item)
            controller = self.run_controller(run)
            controlling = getattr(run, 'bridge_controlling', False) if controller and same_service else data['controlling']
            run.server_instance = state.get('instance', '')
            run.server_revision = state['revision']
            restored = ProcedureRun.restore(data)
            for name in ('sources', 'results', 'current', 'current_path', 'status', 'active',
                         'root_id', 'controller', 'connection', 'exit_code', 'step', 'reminder'):
                setattr(run, name, getattr(restored, name))
            if not controller:
                run.prompt = restored.prompt
                run.output = restored.output
            run.controlling = controlling; run.pending = data.get('pending', ''); run.persist()
        # Preserve selection across notifications, including prompts in another instance.
        if self.selected is None and self.runs:
            self.history.setCurrentItem(self.history.topLevelItem(0))
        self.browser.show(); self.claim.show(); self.release.show()
        self.refresh(); self.selection_changed.emit()

    def can_start(self):
        live = [run for run in self.runs if run.active]
        return len(live) < self.max_instances and all(run.status.upper() in {'PAUSED', 'INTERRUPTED'} and not getattr(run, 'pending', '') for run in live)

    def choose_procedure(self):
        if self.journal_project and self.can_start():
            filename, _ = QFileDialog.getOpenFileName(self, 'Run another procedure',
                str(self.journal_project), 'SPELL procedure (*.py)')
            if filename:
                self.open_instance.emit(Path(filename))

    def open_browser(self):
        if self.service_endpoint:
            config = json.loads(self.service_endpoint.read_text(encoding='utf-8'))
            QDesktopServices.openUrl(QUrl(config['url'] + '/#key=' + config['operator']))

    def save_record(self):
        run = self.selected
        if run is None or run.journal is None:
            return
        filename, _ = QFileDialog.getSaveFileName(self, 'Export As-Run record',
            run.script.stem + '-' + (run.service_id or run.identifier)[:8] + '.jsonl', 'As-Run record (*.jsonl)')
        if filename:
            try:
                run.persist()
                with open(filename, 'w', encoding='utf-8', newline='\n') as stream:
                    if run.service_id and self.service_records:
                        self.service_records.export(run.service_id, stream)
                    else:
                        run.journal.export(run.identifier, stream)
            except (OSError, ValueError) as error:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, 'As-Run export failed', str(error))

    def load_history(self, project, create=True):
        if self.journal_project == project and (self.journal is not None or not create):
            return
        if self.journal:
            self.journal.close(); self.journal = None
        if self.connection_worker:
            self.connection_worker.close(); self.connection_worker = None
        if self.service_records:
            self.service_records.close(); self.service_records = None
        self.journal_project = project
        self.runs.clear(); self.history.clear(); self.active_run = self.selected = None
        from openbexi_runtime.procedure_service import workspace_directory
        self.service_endpoint = workspace_directory(project) / 'endpoint.json'
        path = project / '.openbexi' / 'runs' / 'presentation.sqlite3'
        if not create and not path.is_file() and not self.service_endpoint.is_file():
            self.refresh()
            return
        self.journal = ProcedureRecords(path)
        for record in self.journal.recent(project):
            data = record['snapshot']
            if not data:
                continue
            run = ProcedureRun.restore(data); run.journal = self.journal
            if run.active:
                # A stored display is not evidence of a surviving executor.
                run.active = False; run.prompt = None; run.status = 'UNKNOWN'; run.connection = 'Disconnected'
            self.runs.append(run)
            item = QTreeWidgetItem([run.script.name, run.started.strftime('%Y-%m-%d %H:%M:%S %Z'), run.mode, run.status])
            item.setData(0, Qt.UserRole, run); self.history.addTopLevelItem(item)
        if self.service_endpoint.is_file():
            self.connect_service()
        if self.runs:
            self.history.setCurrentItem(self.history.topLevelItem(0))
        self.refresh()

    def select_tab(self, index):
        if 0 <= index < len(self.runs):
            self.history.setCurrentItem(self.history.topLevelItem(index))

    def control(self, command):
        run = self.selected
        if run and run.active and getattr(run, 'controlling', True):
            controller = self.run_controller(run)
            if controller:
                controller.control(command)
            elif self.connection_worker:
                self.service_request('/api/command', dict(id=run.service_id, command=command,
                    arguments={'threadId': 1}), run)

    def show_item_information(self, index):
        run, path, line = self.selected, self.model.path, index.row() + 1
        if not run:
            return
        dialog = QDialog(self); dialog.setWindowTitle(f'Item information ? {path.name}:{line}')
        layout = QVBoxLayout(dialog); modes = QComboBox()
        modes.addItems(['Latest information', 'History', 'Full']); layout.addWidget(modes)
        table = QTableWidget(); table.setColumnCount(7)
        table.setHorizontalHeaderLabels(['EX', 'Name', 'Value', 'Status', 'Updated', 'Stack', 'Comments'])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers); layout.addWidget(table)
        raw = QPlainTextEdit(); raw.setReadOnly(True); layout.addWidget(raw)
        more = QPushButton('Load more recorded notifications'); layout.addWidget(more)
        records = []; cursor = 0
        def render():
            mode = modes.currentText()
            raw.setVisible(mode == 'Full'); table.setVisible(mode != 'Full')
            if mode == 'Full':
                raw.setPlainText(json.dumps(records, ensure_ascii=False, indent=2)); return
            merged = {}
            for entry in records:
                event = entry['event']
                if not (event.get('item') or event.get('status') or event.get('value')):
                    continue
                for item in notification_items(event, entry['iteration']):
                    key = (entry['iteration'], event.get('procedureId', ''), item['item'], item['details'].get('ItemType', ''))
                    merged[key] = tuple(item[name] for name in ('iteration', 'item', 'value', 'status', 'timestamp', 'stack', 'comments'))
            latest = max((key[0] for key in merged), default=0)
            rows = [row for row in merged.values() if mode == 'History' or row[0] == latest]
            table.setRowCount(len(rows))
            for n, row in enumerate(rows):
                for col, value in enumerate(row):
                    table.setItem(n, col, QTableWidgetItem(str(value).replace('\4', ' ? ')))
            table.resizeColumnsToContents()
        def load_more():
            nonlocal cursor
            journal = self.service_records if run.service_id and self.service_records else run.journal
            identifier = run.service_id if journal is self.service_records else run.identifier
            page = journal.events(identifier, after=cursor, path=path, line=line,
                latest=modes.currentText() == 'Latest information') if journal else []
            records.extend(page)
            if page: cursor = page[-1]['sequence']
            more.setEnabled(len(page) == 500); render()
        def change_mode():
            nonlocal cursor
            records.clear(); cursor = 0; load_more()
        more.clicked.connect(load_more); modes.currentIndexChanged.connect(change_mode)
        buttons = QDialogButtonBox(QDialogButtonBox.Close); buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons); load_more(); dialog.resize(1000, 500); dialog.exec()

    def begin(self, spec, mode, controller=None):
        self.load_history(spec.project.resolve())
        run = ProcedureRun(spec.project.resolve(), spec.script.resolve(), mode)
        controller = controller or self.controller
        if controller not in self.controllers:
            self.bind_controller(controller)
        self.controllers[controller] = run
        run.journal = self.journal
        self.journal.create(run.project, run.script, mode, run.identifier)
        with tokenize.open(spec.script) as stream:
            run.sources[run.script] = stream.read()
        run.persist()
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
        self.selection_changed.emit()

    def receive_event(self, event, run=None):
        run = run or self.active_run
        if run is None or not run.active:
            return
        run.apply(event)
        if event.get('kind') == 'prompt':
            self.refresh(); self.attention.emit()
        elif not self.refresh_timer.isActive():
            self.refresh_timer.start()

    def append_output(self, text, run=None):
        run = run or self.active_run
        if run and run.active:
            if run.journal:
                run.journal.append(run.identifier, {'kind': 'output', 'text': text})
            run.output = (run.output + text)[-524288:]
            if not self.refresh_timer.isActive():
                self.refresh_timer.start()

    def finish(self, code, run=None):
        run = run or self.active_run
        if any(candidate is run and getattr(controller, 'detaching', False)
               for controller, candidate in self.controllers.items()):
            return
        if run and run.active:
            run.active = False; run.prompt = None; run.answering = False
            run.status = 'Aborted' if run.aborted or code == 130 else f'Finished ({code})' if code == 0 else f'Failed ({code})'
            run.exit_code = code
            run.persist()
            self.refresh()
        if self.active_run is run:
            self.active_run = None
        self.selection_changed.emit()

    def stop_selected(self):
        run = self.selected
        if run and run.active and getattr(run, 'controlling', True):
            controller = self.run_controller(run)
            if controller:
                controller.stop()
            elif self.connection_worker:
                self.service_request('/api/command', dict(id=run.service_id, command='disconnect',
                    arguments={'terminateDebuggee': True}), run)
            else:
                self.controller.stop()
            self.refresh()

    def refresh(self, *_):
        run = self.selected
        self.open_procedure.setEnabled(self.can_start())
        self.export_record.setEnabled(run is not None)
        self.procedure_tabs.blockSignals(True)
        while self.procedure_tabs.count() > len(self.runs):
            self.procedure_tabs.removeTab(self.procedure_tabs.count() - 1)
        for index, entry in enumerate(self.runs):
            text = f'{entry.script.stem} · {(entry.service_id or entry.identifier)[:6]} · {entry.status}'
            if index >= self.procedure_tabs.count():
                self.procedure_tabs.addTab(text)
            else:
                self.procedure_tabs.setTabText(index, text)
            self.procedure_tabs.setTabToolTip(index, str(entry.script))
        self.procedure_tabs.setCurrentIndex(self.runs.index(run) if run in self.runs else -1)
        self.procedure_tabs.blockSignals(False)
        controlling = run is not None and run.active and getattr(run, 'controlling', True) and run.connection != 'Disconnected'
        self.claim.setEnabled(bool(run and run.active and not run.controller and run.connection != 'Disconnected'))
        self.release.setEnabled(controlling and run.status.upper() in {'PAUSED', 'INTERRUPTED', 'PROMPT'})
        paused = run is not None and run.status.upper() in {'PAUSED', 'INTERRUPTED'}
        for name, button in self.control_buttons.items():
            button.setEnabled(controlling and not getattr(run, 'pending', '') and (name == 'abort' or (not paused if name == 'pause' else paused)))
        self.connection.setText(run.connection if run else 'Local')
        self.role.setText('CTRL' if controlling else 'Record' if run and not run.active else 'MON')
        self.role.setStyleSheet('color: ' + ('#008000' if controlling else '#0000ff') + '; font-weight: bold;')
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
        self.state.setStyleSheet('QLabel { color: black; padding: 4px 9px; background: ' + procedure_color(run.status if run else 'UNKNOWN') + '; }')

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
                self.answer_field.setStyleSheet('QLineEdit { background: #ffff00; color: black; }')
                input_type = prompt.get('inputType')
                self.answer_field.setEchoMode(QLineEdit.Password if input_type == 'password' else QLineEdit.Normal)
                self.answer_field.setPlaceholderText('Enter a number' if input_type == 'number' else
                    'Enter a date, e.g. 17-Oct-2026 14:30:00' if input_type == 'date' else 'Enter your answer')
                self.answer_field.returnPressed.connect(self.submit)
                self.prompt_body_layout.addWidget(self.answer_field)
                self.answer_field.setFocus()
        enabled = not run.answering and getattr(run, 'controlling', True) and run.connection != 'Disconnected'
        controller = self.run_controller(run)
        if controller:
            enabled = enabled and controller.input_pending and controller.prompt_id == prompt['promptId']
        self.commit.setEnabled(enabled); self.reset.setEnabled(enabled); self.abort.setEnabled(enabled)
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
        if not run or not run.active or not run.prompt or run.answering or not getattr(run, 'controlling', True):
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
        controller = self.run_controller(run)
        if not controller and run.service_id and self.connection_worker:
            identifier = run.prompt['promptId']; run.answering = True
            self.service_request('/api/command', dict(id=run.service_id, command='spell/promptAnswer',
                arguments=dict(promptId=identifier, value=answer)), run,
                lambda result, error: self.answered(identifier, error, run))
        elif (controller or self.controller).answer_prompt(run.prompt['promptId'], answer):
            run.answering = True; run.error = ''
        else:
            run.error = 'This prompt is no longer accepting an answer.'
        self.refresh()

    def answered(self, identifier, error, run=None):
        run = run or self.active_run
        if run and run.prompt and run.prompt['promptId'] == identifier:
            run.answering = False; run.error = error
            if not error:
                run.prompt = None
            self.refresh()
