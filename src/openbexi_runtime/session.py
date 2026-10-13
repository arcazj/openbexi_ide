"""Local Development sessions: fenced controller leases and execution slots."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import codecs
import copy
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

from .launch import LaunchSpec, clean_environment, console_interpreter, interpreter_info
from .processes import ProcessTree, start_owned_process

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
    definition: str | None = None
    version: str | None = None
    capture_digest: str | None = None
    release: str | None = None
    backend: dict | None = None
    channel: object | None = None
    fence: int = 0
    uncertain: bool = False
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
    debug: dict | None = None
    debugger: object | None = None
    debug_initial_breakpoints: dict = field(default_factory=dict)
    debug_pending: tuple | None = None
    stop_on_entry: bool = True

    def public(self):
        return {'id': self.id, 'script': self.script, 'language': self.language,
                'source_sha256': self.source_hash, 'status': self.status,
                'definition_id': self.definition, 'version_id': self.version,
                'capture_sha256': self.capture_digest, 'procedure_fence': self.fence,
                'release_id': self.release,
                'backend': self.backend,
                'uncertain_effects': self.uncertain,
                'pause_reason': self.reason, 'has_token': self.has_token,
                'pid': None if self.process is None else self.process.pid,
                'worker_pid': self.worker_pid,
                'input_closed': self.input_closed,
                'exit_code': self.exit_code, 'error': self.error,
                'debug': copy.deepcopy(self.debug),
                'threads': list(self.stacks.values())}


class Session:
    def __init__(self, project: Path, *, max_parallel=1, lease_seconds=30,
                 interpreter=Path(sys.executable), dss_url=None, state_directory=None,
                 execution_release=None):
        self.project = Path(project).resolve()
        if not self.project.is_dir():
            raise ValueError('Session project must exist')
        if type(max_parallel) is not int or not 1 <= max_parallel <= 16:
            raise ValueError('max_parallel must be in 1..16')
        if type(lease_seconds) not in {int, float} or not 0.5 <= lease_seconds <= 300:
            raise ValueError('lease_seconds must be in 0.5..300')
        self.interpreter_report = interpreter_info(interpreter)
        self.interpreter, self.max_parallel = console_interpreter(interpreter), max_parallel
        self.lease_seconds, self.dss_url = lease_seconds, dss_url
        self.id = uuid.uuid4().hex
        self.developer_invite, self.monitor_invite = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.clients, self.procedures = {}, {}
        self.controller, self.epoch, self.deadline = None, 0, 0.0
        self.lock, self.closed = threading.RLock(), threading.Event()
        self.events, self.sequence = deque(maxlen=2048), 0
        self.store, self.aliases, self.fences = None, {}, {}
        self.storage_failed = False
        self.worker_url = None
        self.execution_release = execution_release
        self.authority = self.release_manifest = None
        if execution_release and not state_directory:
            raise ValueError('Execution requires a durable release authority')
        if state_directory is not None:
            from .session_store import SessionStore
            self.store = SessionStore(state_directory)
            try:
                if execution_release:
                    from .execution_release import ReleaseAuthority, image_info
                    self.authority = ReleaseAuthority(self.store)
                    self.release_manifest = self.authority.require(execution_release)
                    image_info(self.release_manifest['image'])
                self._restore()
                self.event('service_started', epoch=self.epoch, recovered=bool(self.procedures))
            except BaseException:
                self.store.close()
                raise
        self.housekeeper = threading.Thread(target=self._housekeep, name='session-lease', daemon=True)
        self.housekeeper.start()

    def event(self, kind, **data):
        with self.lock:
            if self.storage_failed:
                # Only cleanup can reach here after the authority fails closed.
                # Preserve the last committed recovery state and its cursor.
                return
            event = {'sequence': self.sequence + 1, 'type': kind, 'time': time.time(), **data}
            if self.store:
                try:
                    oldest = self.store.save(self._durable_state(event['sequence']), event)
                except Exception as error:
                    # Persistence is a launch/control precondition. A failed
                    # commit cannot be followed by further grants or worker run.
                    self.storage_failed = True
                    self.closed.set()
                    self.controller = None
                    self.epoch += 1
                    for procedure in self.procedures.values():
                        procedure.wants_run = False
                        if procedure.status not in TERMINAL and (procedure.process or procedure.has_token):
                            procedure.uncertain = True
                            procedure.status, procedure.reason = 'RECOVERY_REQUIRED', 'PERSISTENCE_FAILURE'
                        if procedure.owner:
                            procedure.owner.close()
                    raise SessionError('Durable persistence unavailable; service fenced', 503) from error
                while self.events and self.events[0]['sequence'] < oldest:
                    self.events.popleft()
            self.sequence = event['sequence']
            self.events.append(event)

    def _durable_state(self, sequence):
        return {'schema': 1, 'id': self.id, 'project': str(self.project),
                'mode': 'Execution' if self.execution_release else 'Development',
                'interpreter': str(self.interpreter), 'max_parallel': self.max_parallel,
                'sequence': sequence, 'epoch': self.epoch, 'aliases': self.aliases, 'fences': self.fences,
                'procedures': [{**{k: v for k, v in p.public().items() if k != 'threads'}, 'capture': str(p.spec.project),
                                'arguments': list(p.spec.arguments),
                                'debug_options': {'stop_on_entry': p.stop_on_entry,
                                                  'breakpoints': p.debug_initial_breakpoints} if p.debug else None,
                                'launched': p.process is not None or p.owner is not None or p.status in {'STARTING', 'RECOVERY_REQUIRED'}}
                               for p in self.procedures.values()]}

    def _restore(self):
        state, events = self.store.load()
        if state is None:
            return
        if (state['schema'] != 1 or state['project'] != str(self.project)
                or state['interpreter'] != str(self.interpreter)
                or state.get('mode', 'Development') != ('Execution' if self.execution_release else 'Development')):
            raise ValueError('Durable service project or interpreter identity differs')
        self.id, self.sequence, self.epoch = state['id'], state['sequence'], state['epoch'] + 1
        self.max_parallel, self.aliases, self.fences = state['max_parallel'], state['aliases'], state['fences']
        self.events.extend(events)
        for row in state['procedures']:
            root = Path(row['capture'])
            p = Procedure(row['id'], row['script'], LaunchSpec(root, root / row['script'], self.interpreter,
                          tuple(row['arguments'])), row['language'], row['source_sha256'],
                          definition=row['definition_id'], version=row['version_id'],
                          capture_digest=row['capture_sha256'], fence=row['procedure_fence'],
                          release=row.get('release_id'), backend=row.get('backend'))
            p.status, p.exit_code, p.error = row['status'], row['exit_code'], row['error']
            p.debug = row.get('debug')
            if p.debug:
                options = row.get('debug_options') or {}
                p.stop_on_entry = options.get('stop_on_entry', True)
                p.debug_initial_breakpoints = options.get('breakpoints', {})
                p.debug.update(state='terminated' if p.status in TERMINAL else 'unavailable' if row['launched'] else 'queued',
                               revision=p.debug.get('revision', 0) + 1,
                               stack_frames=[], stacks={}, scopes={}, variables={}, threads=[])
            p.wants_run = False
            p.uncertain = row.get('uncertain_effects', False)
            if p.status not in TERMINAL:
                if row['launched']:
                    if p.backend is not None:
                        from .shared_backends import load_backend
                        load_backend(p.language).recover(self.id, p.id, p.backend)
                    elif p.release:
                        from .execution_container import recover_container
                        recover_container(self.id, p.id)
                    p.status, p.reason, p.has_token, p.uncertain = 'RECOVERY_REQUIRED', 'UNCONFIRMED_SHUTDOWN', True, True
                else:
                    p.status, p.reason = 'PAUSED', 'SERVICE_RESTARTED'
            self.procedures[p.id] = p

    def revoke_subject(self, subject):
        with self.lock:
            self.event('identity_revoked', subject=subject)
            for client in list(self.clients.values()):
                if client.get('subject') == subject:
                    self.leave(client)

    def join(self, name, invite, *, principal=None):
        if not isinstance(name, str) or not 1 <= len(name) <= 64 or not name.strip() or any(ord(c) < 32 for c in name):
            raise SessionError('Developer name must be 1..64 printable characters', 400)
        if principal is not None:
            name, role = principal['name'], principal['role']
        elif not isinstance(invite, str):
            raise SessionError('Invitation required', 403)
        elif secrets.compare_digest(invite, self.developer_invite):
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
            if principal is not None:
                self.clients[token]['subject'] = principal['subject']
            self.event('connected', client=client_id, name=name, role=role,
                       subject=principal['subject'] if principal else None)
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
        if self.closed.is_set():
            raise SessionError('Session is not accepting commands', 503)
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

    def handoff(self, client, epoch, target):
        with self.lock:
            self._control(client, epoch)
            member = next((c for c in self.clients.values() if c['id'] == target), None)
            if member is None or member['role'] != 'developer' or target == client['id']:
                raise SessionError('Handoff requires another connected developer', 400)
            self._lose_controller('CONTROLLER_HANDOFF')
            self.controller = target
            self.deadline = time.monotonic() + self.lease_seconds
            # The recipient must explicitly claim the new fence and resume.
            self.event('controller_handoff', client=client['id'], target=target, epoch=self.epoch)
            return {'epoch': self.epoch, 'target': target, 'requires_claim': True}

    def configure(self, client, epoch, max_parallel):
        with self.lock:
            self._control(client, epoch)
            if type(max_parallel) is not int or not 1 <= max_parallel <= 16:
                raise SessionError('max_parallel must be in 1..16', 400)
            occupied = sum(procedure.has_token for procedure in self.procedures.values())
            if max_parallel < occupied:
                raise SessionError('Pause or finish procedures before reducing the occupied slot count')
            self.max_parallel = max_parallel
            self.event('configuration_changed', max_parallel=max_parallel, client=client['id'], epoch=epoch)
            self._dispatch()
            return {'max_parallel': max_parallel}

    def submit(self, client, epoch, script, *, arguments=(), language='python',
               debug=False, stop_on_entry=True, breakpoints=None):
        # Git capture can be slow. Authenticate first, prepare outside the
        # control lock, then recheck the live fence at atomic admission. Worker
        # checkpoints and revocation must remain responsive during preparation.
        with self.lock:
            self._control(client, epoch)
            if self.closed.is_set() or not self.worker_url:
                raise SessionError('Session is not accepting procedures')
            if language not in {'python', 'spell'}:
                raise SessionError('Language must be python or spell', 400)
            if type(debug) is not bool or type(stop_on_entry) is not bool:
                raise SessionError('Debug options must be booleans', 400)
            if debug and self.execution_release:
                raise SessionError('Execution releases are immutable; debugging requires Development', 403)
            if debug and language != 'python':
                raise SessionError('Shared native SPELL debugging is unavailable in this backend', 400)
            if debug and self.interpreter_report.get('debugpy') != '1.8.22':
                raise SessionError('Shared debugging requires debugpy 1.8.22 in the service interpreter', 400)
            if breakpoints and not debug:
                raise SessionError('Breakpoints require a debug submission', 400)
            if not isinstance(script, str) or not isinstance(arguments, (list, tuple)) or len(arguments) > 128:
                raise SessionError('Invalid procedure arguments', 400)
            target = self.project / script
            if self.execution_release:
                script = Path(script).as_posix()
                target = self.project / script
                approved_language = self.release_manifest.get('backend',{}).get('provider','python')
                if script not in self.release_manifest['procedures'] or language != approved_language:
                    raise SessionError('Procedure is outside the approved runtime release', 400)
                if any(not isinstance(a, str) or '\0' in a for a in arguments):
                    raise SessionError('Invalid procedure arguments', 400)
                spec = LaunchSpec(self.project, target, self.interpreter, tuple(arguments))
            else:
                spec = LaunchSpec(self.project, target, self.interpreter, tuple(arguments)).validate()
            logical = spec.script.relative_to(self.project).as_posix()
            if debug:
                from .shared_debug import validate_breakpoints
                breakpoints = validate_breakpoints(spec.project, breakpoints or {})
        captured = None
        released = None
        backend = None
        if self.execution_release:
            with self.lock:
                released = self.authority.require(self.execution_release)
            if 'backend' in released:
                from .shared_backends import load_backend
                backend = load_backend(language).for_release(released)
            captured = self.project, released['source_digest'], released['source']
        elif self.store:
            if language != 'python':
                from .shared_backends import bind_backend
                backend = bind_backend(language)
            from .source_capture import capture
            captured = capture(self.project, logical, self.store.directory)
        elif language == 'spell':
            from .languages import check_spell
            check_spell(self.interpreter)
        with self.lock:
            self._control(client, epoch)
            if any(p.script == logical and p.status not in TERMINAL for p in self.procedures.values()):
                raise SessionError('This logical procedure is already active in the session')
            if sum(p.status not in TERMINAL for p in self.procedures.values()) >= 128:
                raise SessionError('Procedure queue limit reached')
            if len(self.procedures) >= 512:
                for identifier in [p.id for p in self.procedures.values() if p.status in TERMINAL][:256]:
                    del self.procedures[identifier]
            procedure = Procedure(uuid.uuid4().hex, logical, spec, language,
                                  captured[2]['files'][logical]['sha256'] if captured else
                                  hashlib.sha256(spec.script.read_bytes()).hexdigest(), backend=backend)
            if captured:
                from .procedure_identity import definition_id, version_id
                root, digest, manifest = captured
                procedure.spec = LaunchSpec(root, root / logical, self.interpreter, tuple(arguments))
                procedure.source_hash = manifest['files'][logical]['sha256']
                import tokenize
                if released:
                    identity = released['procedures'][logical]['definition']
                else:
                    with tokenize.open(procedure.spec.script) as source:
                        identity = definition_id(logical, source.read())
                bound = self.aliases.get(logical.casefold())
                if bound is not None and bound != identity:
                    raise SessionError('Catalog alias is already bound to another procedure definition')
                if any(p.definition == identity and (p.status not in TERMINAL or p.uncertain)
                       for p in self.procedures.values()):
                    raise SessionError('This logical procedure is already active or requires reconciliation')
                self.aliases[logical.casefold()] = identity
                self.fences[identity] = self.fences.get(identity, 0) + 1
                procedure.definition, procedure.fence = identity, self.fences[identity]
                procedure.capture_digest = digest
                procedure.version = version_id(identity, procedure.source_hash,
                    {'provider': language, 'binding': backend} if backend is not None else 'python/3.13', digest)
                if released:
                    procedure.release, procedure.version = self.execution_release, released['procedures'][logical]['version']
            if debug:
                from .shared_debug import initial_state, validate_breakpoints
                procedure.debug_initial_breakpoints = validate_breakpoints(procedure.spec.project, breakpoints)
                procedure.debug = initial_state()
                procedure.stop_on_entry = stop_on_entry
            self.procedures[procedure.id] = procedure
            self.event('queued', procedure=procedure.id, script=logical, client=client['id'], epoch=epoch,
                       definition=procedure.definition, version=procedure.version, fence=procedure.fence,
                       release=procedure.release)
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
                elif procedure.debugger:
                    pending = procedure.debug_pending or ('continue', {'threadId': procedure.debug['thread_id']}, self.epoch)
                    procedure.debug_pending = None
                    if pending[2] != self.epoch:
                        self._pause(procedure, 'STALE_DEBUG_REQUEST')
                    else:
                        procedure.debugger.resume(pending[0], pending[1])

    def _execute(self, procedure):
        if procedure.debug:
            from .shared_debug import SharedDebugger
            with self.lock:
                procedure.debugger = SharedDebugger(self, procedure)
            return procedure.debugger.run()
        if procedure.backend is not None:
            from .shared_backends import execute
            return execute(self, procedure)
        pumps = []
        try:
            with self.lock:
                if not procedure.has_token or self.closed.is_set():
                    return
                spec = procedure.spec
                if procedure.capture_digest and not procedure.release:
                    from .source_capture import verify_capture
                    verify_capture(spec.project, procedure.capture_digest)
                environment = clean_environment()
                environment['OPENBEXI_SESSION_WORKER'] = __import__('json').dumps({
                    'url': self.worker_url, 'id': procedure.id, 'token': procedure.secret,
                    'language': procedure.language, 'source_hash': procedure.source_hash,
                    'dss_url': self.dss_url})
                command = [str(spec.interpreter), '-I', '-B', '-u', '-X', 'utf8',
                           str(Path(__file__).with_name('session_worker.py')),
                           str(spec.project), str(spec.script), *spec.arguments]
                if procedure.release:
                    from .execution_container import ContainerOwner, ContainerChannel
                    manifest = self.authority.require(procedure.release)
                    procedure.owner = ContainerOwner(self.id, procedure, manifest)
                    process = procedure.owner.start()
                else:
                    process, procedure.owner = start_owned_process(command, cwd=spec.project, env=environment,
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        start_new_session=os.name != 'nt',
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                procedure.process = process
                if procedure.release:
                    procedure.channel = ContainerChannel(self, procedure)
                    config = __import__('json').loads(environment['OPENBEXI_SESSION_WORKER'])
                    config.pop('url')
                    procedure.channel.send(config)
                self.event('started', procedure=procedure.id, pid=process.pid)
            writer = threading.Thread(target=self._input_pump, args=(procedure,), daemon=True)
            writer.start()
            for stream, name in ((process.stdout, 'stdout'), (process.stderr, 'stderr')):
                pump = (threading.Thread(target=procedure.channel.read, daemon=True)
                        if procedure.channel and name == 'stdout' else
                        threading.Thread(target=self._pump, args=(procedure.id, stream, name), daemon=True))
                pumps.append(pump)
                pump.start()
            if procedure.channel:
                heartbeat = threading.Thread(target=procedure.channel.heartbeat, daemon=True)
                pumps.append(heartbeat)
                heartbeat.start()
            code = process.wait()
            if procedure.release and not procedure.owner.closed:
                state = procedure.owner.inspect()['State']
                if state['Running'] or state['ExitCode'] != 0:
                    code = state['ExitCode'] or 75
            procedure.owner.close()
            try:
                procedure.input_queue.put_nowait(None)
            except queue.Full:
                pass
            writer.join(timeout=2)
            for pump in pumps:
                pump.join(timeout=3)
            with self.lock:
                if procedure.channel and procedure.channel.error:
                    procedure.error, code = procedure.channel.error, 75
                procedure.exit_code = code
                procedure.status = 'CANCELLED' if procedure.cancelled else 'COMPLETED' if code == 0 else 'FAILED'
                if self.store and (code != 0 or procedure.cancelled):
                    # Arbitrary Python may affect external systems. Abnormal
                    # termination supplies no proof that those effects settled.
                    procedure.uncertain = True
        except BaseException as error:
            with self.lock:
                procedure.error, procedure.status = str(error), 'FAILED'
                if procedure.release and procedure.owner and procedure.owner.started:
                    procedure.uncertain = True
        finally:
            if procedure.channel:
                procedure.channel.done.set()
            if procedure.owner:
                try:
                    procedure.owner.close()
                except (ValueError, OSError, subprocess.SubprocessError) as error:
                    procedure.error, procedure.uncertain = str(error), True
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
                    if procedure.uncertain:
                        procedure.status, procedure.reason = 'RECOVERY_REQUIRED', 'UNCERTAIN_EFFECTS'
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
                    if procedure.channel:
                        procedure.channel.send({'type': 'input', 'text': None})
                    else:
                        procedure.process.stdin.close()
                    return
                if procedure.channel:
                    procedure.channel.send({'type': 'input', 'text': chunk.decode('utf-8')})
                else:
                    procedure.process.stdin.write(chunk)
                    procedure.process.stdin.flush()
        except (OSError, ValueError):
            self.event('input_closed', procedure=procedure.id)

    def _pause(self, procedure, reason='USER_PAUSED'):
        if procedure.status == 'RECOVERY_REQUIRED':
            return
        procedure.wants_run, procedure.reason = False, reason
        if procedure.status in TERMINAL or procedure.status == 'STOPPING':
            return
        if procedure.debug:
            procedure.debug_pending = None
            if procedure.debugger and procedure.debugger.adapter:
                procedure.status = 'PAUSING'
                procedure.debugger.pause()
                self.event('pause_requested', procedure=procedure.id, reason=reason)
                return
        if procedure.process is None and procedure.owner is None:
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
            if any(p.status == 'RECOVERY_REQUIRED' or p.uncertain for p in selected):
                raise SessionError('Recovery hold requires offline shutdown and effect reconciliation')
            if action == 'resume' and any(p.status not in TERMINAL and p.status != 'PAUSED' for p in selected):
                raise SessionError('Wait for every selected procedure to confirm PAUSED before resuming')
            for procedure in selected:
                if procedure.status in TERMINAL:
                    continue
                if action == 'pause':
                    self._pause(procedure)
                elif action == 'resume':
                    if procedure.debug and procedure.debug.get('state') == 'unavailable':
                        raise SessionError('The debugger session cannot be restored; submit a new debug procedure')
                    procedure.wants_run, procedure.reason = True, 'WAITING_TOKEN'
                    self.event('resume_requested', procedure=procedure.id, client=client['id'], epoch=epoch)
                else:
                    procedure.cancelled, procedure.wants_run = True, False
                    if procedure.process or procedure.owner:
                        procedure.status = 'STOPPING'
                        if procedure.owner:
                            procedure.owner.close()
                    else:
                        procedure.status, procedure.has_token = 'CANCELLED', False
                    self.event('stop_requested', procedure=procedure.id, client=client['id'], epoch=epoch)
            self._dispatch()
            return [p.public() for p in selected]

    def debug_request(self, client, epoch, identifier, command, arguments=None, revision=None):
        """Admit one DAP request at the live fence; never proxy arbitrary DAP."""
        from .shared_debug import COMMANDS, CONTROL, source_path, validate_breakpoints
        arguments = {} if arguments is None else arguments
        with self.lock:
            self._control(client, epoch)
            if self.execution_release:
                raise SessionError('Debugging requires Development', 403)
            p = self.procedures.get(identifier)
            if p is None:
                raise SessionError('Procedure does not exist', 404)
            if not p.debug or not p.debugger or p.status in TERMINAL or p.uncertain:
                raise SessionError('This procedure has no active shared debugger')
            if not isinstance(command, str) or command not in COMMANDS:
                raise SessionError('Unsupported shared debugger request', 400)
            if type(arguments) is not dict:
                raise SessionError('Debugger arguments must be an object', 400)
            arguments = copy.deepcopy(arguments)
            debug, adapter = p.debug, p.debugger
            if type(revision) is not int or revision != debug['revision']:
                raise SessionError('Stale debugger snapshot revision')
            allowed = {
                'continue': {'threadId'}, 'next': {'threadId'}, 'stepIn': {'threadId'}, 'stepOut': {'threadId'},
                'pause': {'threadId'}, 'threads': set(),
                'stackTrace': {'threadId', 'startFrame', 'levels'}, 'scopes': {'frameId'},
                'variables': {'variablesReference', 'start', 'count', 'filter'},
                'exceptionInfo': {'threadId'}, 'setBreakpoints': {'source', 'breakpoints'},
                'evaluate': {'expression', 'frameId', 'context'},
                'setVariable': {'variablesReference', 'name', 'value'},
                'setExpression': {'expression', 'value', 'frameId'}}
            if set(arguments) - allowed[command]:
                raise SessionError('Unsupported debugger argument', 400)
            if command not in {'setBreakpoints', 'threads', 'pause'} and debug['state'] != 'paused':
                raise SessionError('Wait for a stopped debugger snapshot')
            thread_ids = {item['id'] for item in debug['threads']}
            frame_ids = {frame['id'] for frames in debug['stacks'].values() for frame in frames}
            variable_ids = {scope['variablesReference'] for scopes in debug['scopes'].values() for scope in scopes}
            variable_ids.update(value['variablesReference'] for values in debug['variables'].values()
                                for value in values if value.get('variablesReference'))
            for key, valid in (('threadId', thread_ids), ('frameId', frame_ids), ('variablesReference', variable_ids)):
                if key in arguments and (type(arguments[key]) is not int or arguments[key] not in valid):
                    raise SessionError('Unknown or stale debugger handle')
            required = {'stackTrace': 'threadId', 'scopes': 'frameId', 'variables': 'variablesReference',
                        'setVariable': 'variablesReference', 'evaluate': 'frameId', 'setExpression': 'frameId',
                        'exceptionInfo': 'threadId'}
            if required.get(command) and required[command] not in arguments:
                raise SessionError('Debugger request requires ' + required[command], 400)
            for key in ('expression', 'name', 'value', 'context'):
                if key in arguments and (not isinstance(arguments[key], str) or len(arguments[key]) > 8192):
                    raise SessionError('Invalid debugger text argument', 400)
            for key in ('startFrame', 'levels', 'start', 'count'):
                if key in arguments and (type(arguments[key]) is not int or not 0 <= arguments[key] <= 512):
                    raise SessionError('Debugger view exceeds its bound', 400)
            if command == 'variables':
                arguments['count'] = arguments.get('count') or 64
                arguments.setdefault('start', 0)
            elif command == 'stackTrace':
                arguments['levels'] = arguments.get('levels') or 32
                arguments.setdefault('startFrame', 0)
            if command == 'setBreakpoints':
                source = arguments.get('source')
                points = arguments.get('breakpoints', [])
                if type(source) is not dict or set(source) != {'path'} or type(points) is not list:
                    raise SessionError('Invalid shared breakpoint source', 400)
                if any(type(item) is not dict or set(item) != {'line'} for item in points):
                    raise SessionError('Shared breakpoints accept line numbers', 400)
                validated = validate_breakpoints(p.spec.project, {source['path']: [item['line'] for item in points]})
                name, lines = next(iter(validated.items()))
                arguments = {'source': {'path': str(source_path(p.spec.project, name))},
                             'breakpoints': [{'line': line} for line in lines]}
            if command in {'setVariable', 'setExpression'}:
                capability = 'supportsSetVariable' if command == 'setVariable' else 'supportsSetExpression'
                if not debug['capabilities'].get(capability):
                    raise SessionError('The debugger backend does not support ' + command, 400)
            if command == 'pause':
                self._pause(p)
                return {'accepted': True, 'debug': copy.deepcopy(debug)}
            if command in CONTROL:
                if p.status != 'PAUSED':
                    raise SessionError('Wait for all threads and child processes to pause')
                if p.debug_pending:
                    raise SessionError('A debugger continuation is already waiting for an execution slot')
                arguments.setdefault('threadId', debug['thread_id'])
                if arguments['threadId'] not in thread_ids:
                    raise SessionError('Wait for the current thread snapshot')
                p.debug_pending = (command, arguments, epoch)
                p.wants_run, p.reason = True, 'WAITING_TOKEN'
                self.event('debug_requested', procedure=p.id, command=command, client=client['id'], epoch=epoch)
                self._dispatch()
                return {'accepted': True, 'debug': copy.deepcopy(debug)}
            evaluates = command in {'evaluate', 'setVariable', 'setExpression'}
            if evaluates:
                if p.status != 'PAUSED' or p.debug_pending:
                    raise SessionError('Wait for the debugger to settle before evaluating')
                if sum(item.has_token for item in self.procedures.values()) >= self.max_parallel:
                    raise SessionError('Evaluation requires an available execution slot')
                p.has_token, p.status = True, 'RUNNING'
                debug['state'], debug['all_threads_stopped'] = 'evaluating', False
                adapter.evaluating = True
            try:
                future = adapter.send(command, arguments)
            except BaseException:
                if evaluates:
                    adapter.finish_evaluation()
                raise
            if evaluates:
                # This callback settles the real operation even when HTTP has
                # timed out or its controller has been fenced in the meantime.
                future.add_done_callback(lambda _result: adapter.finish_evaluation())
            self.event('debug_requested', procedure=p.id, command=command, client=client['id'], epoch=epoch)
        # Responses must not hold the authority lock: expiry and handoff remain
        # effective even while debugpy is busy evaluating a controller request.
        body = adapter.result(future)
        with self.lock:
            self._control(client, epoch)
            if debug['revision'] != revision:
                raise SessionError('Debugger response belongs to a stale snapshot')
            body = adapter.cache(command, arguments, body)
            if command in {'evaluate', 'setVariable', 'setExpression'}:
                refreshed = adapter.invalidate('paused')
                threading.Thread(target=adapter.refresh, args=(refreshed,), daemon=True).start()
            return {'body': body, 'debug': copy.deepcopy(debug)}

    def debug_source(self, identifier, name):
        """Read one bounded source copy from the procedure's actual project."""
        import io
        import json
        import tokenize
        from .shared_debug import source_path
        from .session_store import canonical
        with self.lock:
            p = self.procedures.get(identifier)
            if p is None or not p.debug:
                raise SessionError('Select a shared debug procedure', 404)
            path = source_path(p.spec.project, name)
            expected = None
            if p.capture_digest:
                manifest = json.loads(p.spec.project.with_suffix('.json').read_text(encoding='utf-8'))
                if hashlib.sha256(canonical(manifest).encode()).hexdigest() != p.capture_digest:
                    raise SessionError('Captured source manifest differs', 409)
                expected = manifest['files'].get(name, {}).get('sha256')
                if expected is None:
                    raise SessionError('Source is outside the captured tree', 400)
            with path.open('rb') as stream:
                raw = stream.read(2_000_001)
            if len(raw) > 2_000_000:
                raise SessionError('Source view exceeds 2 MB', 413)
            digest = hashlib.sha256(raw).hexdigest()
            if expected is not None and digest != expected:
                raise SessionError('Captured source bytes differ', 409)
            try:
                encoding = tokenize.detect_encoding(io.BytesIO(raw).readline)[0]
                text = raw.decode(encoding)
            except (SyntaxError, UnicodeError) as error:
                raise SessionError('Source has an invalid declared Python encoding', 400) from error
            return {'procedure': p.id, 'path': name, 'text': text,
                    'sha256': digest, 'captured': bool(p.capture_digest),
                    'capture_sha256': p.capture_digest}

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
            if procedure.input_queue.full():
                raise SessionError('Procedure input queue is full; wait before sending more')
            if text is None:
                procedure.input_closed = True
            self.event('input_submitted', procedure=procedure.id, client=client['id'], epoch=epoch,
                       eof=text is None, bytes=0 if text is None else len(text.encode('utf-8')))
            try:
                procedure.input_queue.put_nowait(None if text is None else (text + '\n').encode('utf-8'))
            except queue.Full as error:
                raise SessionError('Procedure input queue is full; wait before sending more') from error
            return {'accepted': True}

    def checkpoint(self, body, *, isolated=False):
        with self.lock:
            procedure = self.procedures.get(body.get('id'))
            token = body.get('token')
            if not procedure or not isinstance(token, str) or not secrets.compare_digest(token, procedure.secret):
                raise SessionError('Worker credential rejected', 403)
            if procedure.backend is not None:
                raise SessionError('Plugin workers cannot use Python checkpoints', 403)
            if procedure.debug:
                raise SessionError('Debug workers use the private adapter transport', 403)
            if bool(procedure.release) != isolated:
                raise SessionError('Worker transport does not match its execution boundary', 403)
            self._expire()
            worker_pid = body.get('pid')
            if type(worker_pid) is not int or worker_pid <= 0 or procedure.worker_pid not in {None, worker_pid}:
                raise SessionError('Worker process identity differs', 400)
            procedure.worker_pid = worker_pid
            if body.get('bootstrap') is True and procedure.bootstrap_pids is None:
                procedure.bootstrap_pids = procedure.owner.process_ids() if procedure.owner else None
                if not isolated and procedure.bootstrap_pids is not None and worker_pid not in procedure.bootstrap_pids:
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
            return {'session': self.id, 'mode': 'Execution' if self.execution_release else 'Development', 'project': str(self.project),
                    'durable': self.store is not None,
                    'storage_healthy': not self.storage_failed,
                    'execution_approved': bool(self.execution_release),
                    'debug_capabilities': {
                        'python': {'available': not self.execution_release and self.interpreter_report.get('debugpy') == '1.8.22',
                                   'backend': 'debugpy', 'controller_only': True},
                        'spell': {'available': False, 'reason': 'Shared native SPELL DAP is unavailable'}},
                    'release_id': self.execution_release,
                    'execution_profile': self.release_manifest['profile'] if self.release_manifest else None,
                    'approved_sources': ({name: self.release_manifest['source']['files'][name]['sha256']
                                          for name in self.release_manifest['procedures']}
                                         if self.release_manifest else {}),
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
                elif procedure.status not in TERMINAL and procedure.status != 'RECOVERY_REQUIRED':
                    procedure.wants_run, procedure.has_token = False, False
                    procedure.status, procedure.reason = 'PAUSED', 'SERVICE_STOPPED'
            threads = [p.thread for p in self.procedures.values() if p.thread]
        for thread in threads:
            thread.join(timeout=6)
        self.housekeeper.join(timeout=2)
        if any(thread.is_alive() for thread in threads):
            raise RuntimeError('Worker cleanup is unconfirmed; durable service ownership is retained')
        if self.store and self.store.db is not None:
            with self.lock:
                if not self.storage_failed:
                    self.event('service_stopped', epoch=self.epoch)
                self.store.close()
