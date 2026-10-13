"""Desktop view of cached debugger state with fenced controller requests."""
from collections import deque
import json
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal


class SharedDebugController(QObject):
    stopped = Signal(object)
    continued = Signal()
    stack_changed = Signal(object)
    threads_changed = Signal(object)
    breakpoints_verified = Signal(object)
    views_changed = Signal()
    error = Signal(str)

    def __init__(self, client, selection, parent=None):
        super().__init__(parent)
        self.client, self.selection = client, selection
        self.view_generation = 0
        self._key = None
        self._signature = None
        self._frames_signature = None
        self._threads_signature = None
        self._views_signature = None
        self._breakpoints_signature = None
        self._was_paused = False
        self._refresh_queued = False
        self._selected_thread = None
        self._pending = None
        self._reads = deque(maxlen=16)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.flush_reads)
        self.timer.start()
        client.changed.connect(self.schedule_refresh)
        client.snapshot_changed.connect(self.schedule_refresh)
        client.debug_result.connect(self.received)

    @property
    def procedure(self):
        selected = self.selection() or {}
        return next((row for row in self.client.snapshot.get('procedures', [])
                     if row['id'] == selected.get('id') and row.get('debug')), None)

    @property
    def state(self):
        return (self.procedure or {}).get('debug') or {}

    @property
    def running(self):
        return self.client.active and self.state.get('enabled', False) and self.state.get('state') not in {'terminated', 'unavailable'}

    @property
    def paused(self):
        return self.running and self.state.get('state') == 'paused'

    @property
    def thread_id(self):
        identifiers = {thread['id'] for thread in self.state.get('threads', [])}
        return self._selected_thread if self._selected_thread in identifiers else self.state.get('thread_id')

    @property
    def backend(self):
        return dict(supportsStepOut=self.state.get('capabilities', {}).get('supportsStepOut', True))

    def schedule_refresh(self, *_):
        if not self._refresh_queued:
            self._refresh_queued = True
            QTimer.singleShot(0, self.refresh)

    def refresh(self, *_):
        self._refresh_queued = False
        if self._pending is not None and 'debug' not in self.client._pending:
            # Failed HTTP requests emit changed without a debug_result signal.
            self._pending = None
        row, debug = self.procedure, self.state
        key = (row['id'] if row else None, debug.get('revision'), self.client.epoch)
        if key != self._key:
            changed = self._key is not None
            self.view_generation += 1
            self._reads.clear()
            self._pending = None
            self._selected_thread = None
            self._key, self._signature = key, None
            self._frames_signature = self._threads_signature = self._views_signature = None
            self._breakpoints_signature = None
            self._was_paused = False
            if changed:
                self.continued.emit()
        signature = json.dumps(debug, sort_keys=True)
        if signature == self._signature:
            return
        previous = self._signature
        self._signature = signature
        if self.paused:
            threads = debug.get('threads', [])
            signature = json.dumps(threads, sort_keys=True)
            if signature != self._threads_signature:
                self._threads_signature = signature
                self.threads_changed.emit(threads)
            frames = debug.get('stacks', {}).get(str(self.thread_id), debug.get('stack_frames', []))
            signature = json.dumps(frames, sort_keys=True)
            if signature != self._frames_signature:
                self._frames_signature = signature
                self.stack_changed.emit(frames)
            if not self._was_paused:
                self.stopped.emit({'reason': debug.get('reason') or 'paused', 'threadId': self.thread_id})
            signature = json.dumps([debug.get('scopes'), debug.get('variables')], sort_keys=True)
            if signature != self._views_signature:
                self._views_signature = signature
                self.views_changed.emit()
        elif previous is not None or key[0] is None:
            self.continued.emit()
        self._was_paused = self.paused
        signature = json.dumps(debug.get('breakpoints', {}), sort_keys=True)
        if signature != self._breakpoints_signature:
            self._breakpoints_signature = signature
            root = Path(self.client.snapshot.get('project', '.')).resolve()
            for path, points in debug.get('breakpoints', {}).items():
                target = (root / path).resolve()
                if target.is_relative_to(root):
                    self.breakpoints_verified.emit({'path': str(target), 'breakpoints': points})

    def select_thread(self, identifier):
        if not self.paused:
            return
        self._selected_thread = identifier
        self.view_generation += 1
        self._reads.clear()
        frames = self.state.get('stacks', {}).get(str(identifier))
        if frames is not None:
            self._frames_signature = json.dumps(frames, sort_keys=True)
            self.stack_changed.emit(frames)
        elif self.client.can_control:
            self.view_request('stackTrace', {'threadId': identifier, 'startFrame': 0, 'levels': 32},
                              lambda body: self.stack_changed.emit(body.get('stackFrames', [])))

    def view_request(self, command, arguments, callback):
        if not self.paused:
            return False
        context = (self.procedure['id'], self.state['revision'], self.client.epoch, self.view_generation)
        def cached(body):
            def deliver():
                current = (self.procedure['id'], self.state['revision'], self.client.epoch, self.view_generation) if self.procedure else None
                if self.paused and current == context:
                    callback(body)
            # Tree expansion is a Qt model notification. Replacing its children
            # inside that notification can corrupt the Windows item model.
            QTimer.singleShot(0, deliver)
        if command in {'scopes', 'variables'}:
            name = 'frameId' if command == 'scopes' else 'variablesReference'
            cache = self.state.get(command, {}).get(str(arguments[name]))
            if cache is not None:
                cached({command: cache})
                return True
        if not self.client.can_control:
            cached({command: []})
            return False
        if command in {'scopes', 'variables', 'stackTrace'}:
            if any(command == item[0] and arguments == item[1] and context == item[3]
                   for item in self._reads):
                return True
            if len(self._reads) == self._reads.maxlen:
                self.error.emit('Too many debugger views are pending')
                return False
            self._reads.append((command, arguments, callback, context))
            self.flush_reads()
            return True
        return self.request(command, arguments, callback, context)

    def flush_reads(self):
        if self._pending is not None or 'debug' in self.client._pending:
            return
        while self._reads:
            command, arguments, callback, context = self._reads.popleft()
            current = (self.procedure['id'], self.state['revision'], self.client.epoch, self.view_generation) if self.procedure else None
            if self.paused and self.client.can_control and context == current:
                self.request(command, arguments, callback, context)
                return

    def request(self, command, arguments, callback=None, context=None):
        if not self.client.can_control or not self.procedure:
            return False
        if self._pending is not None or 'debug' in self.client._pending:
            self.error.emit('Wait for the current debugger request to finish')
            return False
        context = context or (self.procedure['id'], self.state['revision'], self.client.epoch, self.view_generation)
        self._pending = (command, callback, context)
        if self.client.debug_command(context[0], command, arguments, context[1]):
            return True
        self._pending = None
        return False

    def received(self, result):
        pending, self._pending = self._pending, None
        if not pending:
            return
        command, callback, context = pending
        current = (self.procedure['id'], self.state['revision'], self.client.epoch, self.view_generation) if self.procedure else None
        if (context != current or result['procedure'] != context[0] or result.get('epoch') != context[2]
                or result['revision'] != context[1] or result['command'] != command):
            return
        if result.get('debug'):
            self.procedure['debug'] = result['debug']
        if callback and self.paused and command not in {'evaluate', 'setVariable', 'setExpression'}:
            callback(result['body'])
        self.refresh()
        if callback and self.paused and command in {'evaluate', 'setVariable', 'setExpression'}:
            callback(result['body'])

    def control(self, command):
        row = self.procedure
        if not row or not self.client.can_control:
            return False
        if command != 'pause' and (not self.paused or row['status'] != 'PAUSED'):
            return False
        self._reads.clear()
        return self.request(command, {'threadId': self.thread_id} if self.thread_id is not None else {})

    def set_breakpoints(self, path, lines):
        if not self.procedure or not self.client.can_control:
            return False
        root = Path(self.client.snapshot['project']).resolve()
        path = Path(path).resolve()
        if not path.is_relative_to(root):
            return False
        return self.request('setBreakpoints', {'source': {'path': path.relative_to(root).as_posix()},
            'breakpoints': [{'line': line} for line in sorted(lines)]})
