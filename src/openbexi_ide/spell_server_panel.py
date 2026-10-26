"""Asynchronous v0.8 server panel, separate from legacy session controls."""

import queue
import threading
import uuid

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openbexi_runtime.spell_server_client import SpellServerClient


class ServerWorker(QObject):
    completed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.jobs = queue.Queue(maxsize=1)
        self.closed = threading.Event()
        self.cleanup = None
        self.thread = threading.Thread(
            target=self.run, name="spell-v08-client", daemon=True
        )
        self.thread.start()

    def run(self):
        try:
            while not self.closed.is_set():
                try:
                    operation = self.jobs.get(timeout=0.1)
                except queue.Empty:
                    continue
                try:
                    result = operation()
                    item = {"result": result}
                except Exception as error:
                    item = {"error": str(error)}
                if not self.closed.is_set():
                    self.completed.emit(item)
        finally:
            if self.cleanup is not None:
                self.cleanup()

    def submit(self, operation):
        try:
            self.jobs.put_nowait(operation)
            return True
        except queue.Full:
            return False

    def close(self, cleanup=None):
        if cleanup is not None:
            self.cleanup = cleanup
        self.closed.set()


class SpellServerPanel(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.client = None
        self.connections = {}
        self.closing_keys = {}
        self.state = {}
        self.busy = False
        self.worker = ServerWorker(self)
        self.worker.completed.connect(self.receive, Qt.QueuedConnection)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.connect_button = QPushButton("Connect to server…")
        self.refresh_button = QPushButton("Refresh")
        self.disconnect_button = QPushButton("Disconnect")
        self.context = QComboBox()
        row.addWidget(self.connect_button)
        row.addWidget(self.context)
        row.addWidget(self.refresh_button)
        row.addWidget(self.disconnect_button)
        layout.addLayout(row)
        self.status = QLabel("Choose a server connection file")
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        self.executions = QTreeWidget()
        self.executions.setHeaderLabels(
            ["Procedure", "Controller", "State", "Control request"]
        )
        layout.addWidget(self.executions)
        controls = QHBoxLayout()
        self.procedures = QComboBox()
        controls.addWidget(self.procedures)
        self.reserve_button = QPushButton("Reserve")
        self.rebind_button = QPushButton("Reconnect control")
        self.claim_button = QPushButton("Request control")
        self.accept_button = QPushButton("Accept request")
        self.reject_button = QPushButton("Reject request")
        for button in (
            self.reserve_button,
            self.rebind_button,
            self.claim_button,
            self.accept_button,
            self.reject_button,
        ):
            controls.addWidget(button)
        layout.addLayout(controls)
        command_row = QHBoxLayout()
        self.command_buttons = {}
        for label, command in (
            ("Run / Continue", "CMD_RUN"),
            ("Step", "CMD_STEP"),
            ("Pause", "CMD_PAUSE"),
            ("Abort", "CMD_ABORT"),
            ("Close execution", "CMD_CLOSE"),
        ):
            button = QPushButton(label)
            button.clicked.connect(
                lambda checked=False, op=command: self.send_command(op)
            )
            self.command_buttons[command] = button
            command_row.addWidget(button)
        layout.addLayout(command_row)
        self.connect_button.clicked.connect(self.choose_connection)
        self.refresh_button.clicked.connect(self.refresh)
        self.disconnect_button.clicked.connect(self.disconnect_server)
        self.context.currentTextChanged.connect(self.refresh)
        self.executions.itemSelectionChanged.connect(self.update_buttons)
        self.reserve_button.clicked.connect(lambda: self.mutate("reserve"))
        self.rebind_button.clicked.connect(lambda: self.mutate("rebind"))
        self.claim_button.clicked.connect(lambda: self.mutate("claim"))
        self.accept_button.clicked.connect(lambda: self.mutate("accept"))
        self.reject_button.clicked.connect(lambda: self.mutate("reject"))
        self.update_buttons()

    def choose_connection(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Server connection", "", "JSON (*.json)"
        )
        if path:
            self.connect_config(path)

    def connect_config(self, path):
        if self.busy:
            return
        # A connection switch must not silently abandon logical controllers.
        if self.connections:
            self.status.setText("Close this server panel before switching connections")
            return

        def connect():
            client = SpellServerClient.from_config(path)
            return {"client": client, "contexts": client.contexts()}

        self.submit(connect)

    def submit(self, operation):
        if self.busy:
            return
        self.busy = True
        self.update_buttons()
        self.worker.submit(operation)

    def refresh(self):
        if self.busy or self.client is None or not self.context.currentText():
            return
        context, client = self.context.currentText(), self.client
        self.submit(
            lambda: {
                "context": context,
                "health": client.read(context, "health"),
                "procedures": client.read(context, "procedures"),
                "executions": client.read(context, "executions"),
            }
        )

    def selected(self):
        item = self.executions.currentItem()
        return item.data(0, Qt.UserRole) if item else None

    def receive(self, item):
        self.busy = False
        if "error" in item:
            self.state = {}
            self.status.setText(item["error"])
        else:
            result = item["result"]
            if result.get("disconnected"):
                self.client = None
                self.state = {}
                self.context.clear()
                self.executions.clear()
                self.procedures.clear()
                self.status.setText("Disconnected")
            elif "client" in result:
                if self.client:
                    self.client.forget()
                self.client = result["client"]
                self.context.blockSignals(True)
                self.context.clear()
                self.context.addItems(result["contexts"])
                self.context.blockSignals(False)
                self.refresh()
            elif "context" in result:
                self.state = result
                health = result["health"]
                self.status.setText(
                    "Connected • "
                    + health["subject"]
                    + (
                        " • execution unavailable"
                        if not health["runtime_enabled"]
                        and not health.get("native_commands")
                        else ""
                    )
                )
                selected = (self.selected() or {}).get("id")
                self.executions.clear()
                for execution in result["executions"]["executions"]:
                    claim = execution.get("pending_claim") or {}
                    row = QTreeWidgetItem(
                        [
                            execution["procedure_id"],
                            execution["owner"],
                            execution["control_state"],
                            claim.get("requester", ""),
                        ]
                    )
                    row.setData(0, Qt.UserRole, execution)
                    self.executions.addTopLevelItem(row)
                    if execution["id"] == selected:
                        self.executions.setCurrentItem(row)
                self.procedures.clear()
                for procedure in result["procedures"]["procedures"]:
                    self.procedures.addItem(procedure["procedure_id"], procedure)
            else:
                self.refresh()
        self.update_buttons()
        self.changed.emit()

    def update_buttons(self):
        ready = not self.busy and self.client is not None
        health = self.state.get("health", {})
        permissions = set(health.get("permissions", []))
        execution = self.selected() or {}
        owner = execution.get("owner") == health.get("subject") and bool(execution)
        control = ready and "execution:control" in permissions
        self.connect_button.setEnabled(not self.busy and not self.connections)
        self.context.setEnabled(ready)
        self.refresh_button.setEnabled(ready)
        self.disconnect_button.setEnabled(ready)
        self.reserve_button.setEnabled(
            control and "execution:start" in permissions and self.procedures.count() > 0
        )
        self.rebind_button.setEnabled(
            control
            and owner
            and (
                execution.get("lifecycle") == "RESERVED"
                or execution.get("control_state") == "HANDOFF_PAUSED"
            )
        )
        self.claim_button.setEnabled(
            control
            and not owner
            and bool(execution)
            and "execution:request_control" in permissions
            and not execution.get("pending_claim")
        )
        has_proof = (
            control
            and owner
            and self.client.has_controller(
                self.context.currentText(), execution.get("id")
            )
        )
        for button in (self.accept_button, self.reject_button):
            button.setEnabled(
                control and owner and has_proof and bool(execution.get("pending_claim"))
            )
        available = set(health.get("native_commands", []))
        for command, button in self.command_buttons.items():
            button.setEnabled(
                bool(has_proof)
                and execution.get("lifecycle") == "STARTING"
                and (
                    execution.get("control_state") == "OWNED"
                    or (
                        execution.get("control_state") == "HANDOFF_PAUSED"
                        and command == "CMD_RUN"
                    )
                )
                and command in available
            )

    def send_command(self, command):
        button = self.command_buttons.get(command)
        if button is None or not button.isEnabled() or self.busy or self.client is None:
            return
        execution = dict(self.selected() or {})
        context, client = self.context.currentText(), self.client
        key = str(uuid.uuid4())

        def action():
            result = client.command(context, execution["id"], command, key=key)
            return {"command_result": result}

        self.submit(action)

    def mutate(self, operation):
        if self.busy or self.client is None:
            return
        context, client = self.context.currentText(), self.client
        execution = dict(self.selected() or {})
        procedure = self.procedures.currentData()

        def action():
            if context not in self.connections:
                self.connections[context] = client.authority(
                    context, "session.open", {}, key=str(uuid.uuid4())
                )["connection_id"]
            connection = self.connections[context]
            key = str(uuid.uuid4())
            if operation == "reserve":
                payload = {
                    name: procedure[name]
                    for name in (
                        "procedure_id",
                        "source_revision",
                        "source_sha256",
                        "runtime_image",
                        "driver_binding",
                    )
                }
                result = client.authority(
                    context,
                    "execution.reserve",
                    {**payload, "connection_id": connection},
                    key=key,
                )
                client.remember_controller(context, result)
            elif operation in ("accept", "reject"):
                client.decide(
                    context,
                    execution["id"],
                    execution["pending_claim"]["id"],
                    operation,
                    key=key,
                )
            else:
                result = client.authority(
                    context,
                    "execution." + operation,
                    {
                        "execution_id": execution["id"],
                        "expected_epoch": execution["epoch"],
                        "connection_id": connection,
                    },
                    key=key,
                )
                if operation == "rebind":
                    client.remember_controller(context, result)
            return {}

        self.submit(action)

    def disconnect_server(self):
        if self.busy or self.client is None:
            return
        client = self.client

        def disconnect():
            for context, connection in list(self.connections.items()):
                key = self.closing_keys.setdefault(context, str(uuid.uuid4()))
                client.authority(
                    context, "session.close", {"connection_id": connection}, key=key
                )
                del self.connections[context]
                del self.closing_keys[context]
            client.forget()
            return {"disconnected": True}

        self.submit(disconnect)

    def close_connection(self):
        # Closing the window is transport detach, not a proven controller close.
        # Persisted server authority is never cleared on a failed/omitted close.
        self.worker.close(self.client.forget if self.client else None)
