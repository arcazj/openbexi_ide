"""Background connection to the authoritative procedure workspace."""
from queue import Queue, Empty
import threading

from PySide6.QtCore import QObject, Signal
from openbexi_runtime.procedure_client import Client


class ProcedureConnection(QObject):
    snapshot = Signal(object)
    completed = Signal(object, object, str)
    disconnected = Signal(str)

    def __init__(self, endpoint, parent=None):
        super().__init__(parent)
        self.endpoint = endpoint
        self.commands = Queue()
        self.closed = threading.Event()
        self.client = None
        self.revision = None
        self.destroyed.connect(lambda: self.closed.set())
        threading.Thread(target=self.work, daemon=True, name='procedure-workspace').start()

    def request(self, path, data, callback=None):
        self.commands.put((path, data, callback))

    def work(self):
        while not self.closed.is_set():
            try:
                if self.client is None:
                    self.client = Client.connect(self.endpoint, 'Desktop workspace')
                state = self.client.request('/api/state', timeout=3)
                if self.revision != state['revision']:
                    self.revision = state['revision']; self.snapshot.emit(state)
                try:
                    path, data, callback = self.commands.get(timeout=.6)
                except Empty:
                    continue
                try:
                    result = self.client.request(path, data)
                    self.completed.emit(callback, result, '')
                except Exception as error:
                    self.completed.emit(callback, None, str(error))
            except Exception as error:
                self.client = None
                self.revision = None
                self.disconnected.emit(str(error))
                self.closed.wait(2)
        if self.client:
            try:
                self.client.request('/api/disconnect', {}, timeout=3)
            except Exception:
                pass

    def close(self):
        self.closed.set()
