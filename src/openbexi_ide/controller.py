"""Responsive Qt bridges for the independent runtime and owned child processes."""
import codecs
import os
import threading

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QRunnable, QThreadPool, QTimer, Signal
from openbexi_runtime.launch import LaunchSpec, clean_environment, interpreter_info
from openbexi_runtime.processes import ProcessTree


class ProbeSignals(QObject):
    done = Signal(int, object, str)


class ProbeTask(QRunnable):
    def __init__(self, epoch, interpreter, debugger=False):
        super().__init__()
        self.epoch, self.interpreter, self.debugger = epoch, interpreter, debugger
        self.signals = ProbeSignals()
        self.cancel = threading.Event()

    def run(self):
        try:
            result = interpreter_info(self.interpreter, require_debugger=self.debugger, cancel=self.cancel)
            self.signals.done.emit(self.epoch, result, "")
        except Exception as error:
            self.signals.done.emit(self.epoch, None, str(error))


def process_environment(extra=None):
    values = clean_environment()
    for key, value in (extra or {}).items():
        if value is None:
            values.pop(key, None)
        else:
            values[key] = str(value)
    environment = QProcessEnvironment()
    for key, value in values.items():
        environment.insert(key, value)
    return environment


class OwnedProcess(QProcess):
    ownership_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.owner = None
        if os.name != "nt":
            self.setUnixProcessParameters(QProcess.UnixProcessFlag.CreateNewSession)
        self.started.connect(self.claim_tree)
        self.finished.connect(self.release_tree)

    def claim_tree(self):
        try:
            self.owner = ProcessTree(int(self.processId()))
        except (OSError, ValueError, RuntimeError) as error:
            if self.state() == QProcess.NotRunning:
                return
            self.ownership_error.emit(f"Unable to own the child process tree: {error}")
            self.kill()

    def release_tree(self, *_):
        if self.owner:
            owner, self.owner = self.owner, None
            try:
                owner.close()
            except OSError as error:
                self.ownership_error.emit(f"Process cleanup failed: {error}")

    def kill_tree(self):
        self.release_tree()
        if self.state() != QProcess.NotRunning:
            self.kill()


class StreamPump(QObject):
    output = Signal(str)

    def __init__(self, process, parent=None):
        super().__init__(parent)
        self.process = process
        self.timer = QTimer(self); self.timer.setInterval(35)
        self.timer.timeout.connect(self.flush)
        process.readyReadStandardOutput.connect(self.read_stdout)
        process.readyReadStandardError.connect(self.read_stderr)
        self.reset()

    def reset(self):
        self.timer.stop()
        self.pending = ""
        self.truncated = False
        self.decoders = [codecs.getincrementaldecoder("utf-8")("replace") for _ in range(2)]

    def read_stdout(self):
        self.append(self.decoders[0].decode(bytes(self.process.readAllStandardOutput())))

    def read_stderr(self):
        self.append(self.decoders[1].decode(bytes(self.process.readAllStandardError())))

    def append(self, content):
        self.pending += content
        if len(self.pending) > 128_000:
            self.pending = self.pending[-128_000:]; self.truncated = True
        if content and not self.timer.isActive():
            self.timer.start()

    def flush(self):
        self.timer.stop()
        if self.pending or self.truncated:
            text = ("\n[Earlier output omitted from the live view]\n" if self.truncated else "") + self.pending
            self.pending, self.truncated = "", False
            self.output.emit(text)

    def finish(self):
        self.read_stdout(); self.read_stderr()
        for decoder in self.decoders:
            self.append(decoder.decode(b"", final=True))
        self.flush()


class RunController(QObject):
    output = Signal(str)
    finished = Signal(int)
    state_changed = Signal(bool)
    error = Signal(str)
    interpreter_checked = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = OwnedProcess(self)
        self.pump = StreamPump(self.process, self)
        self.pump.output.connect(self.output)
        self.process.finished.connect(self.on_finished)
        self.process.errorOccurred.connect(self.on_error)
        self.process.ownership_error.connect(self.error)
        self.epoch = 0
        self.validating = False
        self.active = False
        self.stopping = False

    @property
    def running(self):
        return self.active

    def start(self, spec: LaunchSpec):
        if self.running:
            raise RuntimeError("Stop the current script before starting another")
        self.spec = spec.validate()
        self.epoch += 1
        self.validating = self.active = True
        self.stopping = False
        self.pump.reset()
        self.state_changed.emit(True)
        self.probe = ProbeTask(self.epoch, self.spec.interpreter)
        self.probe.signals.done.connect(self.probe_finished)
        QThreadPool.globalInstance().start(self.probe)

    def probe_finished(self, epoch, info, error):
        if epoch != self.epoch or not self.active:
            return
        self.validating = False
        if error:
            self.error.emit(error); self.finish(-1); return
        self.interpreter_checked.emit(info)
        self.process.setProcessEnvironment(process_environment())
        self.process.setWorkingDirectory(str(self.spec.project))
        command = self.spec.command()
        self.process.start(command[0], command[1:])

    def on_finished(self, code, _status):
        self.pump.finish()
        self.finish(code)

    def finish(self, code):
        if self.active:
            self.active = self.validating = False
            self.state_changed.emit(False)
            self.finished.emit(code)

    def on_error(self, error):
        if error == QProcess.FailedToStart:
            self.error.emit(self.process.errorString()); self.finish(-1)
        elif error != QProcess.Crashed or not self.stopping:
            self.error.emit(self.process.errorString())

    def send_input(self, text):
        if self.process.state() == QProcess.Running:
            self.process.write((text + "\n").encode("utf-8"))

    def close_input(self):
        self.process.closeWriteChannel()

    def stop(self):
        if not self.active:
            return
        self.stopping = True
        if self.validating:
            self.probe.cancel.set()
            self.epoch += 1
            self.finish(-1)
        else:
            self.process.kill_tree()
