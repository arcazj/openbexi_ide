"""debugpy host adapter using standard DAP and a native integrated console."""
from __future__ import annotations

from pathlib import Path
import time

from PySide6.QtCore import QObject, QProcess, QThreadPool, QTimer, Signal
from openbexi_runtime.dap import MessageReader, ProtocolError, encode_message
from openbexi_runtime.launch import LaunchSpec, console_interpreter
from .controller import OwnedProcess, ProbeTask, StreamPump, process_environment


class DebugController(QObject):
    output = Signal(str)
    error = Signal(str)
    finished = Signal(int)
    state_changed = Signal(bool)
    interpreter_checked = Signal(object)
    stopped = Signal(object)
    continued = Signal()
    stack_changed = Signal(object)
    threads_changed = Signal(object)
    breakpoints_verified = Signal(object)
    input_requested = Signal(object)
    procedure_event = Signal(object)
    prompt_answered = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.adapter = OwnedProcess(self)
        self.terminal = OwnedProcess(self)
        self.pump = StreamPump(self.terminal, self)
        self.pump.output.connect(self.output)
        self.adapter.readyReadStandardOutput.connect(self.read_messages)
        self.adapter.readyReadStandardError.connect(self.read_adapter_errors)
        self.adapter.started.connect(self.adapter_started)
        self.adapter.finished.connect(self.adapter_finished)
        self.terminal.started.connect(self.terminal_started)
        self.terminal.finished.connect(self.terminal_finished)
        self.adapter.errorOccurred.connect(lambda error: self.process_error(self.adapter, error))
        self.terminal.errorOccurred.connect(lambda error: self.process_error(self.terminal, error))
        self.adapter.ownership_error.connect(self.fail)
        self.terminal.ownership_error.connect(self.fail)
        self.timer = QTimer(self); self.timer.setInterval(250)
        self.timer.timeout.connect(self.check_timeouts)
        self.epoch = 0
        self.active = False
        self.paused = False
        self.thread_id = None
        self.pending = {}
        self.input_pending = False
        self.backend = None
        self.no_debug = False
        self.prompt_id = None
        self.answer_pending = None
        self.answer_requests = {}

    @property
    def running(self):
        return self.active

    def start(self, spec: LaunchSpec, breakpoints=None, *, no_debug=False):
        if self.active or any(p.state() != QProcess.NotRunning for p in (self.adapter, self.terminal)):
            raise RuntimeError("Stop the current debugger before starting another")
        self.spec = spec.validate()
        self.no_debug = no_debug
        self.backend = None
        self.prompt_id = self.answer_pending = None
        self.answer_requests = {}
        self.breakpoints = {str(Path(path).resolve()): sorted(set(lines))
                            for path, lines in (breakpoints or {}).items()}
        self.epoch += 1
        self.active = self.validating = True
        self.stopping = self.terminated = self.paused = False
        self.thread_id = None
        self.input_pending = False
        self.exit_code = 0
        self.sequence = self.view_generation = 0
        self.pending = {}
        self.reader = MessageReader()
        self.reverse_request = None
        self.pump.reset()
        self.state_changed.emit(True)
        self.probe = ProbeTask(self.epoch, self.spec.interpreter, debugger=True, language=self.spec.language)
        self.probe.signals.done.connect(self.probe_finished)
        QThreadPool.globalInstance().start(self.probe)

    def probe_finished(self, epoch, info, error):
        if epoch != self.epoch or not self.active:
            return
        self.validating = False
        if error:
            self.fail(error); return
        self.interpreter_checked.emit(info)
        self.backend = info.get('backend')
        self.adapter.setWorkingDirectory(str(self.spec.project))
        self.adapter.setProcessEnvironment(process_environment())
        self.timer.start()
        module = self.backend['debugAdapter'] if self.backend else 'debugpy.adapter'
        args = ['--project', str(self.spec.project)] if self.backend else []
        self.adapter.start(str(self.spec.interpreter), ["-I", "-B", "-X", "utf8", "-m", module, *args])

    def adapter_started(self):
        self.request("initialize", {"clientID": "openbexi-python", "adapterID": self.spec.language,
            "linesStartAt1": True, "columnsStartAt1": True, "pathFormat": "path",
            "supportsRunInTerminalRequest": True, "supportsVariableType": True,
            "supportsVariablePaging": True, "supportsArgsCanBeInterpretedByShell": False},
            lambda _body: self.launch())

    def launch(self):
        if self.backend:
            self.request('launch', {'name': self.spec.script.name, 'type': self.spec.language,
                'request': 'launch', 'program': str(self.spec.script), 'project': str(self.spec.project),
                'args': list(self.spec.arguments), 'stopOnEntry': False, 'noDebug': self.no_debug})
            return
        self.request("launch", {"name": self.spec.script.name, "type": "python", "request": "launch",
            "program": self.spec.worker_arguments()[0], "args": self.spec.worker_arguments()[1:],
            "cwd": str(self.spec.project), "python": str(self.spec.interpreter),
            "pythonArgs": ["-I", "-B", "-u", "-X", "utf8"], "console": "integratedTerminal",
            "redirectOutput": False, "justMyCode": True, "subProcess": False,
            "stopOnEntry": False})

    def request(self, command, arguments=None, callback=None):
        if not self.active or self.adapter.state() != QProcess.Running:
            return None
        self.sequence += 1
        sequence = self.sequence
        self.pending[sequence] = (command, callback, time.monotonic())
        self.adapter.write(encode_message({"seq": sequence, "type": "request",
                                          "command": command, "arguments": arguments or {}}))
        return sequence

    def reply(self, request, success=True, body=None, message=None):
        self.sequence += 1
        response = {"seq": self.sequence, "type": "response", "request_seq": request["seq"],
                    "command": request["command"], "success": success, "body": body or {}}
        if message:
            response["message"] = message
        self.adapter.write(encode_message(response))

    def read_messages(self):
        try:
            for message in self.reader.feed(bytes(self.adapter.readAllStandardOutput())):
                self.dispatch(message)
        except (ProtocolError, KeyError, TypeError, ValueError) as error:
            self.fail(f"Debugger protocol error: {error}")

    def dispatch(self, message):
        kind = message["type"]
        if kind == "response":
            pending = self.pending.pop(message.get("request_seq"), None)
            if not pending:
                return
            command, callback, _ = pending
            answered = self.answer_requests.pop(message.get('request_seq'), None)
            if answered is not None:
                self.answer_pending = None
                error = '' if message.get('success') else message.get('message', 'Answer rejected')
                if not error and (self.prompt_id or '') == answered:
                    self.prompt_id = None
                    self.input_pending = False
                self.prompt_answered.emit(answered, error)
                self.state_changed.emit(True)
                return
            if not message.get("success"):
                error = f"{command}: {message.get('message', 'Debugger request failed')}"
                if command in {"initialize", "launch", "configurationDone"}:
                    self.fail(error)
                else:
                    self.error.emit(error)
                    if command in {"continue", "next", "stepIn", "stepOut"}:
                        self.paused = True
                        self.stopped.emit({"threadId": self.thread_id, "reason": "request rejected"})
            elif callback:
                callback(message.get("body", {}))
        elif kind == "request":
            if message.get("command") == "runInTerminal":
                self.run_terminal(message)
            else:
                self.reply(message, False, message="This reverse request is not supported")
        else:
            event, body = message.get("event"), message.get("body", {})
            if event == 'openbexi/procedure' and self.backend:
                if body.get('kind') == 'promptClosed' and body.get('promptId') == self.prompt_id:
                    self.prompt_id = None
                    self.input_pending = False
                    self.state_changed.emit(True)
                self.procedure_event.emit(body)
                return
            if event == "initialized":
                self.configure()
            elif event == "output" and body.get("category") != "telemetry":
                self.output.emit(body.get("output", ""))
            elif event == "stopped":
                self.paused = True
                self.thread_id = body.get("threadId")
                self.view_generation += 1
                self.stopped.emit(body)
                self.request("threads", callback=lambda result: self.threads_changed.emit(result.get("threads", [])))
                if self.thread_id is not None:
                    self.select_thread(self.thread_id)
            elif event == "continued":
                self.paused = False; self.view_generation += 1
                self.continued.emit()
            elif event == "exited":
                self.exit_code = body.get("exitCode", 0)
            elif event == 'openbexi/inputRequest' and self.backend:
                self.input_pending = True
                self.prompt_id = body.get('promptId')
                self.input_requested.emit(body)
                self.state_changed.emit(True)
            elif event == "terminated":
                self.terminated = self.stopping = True
                self.request("disconnect", {"terminateDebuggee": True})
                epoch = self.epoch
                grace = self.backend['gracefulStopMilliseconds'] if self.backend else 150
                QTimer.singleShot(grace, lambda: self.force_end(epoch))

    def configure(self):
        for path, lines in ({} if self.no_debug else self.breakpoints).items():
            self.set_breakpoints(path, lines)
        self.request("setExceptionBreakpoints", {"filters": ["uncaught"]})
        # Requests are ordered on one adapter stream; configurationDone follows
        # breakpoint installation rather than starting a second execution.
        self.request("configurationDone")

    def set_breakpoints(self, path, lines):
        path = str(Path(path).resolve())
        self.breakpoints[path] = sorted(set(lines))
        self.request("setBreakpoints", {"source": {"path": path},
                     "breakpoints": [{"line": line} for line in self.breakpoints[path]]},
                     lambda body: self.breakpoints_verified.emit({"path": path,
                                                                  "breakpoints": body.get("breakpoints", [])}))

    def run_terminal(self, request):
        args = request.get("arguments", {})
        command = args.get("args")
        if (not isinstance(command, list) or len(command) < 2
                or not all(isinstance(value, str) and "\0" not in value for value in command)
                or console_interpreter(command[0]) != self.spec.interpreter
                or args.get("argsCanBeInterpretedByShell", False)
                or self.terminal.state() != QProcess.NotRunning):
            self.reply(request, False, message="Invalid integrated-console launch")
            self.fail("The debugger requested an invalid console launch"); return
        self.reverse_request = request
        self.terminal.setWorkingDirectory(str(self.spec.project))
        self.terminal.setProcessEnvironment(process_environment(args.get("env")))
        self.terminal.start(command[0], command[1:])

    def terminal_started(self):
        if self.reverse_request:
            self.reply(self.reverse_request, body={"processId": int(self.terminal.processId())})
            self.reverse_request = None
        self.state_changed.emit(True)

    def read_adapter_errors(self):
        text = bytes(self.adapter.readAllStandardError()).decode("utf-8", "replace")
        if text:
            self.output.emit(text)

    def select_thread(self, thread_id):
        if not self.paused:
            return
        self.thread_id = thread_id
        self.view_generation += 1
        generation = self.view_generation
        def received(body):
            if self.paused and generation == self.view_generation:
                self.stack_changed.emit(body.get("stackFrames", []))
        self.request("stackTrace", {"threadId": thread_id, "startFrame": 0, "levels": 50}, received)

    def view_request(self, command, arguments, callback):
        generation = self.view_generation
        def received(body):
            if self.paused and generation == self.view_generation:
                callback(body)
        self.request(command, arguments, received)

    def control(self, command):
        if command == "pause":
            def pause_thread(body):
                threads = body.get("threads", [])
                if threads:
                    self.request("pause", {"threadId": self.thread_id or threads[0]["id"]})
            self.request("threads", callback=pause_thread)
        elif self.paused and self.thread_id is not None:
            if self.request(command, {"threadId": self.thread_id}) is not None:
                self.paused = False; self.view_generation += 1
                self.continued.emit()

    def send_input(self, text):
        if self.terminal.state() == QProcess.Running:
            self.terminal.write((text + "\n").encode("utf-8"))
        elif self.backend and self.input_pending:
            self.answer_prompt(self.prompt_id, text)

    def answer_prompt(self, identifier, text):
        if not self.input_pending or identifier != self.prompt_id or self.answer_pending is not None:
            return False
        sequence = self.request('openbexi/input', {'text': text, **({'promptId': identifier} if identifier else {})})
        if sequence is None:
            return False
        self.answer_pending = identifier or ''
        self.answer_requests[sequence] = identifier or ''
        return True

    def close_input(self):
        self.terminal.closeWriteChannel()

    def check_timeouts(self):
        now = time.monotonic()
        for sequence, (command, _callback, started) in list(self.pending.items()):
            if now - started > (30 if command == "launch" else 10):
                self.pending.pop(sequence, None)
                if sequence in self.answer_requests:
                    identifier = self.answer_requests.pop(sequence)
                    self.answer_pending = None
                    self.prompt_answered.emit(identifier, 'The answer request timed out. Check the procedure state before retrying.')
                if command in {"initialize", "launch", "configurationDone"}:
                    self.fail(f"Debugger timed out during {command}"); return
                self.error.emit(f"Debugger request timed out: {command}")

    def process_error(self, process, error):
        if error == QProcess.FailedToStart:
            if process is self.terminal and self.reverse_request:
                self.reply(self.reverse_request, False, message=process.errorString())
                self.reverse_request = None
            self.fail(process.errorString())
        elif error != QProcess.Crashed or not self.stopping:
            self.error.emit(process.errorString())

    def terminal_finished(self, _code, _status):
        self.pump.finish()
        self.maybe_finish()

    def adapter_finished(self, _code, _status):
        self.read_messages(); self.read_adapter_errors()
        if self.active and not self.stopping:
            self.error.emit("Debugger adapter exited unexpectedly")
            self.exit_code = -1
        self.force_end(self.epoch)

    def fail(self, message):
        self.error.emit(message)
        self.exit_code = -1
        self.stop()

    def stop(self):
        if not self.active:
            return
        if not self.terminated and self.exit_code == 0:
            self.exit_code = 130
        self.stopping = True
        if self.validating:
            self.probe.cancel.set()
            self.epoch += 1; self.validating = False
            self.maybe_finish(); return
        self.request("disconnect", {"terminateDebuggee": True})
        epoch = self.epoch
        grace = self.backend['gracefulStopMilliseconds'] if getattr(self, 'backend', None) else 250
        QTimer.singleShot(grace, lambda: self.force_end(epoch))

    def force_end(self, epoch):
        if epoch != self.epoch or not self.active:
            return
        self.stopping = True
        self.terminal.kill_tree(); self.adapter.kill_tree()
        self.maybe_finish()

    def maybe_finish(self):
        if self.active and not self.validating and all(p.state() == QProcess.NotRunning for p in (self.adapter, self.terminal)):
            self.active = self.paused = False
            self.input_pending = False
            self.prompt_id = self.answer_pending = None
            self.answer_requests.clear()
            self.timer.stop(); self.pending.clear()
            self.state_changed.emit(False)
            self.finished.emit(self.exit_code)
