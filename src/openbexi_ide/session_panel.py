"""Shared-session membership, procedure queue and read-only live inspection."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox,
    QSplitter, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from openbexi_runtime.session import TERMINAL
from .fonts import fixed_font


class JoinDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Join shared session')
        layout = QVBoxLayout(self)
        description = QLabel('Developers can claim control. Monitors can inspect output and stacks.')
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        self.url = QLineEdit('http://127.0.0.1:9010')
        self.user = QLineEdit(os.environ.get('USERNAME', 'Developer'))
        self.role = QComboBox()
        self.role.addItem('Developer', 'developer')
        self.role.addItem('Monitor (read-only)', 'monitor')
        self.file = QLineEdit()
        default = Path.cwd()/'.session/server.json'
        if default.is_file():
            self.file.setText(str(default))
        self.file.setPlaceholderText('Private invitation JSON')
        file_row = QHBoxLayout()
        file_row.addWidget(self.file)
        browse = QPushButton('Browse…')
        browse.clicked.connect(self.browse)
        file_row.addWidget(browse)
        self.invite = QLineEdit()
        self.invite.setEchoMode(QLineEdit.Password)
        self.invite.setPlaceholderText('Or paste the invitation for your selected role')
        form.addRow('Session URL', self.url)
        form.addRow('Your name', self.user)
        form.addRow('Role', self.role)
        form.addRow('Invitation file', file_row)
        form.addRow('Invitation', self.invite)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(570, 330)

    def browse(self):
        name, _ = QFileDialog.getOpenFileName(self, 'Private invitation file', self.file.text(), 'JSON (*.json)')
        if name:
            self.file.setText(name)

    def values(self):
        return {'user': self.user.text().strip(), 'url': self.url.text().strip() or None,
                'role': self.role.currentData(), 'invite_file': self.file.text().strip() or None,
                'invite': self.invite.text().strip() or None}


class SessionPanel(QWidget):
    join_requested = Signal()
    open_project_requested = Signal(str)
    frame_activated = Signal(object)
    selection_changed = Signal()

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self.preferred = None
        self._frame_key = None
        self._output_cursor = 0
        self._output_procedure = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 10)
        self.status = QLabel('Join a session to share Python or SPELL execution.')
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        connections = QHBoxLayout()
        self.join = QPushButton('Join Session…')
        self.join.clicked.connect(self.join_requested)
        self.claim = QPushButton('Claim control')
        self.claim.clicked.connect(lambda: client.command('claim'))
        self.release = QPushButton('Release control')
        self.release.clicked.connect(lambda: client.command('release'))
        self.disconnect = QPushButton('Disconnect')
        self.disconnect.clicked.connect(client.disconnect)
        self.open_folder = QPushButton('Open session folder')
        self.open_folder.clicked.connect(lambda: self.open_project_requested.emit(client.snapshot.get('project', '')))
        for button in (self.join, self.claim, self.release, self.disconnect, self.open_folder):
            connections.addWidget(button)
        connections.addStretch()
        layout.addLayout(connections)
        controls = QHBoxLayout()
        self.scope = QComboBox()
        self.scope.addItem('Selected procedure', 'selected')
        self.scope.addItem('All procedures', 'all')
        self.scope.currentIndexChanged.connect(self.refresh_controls)
        controls.addWidget(self.scope)
        self.pause = QPushButton('Pause')
        self.resume = QPushButton('Resume')
        self.stop = QPushButton('Stop')
        for name in ('pause', 'resume', 'stop'):
            button = getattr(self, name)
            button.clicked.connect(lambda _checked=False, operation=name: self.control(operation))
            controls.addWidget(button)
        controls.addStretch()
        controls.addWidget(QLabel('Slots'))
        self.slots = QSpinBox()
        self.slots.setRange(1, 16)
        self.slots.setToolTip('1 runs serially; more slots permit bounded parallel procedures')
        controls.addWidget(self.slots)
        self.apply_slots = QPushButton('Apply')
        self.apply_slots.clicked.connect(lambda: client.command('configure', max_parallel=self.slots.value()))
        controls.addWidget(self.apply_slots)
        self.keep_control = QCheckBox('Keep control')
        self.keep_control.setChecked(True)
        self.keep_control.setToolTip('Renew your lease while this desktop stays connected')
        self.keep_control.toggled.connect(self.set_keep_control)
        controls.addWidget(self.keep_control)
        layout.addLayout(controls)
        details = QSplitter(Qt.Horizontal)
        left = QTabWidget()
        self.procedures = QTreeWidget()
        self.procedures.setHeaderLabels(['Procedure', 'Language', 'State', 'Slot', 'Detail'])
        self.procedures.setColumnWidth(0, 160)
        self.procedures.setColumnWidth(2, 90)
        self.procedures.setRootIsDecorated(False)
        self.procedures.setSelectionMode(QTreeWidget.SingleSelection)
        self.procedures.currentItemChanged.connect(self.select_procedure)
        self.members = QTreeWidget()
        self.members.setHeaderLabels(['Developer', 'Role', 'Control'])
        self.members.setRootIsDecorated(False)
        left.addTab(self.procedures, 'Procedures')
        left.addTab(self.members, 'Developers')
        right = QTabWidget()
        stack_view = QSplitter(Qt.Vertical)
        self.stack = QTreeWidget()
        self.stack.setHeaderLabels(['Live Python stack', 'Line'])
        self.stack.setColumnWidth(0, 300)
        self.stack.currentItemChanged.connect(self.select_frame)
        self.stack.itemDoubleClicked.connect(self.activate_frame)
        self.locals = QTreeWidget()
        self.locals.setHeaderLabels(['Local name', 'Value'])
        self.locals.setRootIsDecorated(False)
        self.locals.setColumnWidth(0, 150)
        stack_view.addWidget(self.stack)
        stack_view.addWidget(self.locals)
        stack_view.setSizes([160, 90])
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(fixed_font())
        self.output.setMaximumBlockCount(2000)
        self.output.setPlaceholderText('Select a procedure to inspect its output.')
        right.addTab(stack_view, 'Live stack')
        right.addTab(self.output, 'Selected output')
        details.addWidget(left)
        details.addWidget(right)
        details.setSizes([550, 450])
        layout.addWidget(details)
        client.changed.connect(self.refresh_controls)
        client.snapshot_changed.connect(self.update_snapshot)
        client.submitted.connect(self.prefer_procedure)
        self.refresh_controls()

    @property
    def selected(self):
        item = self.procedures.currentItem()
        return item.data(0, Qt.UserRole) if item else None

    @property
    def target(self):
        return 'all' if self.scope.currentData() == 'all' else (self.selected or {}).get('id')

    def prefer_procedure(self, identifier):
        self.preferred = identifier

    def set_keep_control(self, checked):
        self.client.keep_control = checked

    def control(self, action):
        if self.target:
            self.client.command(action, procedure=self.target)

    def refresh_controls(self, *_):
        client = self.client
        owner = client.snapshot.get('controller') or {}
        if client.state == 'local':
            text = 'Local workspace · join to share Python or SPELL execution.'
        elif client.state == 'joining':
            text = 'Connecting to the shared session…'
        elif client.state == 'leaving':
            text = 'Disconnecting and releasing any controller ownership…'
        elif not client.healthy:
            text = 'Session unavailable · execution controls are disabled.'
        else:
            mode = 'Monitoring (read-only)' if client.identity.get('role') == 'monitor' else 'Development'
            occupied = sum(p['has_token'] for p in client.snapshot.get('procedures', []))
            text = f"{mode} · {client.url} · Controller: {owner.get('name', 'unclaimed')} · {occupied}/{client.snapshot.get('max_parallel', 1)} slots"
        self.status.setText(text)
        self.status.setToolTip(client.snapshot.get('project', ''))
        self.join.setEnabled(not client.active)
        self.claim.setEnabled(client.can_claim)
        self.release.setEnabled(client.can_control)
        self.disconnect.setEnabled(client.active and client.state != 'leaving')
        self.open_folder.setEnabled(client.state == 'joined' and bool(client.snapshot.get('project')))
        self.slots.setEnabled(client.can_control)
        self.apply_slots.setEnabled(client.can_control)
        self.keep_control.setEnabled(client.identity.get('role') == 'developer' and client.state == 'joined')
        selected = client.snapshot.get('procedures', []) if self.target == 'all' else [self.selected] if self.selected else []
        active = [p for p in selected if p['status'] not in TERMINAL]
        held = any(p['status'] == 'RECOVERY_REQUIRED' for p in active)
        self.pause.setEnabled(client.can_control and not held and any(p['status'] not in {'PAUSED', 'STOPPING'} for p in active))
        self.resume.setEnabled(client.can_control and bool(active) and all(p['status'] == 'PAUSED' for p in active))
        self.stop.setEnabled(client.can_control and bool(active) and not held)

    def update_snapshot(self, snapshot):
        current = self.preferred or (self.selected or {}).get('id')
        self.members.clear()
        owner = (snapshot.get('controller') or {}).get('id')
        for member in snapshot.get('clients', []):
            name = member['name'] + (' (you)' if member['id'] == self.client.identity.get('client') else '')
            row = QTreeWidgetItem([name, member['role'], 'Controller' if member['id'] == owner else ''])
            row.setToolTip(0, member['id'])
            self.members.addTopLevelItem(row)
        self.procedures.blockSignals(True)
        self.procedures.clear()
        chosen = None
        for procedure in snapshot.get('procedures', []):
            detail = procedure.get('error') or procedure.get('pause_reason') or (
                'Exit ' + str(procedure['exit_code']) if procedure.get('exit_code') is not None else '')
            row = QTreeWidgetItem([procedure['script'], procedure['language'], procedure['status'],
                                  'Granted' if procedure['has_token'] else '', detail])
            row.setData(0, Qt.UserRole, procedure)
            row.setToolTip(0, procedure['id'])
            self.procedures.addTopLevelItem(row)
            if procedure['id'] == current:
                chosen = row
            elif chosen is None and current is None and procedure['status'] not in TERMINAL:
                chosen = row
        if chosen:
            self.procedures.setCurrentItem(chosen)
            self.preferred = None
        self.procedures.blockSignals(False)
        if not self.slots.hasFocus():
            self.slots.setValue(snapshot['max_parallel'])
        self.select_procedure()

    def select_procedure(self, *_):
        self.refresh_controls()
        procedure = self.selected or {}
        self.stack.blockSignals(True)
        self.stack.clear()
        chosen = None
        for thread in procedure.get('threads', []):
            root = QTreeWidgetItem([thread.get('name', 'Python thread') + (' · paused' if thread.get('paused') else ''), ''])
            self.stack.addTopLevelItem(root)
            for depth, frame in enumerate(thread.get('stack', [])):
                row = QTreeWidgetItem([frame['function'] + ' · ' + Path(frame['file']).name, str(frame['line'])])
                key = (thread['id'], depth)
                row.setData(0, Qt.UserRole, {'frame': frame, 'key': key})
                row.setToolTip(0, frame['file'])
                root.addChild(row)
                if key == self._frame_key or chosen is None:
                    chosen = row
            root.setExpanded(True)
        if chosen:
            self.stack.setCurrentItem(chosen)
        self.stack.blockSignals(False)
        self.select_frame(chosen)
        identifier = procedure.get('id')
        if identifier != self._output_procedure:
            self.output.clear()
            self._output_cursor = 0
            self._output_procedure = identifier
        for event in self.client.outputs:
            if event['sequence'] > self._output_cursor and event.get('procedure') == identifier:
                cursor = self.output.textCursor()
                cursor.movePosition(cursor.MoveOperation.End)
                cursor.insertText(event['text'])
                self.output.setTextCursor(cursor)
            self._output_cursor = max(self._output_cursor, event['sequence'])
        if self.output.document().characterCount() > 500000:
            text = self.output.toPlainText()[-400000:]
            self.output.setPlainText(text)
        self.selection_changed.emit()

    def select_frame(self, item=None, *_):
        self.locals.clear()
        data = item.data(0, Qt.UserRole) if item else None
        if data:
            self._frame_key = data['key']
            for name, value in data['frame'].get('locals', {}).items():
                self.locals.addTopLevelItem(QTreeWidgetItem([name, value]))

    def activate_frame(self, item, *_):
        data = item.data(0, Qt.UserRole)
        if data:
            self.frame_activated.emit(data['frame'])
