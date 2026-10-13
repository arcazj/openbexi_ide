"""Asynchronous desktop client for the existing fenced session protocol."""
from __future__ import annotations

from collections import deque
import json
from pathlib import Path
import queue
import threading
import time

from PySide6.QtCore import QObject, QTimer, Qt, Signal, Slot

from openbexi_runtime.cli import request


class SessionClient(QObject):
    changed = Signal()
    snapshot_changed = Signal(object)
    output = Signal(object)
    error = Signal(str)
    submitted = Signal(str)
    debug_result = Signal(object)
    source_result = Signal(object)
    _completed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = 'local'
        self.url = ''
        self.identity = {}
        self.snapshot = {}
        self.epoch = None
        self.healthy = False
        self.keep_control = True
        self.outputs = deque(maxlen=2048)
        self._generation = 0
        self._cursor = 0
        self._pending = set()
        self._last_renew = 0
        self._lease_seconds = 30
        self._requested_role = 'developer'
        self._tls = None
        self._unavailability_reported = False
        self._jobs = queue.Queue(maxsize=16)
        self._thread = None
        self._completed.connect(self._receive, Qt.QueuedConnection)
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self._tick)

    @property
    def active(self):
        return self.state != 'local'

    @property
    def command_pending(self):
        return bool(self._pending - {'snapshot', 'renew', 'source'})

    @property
    def owns_control(self):
        owner = self.snapshot.get('controller') or {}
        return (self.state == 'joined' and self.healthy and self.identity.get('role') == 'developer'
                and self.epoch is not None and self.epoch == self.snapshot.get('epoch')
                and owner.get('id') == self.identity.get('client'))

    @property
    def can_control(self):
        return self.owns_control and not self.command_pending

    @property
    def can_claim(self):
        owner = self.snapshot.get('controller') or {}
        return (self.state == 'joined' and self.healthy and not self.command_pending
                and self.identity.get('role') == 'developer'
                and owner.get('id') in {None, self.identity.get('client')})

    def join(self, *, user, url=None, invite=None, invite_file=None, role='developer'):
        if self.active:
            self.error.emit('Disconnect from the current session first')
            return False
        try:
            if role not in {'developer', 'monitor'}:
                raise ValueError('Choose Developer or Monitor')
            info = {}
            if invite_file:
                path = Path(invite_file)
                if path.stat().st_size > 65536:
                    raise ValueError('Invitation file exceeds its bound')
                info = json.loads(path.read_text(encoding='utf-8-sig'))
            url = url or info.get('url')
            invite = invite or info.get(role + '_invite')
            tls = info.get('tls')
            if tls is not None:
                if type(tls) is not dict or set(tls) - {'ca', 'certificate', 'key'}:
                    raise ValueError('Invalid session TLS configuration')
                tls = {key: str((path.parent / value).resolve()) if value else None for key, value in tls.items()}
            if not url or not (invite or tls):
                raise ValueError('Supply a session URL and invitation or invitation file')
            if role == 'monitor' and invite and invite == info.get('developer_invite'):
                raise ValueError('A monitor needs the monitor invitation')
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.error.emit(str(exc))
            return False
        self._generation += 1
        self.state, self.url = 'joining', url
        self._tls = tls
        self.identity, self.snapshot, self.epoch = {}, {}, None
        self.healthy = False
        self._unavailability_reported = False
        self._cursor = 0
        self.outputs.clear()
        self._pending.clear()
        self._requested_role = role
        self._jobs = queue.Queue(maxsize=16)
        self._thread = threading.Thread(target=self._work, args=(self._jobs,), name='desktop-session-http', daemon=True)
        self._thread.start()
        self._enqueue('connect', '/connect', {'name': user, 'invite': invite}, token=None)
        self.changed.emit()
        return True

    def _enqueue(self, kind, path, body=None, *, token=None):
        if kind in self._pending:
            return False
        job = {'generation': self._generation, 'kind': kind, 'url': self.url,
               'tls': self._tls,
               'path': path, 'body': body, 'token': self.identity.get('token') if token is None and kind != 'connect' else token}
        if kind != 'renew':
            try:
                self._jobs.put_nowait(job)
            except queue.Full:
                self.error.emit('A session request is still pending; wait before trying again')
                return False
        self._pending.add(kind)
        if kind == 'renew':
            # A slow inspection/evaluation must not block lease maintenance.
            # At most one renewal is outstanding, still bound to this generation.
            threading.Thread(target=self._renew, args=(job,), name='desktop-session-lease', daemon=True).start()
        self.changed.emit()
        return True

    def _renew(self, job):
        result = {'job': job}
        try:
            result['value'] = request(job['url'], job['path'], job['body'], job['token'], tls=job.get('tls'))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            result['error'] = str(exc)
            result['http_status'] = getattr(exc.__cause__, 'code', None)
        try:
            self._completed.emit(result)
        except RuntimeError:
            pass

    def _work(self, jobs):
        while True:
            job = jobs.get()
            if job['generation'] != self._generation:
                if job['kind'] == 'disconnect':
                    return
                continue
            result = {'job': job}
            try:
                result['value'] = ({'disconnected': True} if job['kind'] == 'disconnect' and not job['token']
                                   else request(job['url'], job['path'], job['body'], job['token'], tls=job.get('tls')))
                if job['kind'] == 'connect' and job['generation'] != self._generation:
                    # A join cancelled while its HTTP response was in flight
                    # still owns a newly issued credential: revoke it explicitly.
                    request(job['url'], '/disconnect', {}, result['value']['token'], tls=job.get('tls'))
            except (ValueError, OSError, KeyError, TypeError) as exc:
                result['error'] = str(exc)
                result['http_status'] = getattr(exc.__cause__, 'code', None)
            try:
                self._completed.emit(result)
            except RuntimeError:
                return
            if job['kind'] == 'disconnect':
                return

    @Slot(object)
    def _receive(self, result):
        job = result['job']
        if job['generation'] != self._generation:
            return
        kind = job['kind']
        self._pending.discard(kind)
        if kind == 'disconnect':
            if result.get('error'):
                self.error.emit('Disconnect could not reach the service; its controller lease will expire')
            self.state, self.identity, self.snapshot = 'local', {}, {}
            self.epoch, self.healthy = None, False
            self.changed.emit()
            return
        if result.get('error'):
            if kind == 'connect':
                self.state = 'local'
                self._generation += 1
                # The worker has finished the failed connect; stop its loop.
                self._jobs.put_nowait({'generation': self._generation, 'kind': 'disconnect',
                                      'url': self.url, 'path': '/disconnect', 'body': {}, 'token': None})
            elif (result.get('http_status') in {None, 401}
                  or (result.get('http_status') or 0) >= 500 or 'controller token' in result['error']):
                self.healthy, self.epoch = False, None
            if kind != 'snapshot' or self.healthy:
                self.error.emit(result['error'])
            elif self.state == 'joined' and not self._unavailability_reported:
                self.error.emit('Session unavailable; execution controls are disabled')
                self._unavailability_reported = True
            self.changed.emit()
            return
        value = result['value']
        if kind == 'connect':
            self.identity = value
            if value.get('role') != self._requested_role:
                self.error.emit('Invitation role does not match the selected connection role')
                self.disconnect()
                return
            self.state = 'joined'
            self.timer.start()
            self._tick()
        elif kind == 'snapshot':
            if value.get('session') != self.identity.get('session'):
                self.healthy, self.epoch = False, None
                self.error.emit('The service session changed; disconnect and join the new session')
            else:
                self.healthy = value.get('storage_healthy', True)
                self._unavailability_reported = False
                owner = value.get('controller') or {}
                if owner.get('id') != self.identity.get('client') or value.get('epoch') != self.epoch:
                    self.epoch = None
                self.snapshot = value
                if value.get('replay_gap'):
                    self.error.emit('Earlier session output is no longer retained')
                for event in value.get('events', []):
                    if event.get('type') == 'output' and event.get('text'):
                        self.outputs.append(event)
                        self.output.emit(event)
                self._cursor = value['cursor']
                self.snapshot_changed.emit(value)
        elif kind in {'claim', 'renew'}:
            self.epoch = value['epoch']
            self._lease_seconds = value['lease_seconds']
            self._last_renew = time.monotonic()
        elif kind == 'release':
            self.epoch = None
        elif kind == 'run':
            self.submitted.emit(value['id'])
        elif kind == 'debug':
            sent = job['body']
            if self.epoch == sent['epoch']:
                self.debug_result.emit({'procedure': sent['procedure'], 'command': sent['command'],
                    'arguments': sent['arguments'], 'revision': sent['revision'],
                    'epoch': sent['epoch'], 'body': value.get('body', {}), 'debug': value.get('debug')})
        elif kind == 'source':
            self.source_result.emit(value)
        self.changed.emit()

    def _tick(self):
        if self.state != 'joined':
            return
        if self.keep_control and self.owns_control and time.monotonic() - self._last_renew >= self._lease_seconds / 3:
            self._enqueue('renew', '/renew', {'epoch': self.epoch})
        self._enqueue('snapshot', '/session?after=' + str(self._cursor))

    def command(self, kind, **fields):
        if not (self.can_claim if kind == 'claim' else self.can_control):
            self.error.emit('Claim the controller token before executing session commands')
            return False
        return self._enqueue(kind, '/' + kind, {'epoch': self.epoch, **fields})

    def submit(self, script, *, language='python', arguments=(), debug=False,
               stop_on_entry=True, breakpoints=None):
        return self.command('run', script=script, language=language, arguments=list(arguments),
                            debug=debug, stop_on_entry=stop_on_entry, breakpoints=breakpoints or {})

    def debug_command(self, procedure, command, arguments=None, revision=None):
        row = next((p for p in self.snapshot.get('procedures', []) if p['id'] == procedure), None)
        if not row or not row.get('debug'):
            self.error.emit('Select a procedure with an active shared debugger')
            return False
        if revision is None:
            revision = row['debug']['revision']
        return self.command('debug', procedure=procedure, command=command,
                            arguments=arguments or {}, revision=revision)

    def fetch_source(self, procedure, path):
        if self.state != 'joined' or not self.healthy:
            return False
        return self._enqueue('source', '/source', {'procedure': procedure, 'path': path})

    def disconnect(self):
        if not self.active or self.state == 'leaving':
            return
        self.timer.stop()
        self._generation += 1
        self._pending.clear()
        self.state, self.healthy = 'leaving', False
        self._enqueue('disconnect', '/disconnect', {})
        self.changed.emit()
