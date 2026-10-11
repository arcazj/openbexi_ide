"""Local Development sessions: fenced controller leases and execution slots."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import codecs
import hashlib
import os
from pathlib import Path
import secrets
import queue
import subprocess
import sys
import threading
import time
import uuid

from .launch import LaunchSpec, clean_environment, interpreter_info
from .processes import ProcessTree

TERMINAL = frozenset({'COMPLETED', 'FAILED', 'CANCELLED'})


class SessionError(ValueError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


@dataclass
class Procedure:
    id: str
    script: str
    spec: LaunchSpec
    language: str
    source_hash: str
    status: str = 'PAUSED'
    reason: str | None = 'WAITING_TOKEN'
    wants_run: bool = True
    has_token: bool = False
    secret: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    process: subprocess.Popen | None = None
    owner: ProcessTree | None = None
    stacks: dict = field(default_factory=dict)
    exit_code: int | None = None
    error: str | None = None
    cancelled: bool = False
    worker_pid: int | None = None
    bootstrap_pids: set | None = None
    input_queue: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=8))
    input_closed: bool = False
    thread: threading.Thread | None = None

    def public(self):
        return {'id': self.id, 'script': self.script, 'language': self.language,
                'source_sha256': self.source_hash, 'status': self.status,
                'pause_reason': self.reason, 'has_token': self.has_token,
                'pid': None if self.process is None else self.process.pid,
                'worker_pid': self.worker_pid,
                'input_closed': self.input_closed,
                'exit_code': self.exit_code, 'error': self.error,
                'threads': list(self.stacks.values())}


class Session:
    def __init__(self, project: Path, *, max_parallel=1, lease_seconds=30,
                 interpreter=Path(sys.executable), dss_url=None):
        self.project = Path(project).resolve()
        if not self.project.is_dir():
            raise ValueError('Session project must exist')
        if type(max_parallel) is not int or not 1 <= max_parallel <= 16:
            raise ValueError('max_parallel must be in 1..16')
        if type(lease_seconds) not in {int, float} or not 0.5 <= lease_seconds <= 300:
            raise ValueError('lease_seconds must be in 0.5..300')
        interpreter_info(interpreter)
        self.interpreter, self.max_parallel = Path(interpreter), max_parallel
        self.lease_seconds, self.dss_url = lease_seconds, dss_url
        self.id = uuid.uuid4().hex
        self.developer_invite, self.monitor_invite = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.clients, self.procedures = {}, {}
        self.controller, self.epoch, self.deadline = None, 0, 0.0
        self.lock, self.closed = threading.RLock(), threading.Event()
        self.events, self.sequence = deque(maxlen=2048), 0
        self.worker_url = None
        self.housekeeper = threading.Thread(target=self._housekeep, name='session-lease', daemon=True)
        self.housekeeper.start()

    def event(self, kind, **data):
        with self.lock:
            self.sequence += 1
            self.events.append({'sequence': self.sequence, 'type': kind,
                                'time': time.time(), **data})

    def join(self, name, invite):
        if not isinstance(name, str) or not 1 <= len(name) <= 64 or not name.strip() or any(ord(c) < 32 for c in name):
            raise SessionError('Developer name must be 1..64 printable characters', 400)
        if not isinstance(invite, str):
            raise SessionError('Invitation required', 403)
        if secrets.compare_digest(invite, self.developer_invite):
            role = 'developer'
        elif secrets.compare_digest(invite, self.monitor_invite):
            role = 'monitor'
        else:
            raise SessionError('Invalid invitation', 403)
        client_id, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
        with self.lock:
            if len(self.clients) >= 64:
                raise SessionError('Session connection limit reached')
            self.clients[token] = {'id': client_id, 'name': name, 'role': role}
            self.event('connected', client=client_id, name=name, role=role)
        return {'session': self.id, 'client': client_id, 'token': token, 'role': role}

    def authenticate(self, token):
        with self.lock:
            if not isinstance(token, str) or token not in self.clients:
                raise SessionError('Connection credential required', 401)
            return self.clients[token]

    def leave(self, client):
        """Revoke this member's credential and pause any control it owns."""
        with self.lock:
            if self.controller == client['id']:
                self._lose_controller('CONTROLLER_DISCONNECTED')
            self.clients = {token: member for token, member in self.clients.items()
                            if member['id'] != client['id']}
            self.event('disconnected', client=client['id'])
            return {'disconnected': True}

    def _developer(self, client):
        if not any(member is client for member in self.clients.values()):
            raise SessionError('Connection credential revoked', 401)
        if client['role'] != 'developer':
            raise SessionError('Monitoring connections are read-only', 403)

    def _expire(self):
        if self.controller is not None and time.monotonic() >= self.deadline:
            self._lose_controller('CONTROLLER_EXPIRED')

    def _lose_controller(self, reason):
        former = self.controller
        self.controller = None
        self.epoch += 1
        for procedure in self.procedures.values():
            if procedure.status not in TERMINAL:
                self._pause(procedure, reason)
        self.event('controller_released', client=former, reason=reason, epoch=self.epoch)

    def claim(self, client):
        with self.lock:
            self._developer(client)
            self._expire()
            if self.controller not in {None, client['id']}:
                raise SessionError('Another developer holds the controller token')
            if self.controller is None:
                self.controller = client['id']
                self.epoch += 1
                self.event('controller_claimed', client=client['id'], epoch=self.epoch)
            self.deadline = time.monotonic() + self.lease_seconds
            return {'epoch': self.epoch, 'lease_seconds': self.lease_seconds}

    def _control(self, client, epoch):
        self._developer(client)
        self._expire()
        if type(epoch) is not int or self.controller != client['id'] or self.epoch != epoch:
            raise SessionError('Stale or missing controller token')
        self.deadline = time.monotonic() + self.lease_seconds

    def renew(self, client, epoch):
        with self.lock:
            self._control(client, epoch)
            return {'epoch': self.epoch, 'lease_seconds': self.lease_seconds}

    def release(self, client, epoch):
        with self.lock:
            self._control(client, epoch)
            self._lose_controller('CONTROLLER_RELEASED')
            return {'epoch': self.epoch}

    def configure(self, client, epoch, max_parallel):
        with self.lock:
            self._control(client, epoch)
            if type(max_parallel) is not int or not 1 <= max_parallel <= 16:
                raise SessionError('max_parallel must be in 1..16', 400)
            occupied = sum(procedure.has_token for procedure in self.procedures.values())
            if max_parallel < occupied:
                raise SessionError('Pause or finish procedures before reducing the occupied slot count')
            self.max_parallel = max_parallel
            self.event('configuration_changed', max_parallel=max_parallel)
            self._dispatch()
            return {'max_parallel': max_parallel}

    def submit(self, client, epoch, script, *, arguments=(), language='python'):
        with self.lock:
            self._control(client, epoch)
            if self.closed.is_set() or not self.worker_url:
                raise SessionError('Session is not accepting procedures')
            if language not in {'python', 'spell'}:
                raise SessionError('Language must be python or spell', 400)
            if not isinstance(script, str) or not isinstance(arguments, (list, tuple)) or len(arguments) > 128:
                raise SessionError('Invalid procedure arguments', 400)
            target = self.project / script
            spec = LaunchSpec(self.project, target, self.interpreter, tuple(arguments)).validate()
            logical = spec.script.relative_to(self.project).as_posix()
            if any(p.script == logical and p.status not in TERMINAL for p in self.procedures.values()):
                raise SessionError('This logical procedure is already active in the session')
            if sum(p.status not in TERMINAL for p in self.procedures.values()) >= 128:
                raise SessionError('Procedure queue limit reached')
            if len(self.procedures) >= 512:
                for identifier in [p.id for p in self.procedures.values() if p.status in TERMINAL][:256]:
                    del self.procedures[identifier]
            if language == 'spell':
                from .languages import check_spell
                check_spell(self.interpreter)
            procedure = Procedure(uuid.uuid4().hex, logical, spec, language,
                                  hashlib.sha256(spec.script.read_bytes()).hexdigest())
            self.procedures[procedure.id] = procedure
            self.event('queued', procedure=procedure.id, script=logical)
            self._dispatch()
            return procedure.public()

    def _dispatch(self):
        if self.closed.is_set() or self.controller is None:
            return
        slots = self.max_parallel - sum(p.has_token for p in self.procedures.values())
        for procedure in self.procedures.values():
            if slots <= 0:
                break
            if procedure.status == 'PAUSED' and procedure.wants_run and not procedure.has_token:
                procedure.has_token, procedure.reason = True, None
                procedure.status = 'RUNNING' if procedure.process else 'STARTING'
                self.event('token_granted', procedure=procedure.id)
                slots -= 1
                if procedure.process is None:
                    procedure.thread = threading.Thread(target=self._execute, args=(procedure,), daemon=True)
                    procedure.thread.start()

    def _execute(self, procedure):
        pumps = []
        try:
            with self.lock:
                if not procedure.has_token or self.closed.is_set():
                    return
                spec = procedure.spec
                environment = clean_environment()
                environment['OPENBEXI_SESSION_WORKER'] = __import__('json').dumps({
                    'url': self.worker_url, 'id': procedure.id, 'token': procedure.secret,
                    'language': procedure.language, 'source_hash': procedure.source_hash,
                    'dss_url': self.dss_url})
                command = [str(spec.interpreter), '-I', '-B', '-u', '-X', 'utf8',
                           str(Path(__file__).with_name('session_worker.py')),
                           str(spec.project), str(spec.script), *spec.arguments]
                process = subprocess.Popen(command, cwd=spec.project, env=environment,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    start_new_session=os.name != 'nt',
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                procedure.process = process
                try:
                    procedure.owner = ProcessTree(process.pid)
                except BaseException:
                    process.kill()
                    raise
                self.event('started', procedure=procedure.id, pid=process.pid)
            writer = threading.Thread(target=self._input_pump, args=(procedure,), daemon=True)
            writer.start()
            for stream, name in ((process.stdout, 'stdout'), (process.stderr, 'stderr')):
                pump = threading.Thread(target=self._pump, args=(procedure.id, stream, name), daemon=True)
                pumps.append(pump)
                pump.start()
            code = process.wait()
            procedure.owner.close()
            try:
                procedure.input_queue.put_nowait(None)
            except queue.Full:
                pass
            writer.join(timeout=2)
            for pump in pumps:
                pump.join(timeout=3)
            with self.lock:
                procedure.exit_code = code
                procedure.status = 'CANCELLED' if procedure.cancelled else 'COMPLETED' if code == 0 else 'FAILED'
        except BaseException as error:
            with self.lock:
                procedure.error, procedure.status = str(error), 'FAILED'
        finally:
            if procedure.owner:
                procedure.owner.close()
            if procedure.process:
                if procedure.process.poll() is None:
                    procedure.process.kill()
                procedure.process.wait(timeout=5)
                for stream in (procedure.process.stdin, procedure.process.stdout, procedure.process.stderr):
                    if stream:
                        try:
                            stream.close()
                        except OSError:
                            # Closing buffered stdin may flush into a pipe whose
                            # worker has already been stopped. The process/tree
                            # is gone; still close the underlying parent handle.
                            if not stream.closed:
                                stream.raw.close()
            with self.lock:
                # A grant cancelled before process creation stays resumable.
                if procedure.process is not None or procedure.status == 'FAILED':
                    procedure.has_token, procedure.wants_run = False, False
                    self.event('finished', procedure=procedure.id, status=procedure.status, exit_code=procedure.exit_code)
                self._expire()
                self._dispatch()

    def _pump(self, identifier, stream, name):
        decoder = codecs.getincrementaldecoder('utf-8')('replace')
        while raw := stream.read1(4096):
            self.event('output', procedure=identifier, stream=name, text=decoder.decode(raw))
        final = decoder.decode(b'', final=True)
        if final:
            self.event('output', procedure=identifier, stream=name, text=final)

    def _input_pump(self, procedure):
        try:
            while True:
                chunk = procedure.input_queue.get()
                if chunk is None:
                    procedure.process.stdin.close()
                    return
                procedure.process.stdin.write(chunk)
                procedure.process.stdin.flush()
        except (OSError, ValueError):
            self.event('input_closed', procedure=procedure.id)

    def _pause(self, procedure, reason='USER_PAUSED'):
        procedure.wants_run, procedure.reason = False, reason
        if procedure.status in TERMINAL or procedure.status == 'STOPPING':
            return
        if procedure.process is None:
            procedure.has_token, procedure.status = False, 'PAUSED'
        elif procedure.has_token:
            procedure.status = 'PAUSING'
        self.event('pause_requested', procedure=procedure.id, reason=reason)

    def change(self, client, epoch, action, identifier):
        with self.lock:
            self._control(client, epoch)
            selected = list(self.procedures.values()) if identifier == 'all' else [self.procedures.get(identifier)]
            if any(p is None for p in selected):
                raise SessionError('Procedure does not exist', 404)
            if action not in {'pause', 'resume', 'stop'}:
                raise SessionError('Unknown procedure action', 400)
            if action == 'resume' and any(p.status not in TERMINAL and p.status != 'PAUSED' for p in selected):
                raise SessionError('Wait for every selected procedure to confirm PAUSED before resuming')
            for procedure in selected:
                if procedure.status in TERMINAL:
                    continue
                if action == 'pause':
                    self._pause(procedure)
                elif action == 'resume':
                    procedure.wants_run, procedure.reason = True, 'WAITING_TOKEN'
                else:
                    procedure.cancelled, procedure.wants_run = True, False
                    if procedure.process:
                        procedure.status = 'STOPPING'
                        if procedure.owner:
                            procedure.owner.close()
                    else:
                        procedure.status, procedure.has_token = 'CANCELLED', False
                    self.event('stop_requested', procedure=procedure.id)
            self._dispatch()
            return [p.public() for p in selected]

    def input(self, client, epoch, identifier, text):
        with self.lock:
            self._control(client, epoch)
            procedure = self.procedures.get(identifier)
            if not procedure or procedure.status not in {'RUNNING', 'PAUSING'} or not procedure.process:
                raise SessionError('Input requires a running or pausing procedure')
            if text is not None and (not isinstance(text, str) or len(text.encode('utf-8')) > 8192):
                raise SessionError('Input exceeds its bound', 400)
            if procedure.input_closed:
                raise SessionError('Procedure input is closed')
            try:
                procedure.input_queue.put_nowait(None if text is None else (text + '\n').encode('utf-8'))
            except queue.Full as error:
                raise SessionError('Procedure input queue is full; wait before sending more') from error
            if text is None:
                procedure.input_closed = True
            return {'accepted': True}

    def checkpoint(self, body):
        with self.lock:
            procedure = self.procedures.get(body.get('id'))
            token = body.get('token')
            if not procedure or not isinstance(token, str) or not secrets.compare_digest(token, procedure.secret):
                raise SessionError('Worker credential rejected', 403)
            self._expire()
            worker_pid = body.get('pid')
            if type(worker_pid) is not int or worker_pid <= 0 or procedure.worker_pid not in {None, worker_pid}:
                raise SessionError('Worker process identity differs', 400)
            procedure.worker_pid = worker_pid
            if body.get('bootstrap') is True and procedure.bootstrap_pids is None:
                procedure.bootstrap_pids = procedure.owner.process_ids() if procedure.owner else None
                if procedure.bootstrap_pids is not None and worker_pid not in procedure.bootstrap_pids:
                    raise SessionError('Worker is outside its owned process tree', 403)
            thread = body.get('thread')
            active = body.get('active_threads')
            if type(active) is not list or len(active) > 128 or any(not isinstance(i, str) for i in active):
                raise SessionError('Invalid active thread inventory', 400)
            procedure.stacks = {identifier: value for identifier, value in procedure.stacks.items() if identifier in active}
            if type(thread) is not dict or not isinstance(thread.get('id'), str) or type(thread.get('stack')) is not list:
                raise SessionError('Invalid stack snapshot', 400)
            if len(thread['stack']) > 32 or len(procedure.stacks) >= 128 and thread['id'] not in procedure.stacks:
                raise SessionError('Stack snapshot exceeds bounds', 400)
            procedure.stacks[thread['id']] = thread
            if procedure.cancelled or self.closed.is_set():
                return {'action': 'stop'}
            if procedure.status == 'STARTING' and procedure.has_token and self.controller is not None:
                procedure.status = 'RUNNING'
            if procedure.status == 'PAUSING' and body.get('quiescent') is True:
                # Native calls and owned child processes retain their slot until
                # actual quiescence. No replacement receives an optimistic token.
                # Startup wrappers are captured before user code is admitted.
                # Compare identities, not counts: a later child must never be
                # mistaken for a wrapper that already exited.
                live = procedure.owner.process_ids() if procedure.owner else None
                if live is not None and procedure.bootstrap_pids is not None and live.issubset(procedure.bootstrap_pids):
                    procedure.status, procedure.has_token = 'PAUSED', False
                    self.event('paused', procedure=procedure.id, reason=procedure.reason)
                    self._dispatch()
            return {'action': 'run' if procedure.status == 'RUNNING' and procedure.has_token and self.controller else 'pause'}

    def snapshot(self, after=0):
        with self.lock:
            self._expire()
            if type(after) is not int or after < 0:
                raise SessionError('Invalid event cursor', 400)
            controller = next((c for c in self.clients.values() if c['id'] == self.controller), None)
            return {'session': self.id, 'mode': 'Development', 'project': str(self.project),
                    'max_parallel': self.max_parallel, 'controller': controller,
                    'epoch': self.epoch, 'lease_remaining': max(0, self.deadline-time.monotonic()) if controller else 0,
                    'clients': list(self.clients.values()), 'procedures': [p.public() for p in self.procedures.values()],
                    'cursor': self.sequence, 'events': [e for e in self.events if e['sequence'] > after],
                    'replay_gap': bool(self.events and after and after < self.events[0]['sequence']-1)}

    def _housekeep(self):
        while not self.closed.wait(0.05):
            with self.lock:
                self._expire()

    def close(self):
        self.closed.set()
        with self.lock:
            for procedure in self.procedures.values():
                procedure.cancelled = True
                if procedure.owner:
                    procedure.owner.close()
            threads = [p.thread for p in self.procedures.values() if p.thread]
        for thread in threads:
            thread.join(timeout=6)
        self.housekeeper.join(timeout=2)
