"""Server-owned local procedure execution shared by desktop and browser clients.

The service is a trusted local Development workspace. Its bearer credentials are
stored in the user's profile, never in source snapshots. Approved Execution and
remote TLS sessions continue to use the separately fenced session service.
"""
from concurrent.futures import Future
import argparse
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import tokenize
from urllib.parse import urlsplit, parse_qs

from .bounded_http import BoundedHTTPServer
from .dap import MessageReader, encode_message
from .launch import clean_environment, LaunchSpec
from .procedure_model import ProcedureRun
from .procedure_records import ProcedureRecords
from .procedure_colors import PROCEDURE_COLORS, RESULT_COLORS, CURRENT_LINE
from .processes import start_owned_process

READ_COMMANDS = {'threads', 'stackTrace', 'scopes', 'variables', 'source', 'loadedSources'}
CONTROL_COMMANDS = {'configurationDone', 'setBreakpoints', 'setExceptionBreakpoints', 'continue',
                    'pause', 'next', 'stepIn', 'evaluate', 'setVariable', 'spell/promptAnswer',
                    'openbexi/input', 'disconnect'}
TERMINAL = {'FINISHED', 'ABORTED', 'ERROR'}


def workspace_directory(project):
    root = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share')) / 'OpenBEXI' / 'procedure-services'
    identity = hashlib.sha256(os.path.normcase(str(Path(project).resolve())).encode()).hexdigest()[:24]
    return root / identity


def implementation_id():
    root = Path(__file__).parent
    digest = hashlib.sha256()
    for path in sorted([*root.glob('procedure_*.py'), *root.joinpath('procedure_web').glob('*')]):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode()); digest.update(path.read_bytes())
    return digest.hexdigest()


class Adapter:
    def __init__(self, command, project, callback, ended):
        self.lock = threading.Lock(); self.sequence = 0; self.pending = {}
        self.callback = callback; self.ended = ended
        self.process, self.owner = start_owned_process(command, cwd=project, env=clean_environment(),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=os.name != 'nt', creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        threading.Thread(target=self.read, daemon=True).start()
        threading.Thread(target=self.errors, daemon=True).start()

    def request(self, command, arguments=None, timeout=40):
        future = Future()
        with self.lock:
            self.sequence += 1; sequence = self.sequence
            self.pending[sequence] = future
            try:
                self.process.stdin.write(encode_message(dict(seq=sequence, type='request', command=command, arguments=arguments or {})))
                self.process.stdin.flush()
            except (OSError, ValueError):
                self.pending.pop(sequence, None)
                raise RuntimeError('The native executor has closed') from None
        try:
            return future.result(timeout)
        finally:
            with self.lock:
                self.pending.pop(sequence, None)

    def read(self):
        reader = MessageReader(); error = ''
        try:
            while data := self.process.stdout.read1(65536):
                for message in reader.feed(data):
                    if message['type'] == 'response':
                        with self.lock:
                            future = self.pending.pop(message.get('request_seq'), None)
                        if future:
                            if message.get('success'):
                                future.set_result(message.get('body') or {})
                            else:
                                future.set_exception(RuntimeError(message.get('message', 'Native command rejected')))
                    elif message['type'] == 'event':
                        self.callback(message)
                    else:
                        raise RuntimeError('This procedure adapter cannot request an external terminal')
        except Exception as exc:
            error = str(exc)
        finally:
            with self.lock:
                for future in self.pending.values():
                    future.set_exception(RuntimeError(error or 'The native executor has closed'))
                self.pending.clear()
            try:
                code = self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.owner.close(); code = self.process.wait(timeout=10)
            self.owner.close()
            self.ended(code, error)

    def errors(self):
        while data := self.process.stderr.read1(16384):
            self.callback(dict(type='event', event='output', body=dict(category='stderr', output=data.decode('utf-8', 'replace'))))

    def close(self):
        self.owner.close()


class ProcedureService:
    lease_seconds = 30

    def __init__(self, project, directory, *, adapter_factory=Adapter):
        self.project = Path(project).resolve(); self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.records = ProcedureRecords(self.directory / 'records.sqlite3')
        self.lock = threading.RLock(); self.changed = threading.Condition(self.lock)
        self.runs = {}; self.adapters = {}; self.clients = {}; self.owners = {}; self.pending = {}
        self.revision = 0; self.adapter_factory = adapter_factory; self.closed = False
        self.instance = secrets.token_hex(16)
        self.operator_key = secrets.token_urlsafe(32); self.monitor_key = secrets.token_urlsafe(32)
        for record in reversed(self.records.recent(self.project)):
            if not record['snapshot']:
                continue
            run = ProcedureRun.restore(record['snapshot']); run.journal = self.records
            if run.active:
                run.active = False; run.status = 'UNKNOWN'; run.connection = 'Disconnected'
                run.prompt = None; run.controller = ''; run.persist()
            self.runs[run.identifier] = run

    def touch(self):
        self.revision += 1; self.changed.notify_all()

    def acknowledge_state(self, run):
        command = self.pending.get(run.identifier)
        if ((command in {'continue', 'next', 'stepIn'} and run.status not in {'PAUSED', 'INTERRUPTED'})
                or (command in {'pause', 'pause after controller disconnect'} and run.status in {'PAUSED', 'INTERRUPTED'})
                or run.status in TERMINAL):
            self.pending.pop(run.identifier, None)

    def connect(self, key, name, principal=None):
        role = ('operator' if hmac.compare_digest(key, self.operator_key) else
                'monitor' if hmac.compare_digest(key, self.monitor_key) else None)
        if role is None:
            raise PermissionError('Invalid workspace credential')
        if principal:
            role = 'monitor' if principal['role'] == 'monitor' or role == 'monitor' else 'operator'
            name = principal['name']
        identifier = secrets.token_urlsafe(32)
        with self.lock:
            if len(self.clients) >= 128:
                raise ValueError('The workspace client limit has been reached')
            self.clients[identifier] = dict(role=role, name=str(name)[:80], seen=time.monotonic(),
                subject=principal['subject'] if principal else None)
        return dict(client=identifier, role=role)

    def client(self, identifier, control=False):
        value = self.clients.get(identifier)
        if not value:
            raise PermissionError('Reconnect to the procedure service')
        if control and value['role'] != 'operator':
            raise PermissionError('Monitoring connections are read-only')
        value['seen'] = time.monotonic()
        return value

    def own(self, client, run):
        self.client(client, control=True)
        if self.owners.get(run.identifier) != client:
            raise PermissionError('Claim control of this procedure first')

    def claim(self, client, identifier, release=False):
        with self.lock:
            actor = self.client(client, control=True); run = self.runs[identifier]
            if not run.active:
                raise ValueError('Completed records cannot be resumed')
            if self.pending.get(identifier):
                raise ValueError('Wait for the native command before changing control')
            owner = self.owners.get(identifier)
            if owner and owner != client:
                raise PermissionError('This procedure already has a controller')
            if release:
                if run.status not in {'PAUSED', 'INTERRUPTED', 'PROMPT'}:
                    raise ValueError('Pause the procedure before releasing control')
                self.owners.pop(identifier, None); run.controller = ''
            else:
                self.owners[identifier] = client; run.controller = actor['name']
            run.persist(); self.touch()
        return {}

    def start(self, client, arguments):
        from .launch import interpreter_info
        with self.lock:
            self.client(client, control=True)
            if self.closed:
                raise ValueError('This procedure service is shutting down for an update')
        spec = LaunchSpec(self.project, self.project / arguments['script'],
                          Path(arguments.get('interpreter') or sys.executable),
                          tuple(arguments.get('args', [])), arguments.get('language', 'spell')).validate()
        info = interpreter_info(spec.interpreter, require_debugger=True, language=spec.language)
        backend = info.get('backend') or {}
        if not backend.get('procedureWorkspace'):
            raise ValueError('Select an installed procedure-workspace backend')
        with self.lock:
            actor = self.client(client, control=True)
            if self.closed:
                raise ValueError('This procedure service is shutting down for an update')
            if any(run.active and (run.status not in {'PAUSED', 'INTERRUPTED'} or self.pending.get(run.identifier)) for run in self.runs.values()):
                raise ValueError('Pause the running procedure before opening another instance')
            if sum(run.active for run in self.runs.values()) >= 8:
                raise ValueError('At most eight live procedure instances are supported')
            if os.environ.get('OPENBEXI_SPELL_BACKEND') == 'packaged-desktop' and any(r.active for r in self.runs.values()):
                raise ValueError('The packaged native desktop supports one live instance at a time')
            run = ProcedureRun(self.project, spec.script, 'Run' if arguments.get('noDebug', True) else 'Debug')
            with tokenize.open(spec.script) as source:
                text = source.read(2 * 1024 * 1024 + 1)
            if len(text) > 2 * 1024 * 1024:
                raise ValueError('Procedure source exceeds 2 MiB')
            run.sources[spec.script] = text; run.status = 'LOADED'; run.controller = actor['name']
            self.records.create(self.project, spec.script, run.mode, run.identifier)
            run.journal = self.records; run.persist()
            self.runs[run.identifier] = run; self.owners[run.identifier] = client
            self.pending[run.identifier] = 'launch'; self.touch()
        command = [str(spec.interpreter), '-I', '-B', '-u', '-X', 'utf8', '-m', backend['debugAdapter'], '--project', str(self.project)]
        if arguments.get('image'):
            command += ['--image', arguments['image']]
        try:
            adapter = self.adapter_factory(command, self.project,
                lambda message: self.event(run, message), lambda code, error: self.ended(run, code, error))
            with self.lock:
                self.adapters[run.identifier] = adapter
            capabilities = adapter.request('initialize', dict(clientID='openbexi-service', adapterID=spec.language,
                linesStartAt1=True, columnsStartAt1=True, pathFormat='path', supportsRunInTerminalRequest=False))
            adapter.request('launch', dict(program=str(spec.script), project=str(self.project), args=list(spec.arguments),
                noDebug=arguments.get('noDebug', True), stopOnEntry=arguments.get('stopOnEntry', False)))
            if arguments.get('configure', True):
                adapter.request('setExceptionBreakpoints', {'filters': ['uncaught']})
                adapter.request('configurationDone')
            return dict(id=run.identifier, capabilities=capabilities)
        except Exception as error:
            if run.identifier in self.adapters:
                self.adapters[run.identifier].close()
            self.ended(run, 1, str(error)); raise
        finally:
            with self.lock:
                self.pending.pop(run.identifier, None); self.touch()

    def event(self, run, message):
        with self.lock:
            self.records.append(run.identifier, dict(kind='dap', message=message))
            event, body = message.get('event'), message.get('body') or {}
            if event == 'openbexi/procedure':
                run.apply(body)
            elif event == 'output':
                run.output = (run.output + str(body.get('output', '')))[-524288:]
            elif event == 'stopped':
                run.status = 'PAUSED'
            elif event == 'continued':
                run.status = 'RUNNING'
            elif event == 'exited':
                run.exit_code = body.get('exitCode')
            elif event == 'terminated':
                # Native adapters wait for disconnect even after completing.
                # Send it off the reader thread so its response can be read.
                def disconnect():
                    try:
                        self.adapters[run.identifier].request('disconnect', {'terminateDebuggee': False})
                    except (RuntimeError, KeyError, TimeoutError):
                        pass
                threading.Thread(target=disconnect, daemon=True).start()
            # Terminal DAP events precede artifact export and process cleanup.
            # Keep the slot occupied until the adapter has actually ended.
            self.acknowledge_state(run)
            run.persist(); self.touch()

    def ended(self, run, code, error):
        with self.lock:
            if not run.active:
                return
            run.active = False; run.prompt = None; run.answering = False
            run.error = error; run.exit_code = run.exit_code if run.exit_code is not None else code if code is not None else 1
            run.status = 'ABORTED' if run.aborted or run.exit_code == 130 else 'FINISHED' if run.exit_code == 0 else 'ERROR'
            run.controller = ''; self.owners.pop(run.identifier, None)
            self.pending.pop(run.identifier, None); run.persist(); self.touch()
            self.adapters.pop(run.identifier, None)
            completed = [key for key, value in self.runs.items() if not value.active]
            for key in completed[:-100]:
                self.runs.pop(key, None)

    def command(self, client, identifier, command, arguments):
        with self.lock:
            self.client(client); run = self.runs[identifier]
            if not run.active:
                if command == 'disconnect':
                    return {}
                raise ValueError('This execution has ended; its record is read-only')
            if command not in READ_COMMANDS | CONTROL_COMMANDS:
                raise ValueError('This native capability is unavailable')
            if command not in READ_COMMANDS:
                self.own(client, run)
                if identifier in self.pending:
                    raise ValueError('A command is awaiting native acknowledgement')
                if command in {'continue', 'next', 'stepIn'}:
                    if run.status not in {'PAUSED', 'INTERRUPTED'}:
                        raise ValueError('The procedure must be paused')
                    if any(r is not run and r.active and (r.status not in {'PAUSED', 'INTERRUPTED'} or self.pending.get(r.identifier)) for r in self.runs.values()):
                        raise ValueError('Another procedure owns the execution slot')
                if command == 'pause' and run.status not in {'RUNNING', 'WAITING', 'PROMPT'}:
                    raise ValueError('Only a running or waiting procedure can be paused')
                if command == 'evaluate':
                    raise ValueError('Expression evaluation is unavailable in the native adapter')
                if command in {'spell/promptAnswer', 'openbexi/input'}:
                    if not run.prompt or run.answering or arguments.get('promptId') != run.prompt.get('promptId'):
                        raise ValueError('This prompt is no longer accepting an answer')
                    answer = arguments.get('value', arguments.get('text'))
                    if not isinstance(answer, str) or len(answer.encode('utf-8')) > 65536:
                        raise ValueError('Prompt answers must be text no larger than 64 KiB')
                    choices = run.prompt.get('choices')
                    if choices and answer not in [choice['value'] for choice in choices]:
                        raise ValueError('Select one of the offered answers')
                    run.answering = True
                if command == 'disconnect' and run.status not in TERMINAL:
                    run.aborted = True
                self.pending[identifier] = command; self.touch()
            adapter = self.adapters[identifier]
        acknowledged = False
        try:
            result = adapter.request(command, arguments)
            acknowledged = True
            with self.lock:
                if command in {'spell/promptAnswer', 'openbexi/input'} and run.prompt and arguments.get('promptId') == run.prompt.get('promptId'):
                    run.prompt = None
                return result
        finally:
            with self.lock:
                if self.pending.get(identifier) == command and (not acknowledged or command not in {'continue', 'next', 'stepIn', 'pause', 'disconnect'}):
                    self.pending.pop(identifier, None)
                self.acknowledge_state(run)
                run.answering = False; run.persist(); self.touch()

    def snapshot(self, client):
        with self.lock:
            actor = self.client(client)
            return dict(project=str(self.project), instance=self.instance, revision=self.revision, role=actor['role'],
                runs=[dict(run.snapshot(), controlling=self.owners.get(run.identifier) == client,
                           pending=self.pending.get(run.identifier, '')) for run in reversed(list(self.runs.values()))],
                colors=dict(procedure=PROCEDURE_COLORS, result=RESULT_COLORS, current=CURRENT_LINE),
                capabilities=dict(run=True, pause=True, step=True, stepOver=True, abort=True,
                    skip=False, goto=False, recover=False, runUntil=False, byStep=False, scheduling=False,
                    shell=False, tcConfirmation=False, maxRunning=1,
                    maxInstances=1 if os.environ.get('OPENBEXI_SPELL_BACKEND') == 'packaged-desktop' else 8))

    def detach(self, client):
        with self.lock:
            self.client(client)['seen'] = time.monotonic() - self.lease_seconds - 1
        self.expire()
        return {}

    def expire(self):
        """Losing a controller requests a real pause; it never fabricates PAUSED."""
        with self.lock:
            stale = [key for key, value in self.clients.items() if time.monotonic() - value['seen'] > self.lease_seconds]
            pauses = []
            for identifier, owner in list(self.owners.items()):
                if owner in stale:
                    run = self.runs[identifier]; run.controller = ''; self.owners.pop(identifier)
                    if run.active and run.status not in {'PAUSED', 'INTERRUPTED', 'PROMPT'}:
                        self.pending[identifier] = 'pause after controller disconnect'
                        pauses.append((run, self.adapters.get(identifier)))
            for key in stale:
                self.clients.pop(key, None)
            if stale:
                self.touch()
        for run, adapter in pauses:
            acknowledged = False
            try:
                if adapter:
                    adapter.request('pause', {'threadId': 1})
                    acknowledged = True
            except Exception as error:
                with self.lock:
                    run.error = 'Controller disconnected; pause not acknowledged: ' + str(error)
            finally:
                with self.lock:
                    if not acknowledged:
                        self.pending.pop(run.identifier, None)
                    self.acknowledge_state(run); run.persist(); self.touch()

    def close(self):
        self.closed = True
        for adapter in list(self.adapters.values()):
            adapter.close()


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_):
        pass  # Credentials and prompt values must not appear in access logs.

    def setup(self):
        super().setup(); self.connection.settimeout(50)

    def send(self, code, value, content_type='application/json'):
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False).encode() if content_type == 'application/json' else value
        self.send_response(code); self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload))); self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers(); self.wfile.write(payload)

    def route(self, mutate=False):
        service = self.server.service
        if self.headers.get('Host') != self.server.authority:
            raise PermissionError('Invalid workspace host')
        origin = self.headers.get('Origin')
        if origin and origin != getattr(self.server, 'scheme', 'http') + '://' + self.server.authority:
            raise PermissionError('Cross-origin requests are not accepted')
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise PermissionError('Cross-site requests are not accepted')
        target = urlsplit(self.path); path = target.path; query = parse_qs(target.query)
        data = {}
        if mutate:
            if self.headers.get('Content-Type') != 'application/json' or self.headers.get('Transfer-Encoding'):
                raise ValueError('Send a JSON request with Content-Length')
            lengths = self.headers.get_all('Content-Length') or []
            if len(lengths) != 1 or not lengths[0].isdigit() or not 0 < int(lengths[0]) <= 1024 * 1024:
                raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(int(lengths[0])))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object')
        if not mutate and path in {'/', '/app.js', '/app.css'}:
            filename, mime = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                              '/app.css': ('app.css', 'text/css; charset=utf-8')}[path]
            return self.send(200, (Path(__file__).parent / 'procedure_web' / filename).read_bytes(), mime)
        token = self.headers.get('Authorization', '').removeprefix('Bearer ')
        principal = None
        if getattr(self.server, 'identities', None):
            certificate = self.connection.getpeercert(binary_form=True)
            principal = self.server.identities.principal(certificate) if certificate else None
            if not principal:
                raise PermissionError('The connection certificate is unregistered or revoked')
        if path == '/api/connect' and mutate:
            return self.send(200, service.connect(token, data.get('name', 'Client'), principal))
        with service.lock:
            member = service.client(token)
            if principal and (member['subject'] != principal['subject'] or
                              member['role'] == 'operator' and principal['role'] != 'developer'):
                raise PermissionError('Connection identity or role differs from the workspace session')
        if path == '/api/heartbeat' and not mutate:
            return self.send(200, {'connected': True})
        if path == '/api/disconnect' and mutate:
            return self.send(200, service.detach(token))
        if path == '/api/shutdown' and mutate:
            with service.lock:
                service.client(token, control=True)
                if any(run.active for run in service.runs.values()):
                    raise ValueError('Stop all live procedure instances before updating the service')
                service.closed = True
            self.send(200, {'stopping': True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if path == '/api/state' and not mutate:
            return self.send(200, service.snapshot(token))
        if path == '/api/files' and not mutate:
            files = []
            for directory, folders, names in os.walk(service.project):
                folders[:] = [name for name in folders if not name.startswith('.') and name not in {'build', 'dist', '__pycache__', 'node_modules'}]
                for name in names:
                    candidate = Path(directory) / name
                    if name.endswith('.py') and candidate.resolve().is_relative_to(service.project):
                        files.append(candidate.relative_to(service.project).as_posix())
                        if len(files) >= 10000:
                            raise ValueError('Project has too many procedures; open a smaller project folder')
            return self.send(200, sorted(files))
        if path == '/api/run' and mutate:
            return self.send(200, service.start(token, data))
        if path == '/api/control' and mutate:
            return self.send(200, service.claim(token, data['id'], data.get('release', False)))
        if path == '/api/command' and mutate:
            return self.send(200, service.command(token, data['id'], data['command'], data.get('arguments', {})))
        if path == '/api/events' and not mutate:
            identifier = query['id'][0]
            with service.lock:
                if identifier not in service.runs:
                    raise KeyError(identifier)
                entries = service.records.events(identifier, after=int(query.get('after', ['0'])[0]),
                    path=query.get('path', [None])[0], line=int(query['line'][0]) if 'line' in query else None,
                    latest=query.get('latest', ['false'])[0] == 'true',
                    until=int(query['until'][0]) if 'until' in query else None)
            return self.send(200, entries)
        if path == '/api/record' and not mutate:
            return self.send(200, dict(schema='openbexi.as-run/1', snapshot=service.records.snapshot(query['id'][0])))
        self.send(404, {'error': 'Unknown workspace endpoint'})

    def handle_request(self, mutate):
        try:
            self.route(mutate)
        except PermissionError as error:
            self.close_connection = True; self.send(403, {'error': str(error)})
        except (KeyError, TypeError, ValueError, RuntimeError, TimeoutError, OSError) as error:
            self.close_connection = True; self.send(400, {'error': str(error) or type(error).__name__})

    def do_GET(self):
        self.handle_request(False)

    def do_POST(self):
        self.handle_request(True)


class ProcedureServer(BoundedHTTPServer):
    def __init__(self, address, service, *, tls_context=None, identities=None, public_host=None):
        if bool(tls_context) != bool(identities):
            raise ValueError('TLS requires explicit certificate identities')
        if address[0] not in {'127.0.0.1', 'localhost'} and not tls_context:
            raise ValueError('Remote procedure access requires mutual TLS and certificate identities')
        if public_host and any(character in public_host for character in '/\\@:#?'):
            raise ValueError('The public host must be a DNS name or IPv4 address')
        super().__init__(address, Handler)
        self.service = service; self.identities = identities
        self.scheme = 'https' if tls_context else 'http'
        self.authority = (public_host or address[0]) + ':' + str(self.server_port)
        if tls_context:
            self.socket = tls_context.wrap_socket(self.socket, server_side=True, do_handshake_on_connect=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--public-host')
    parser.add_argument('--tls-cert', type=Path)
    parser.add_argument('--tls-key', type=Path)
    parser.add_argument('--client-ca', type=Path)
    parser.add_argument('--identities', type=Path)
    args = parser.parse_args()
    tls_values = (args.tls_cert, args.tls_key, args.client_ca, args.identities)
    if any(tls_values) and not all(tls_values):
        parser.error('Remote access requires --tls-cert, --tls-key, --client-ca and --identities together')
    tls_context = identities = None
    if all(tls_values):
        from .session_identity import server_context, CertificateIdentities
        tls_context = server_context(args.tls_cert, args.tls_key, args.client_ca)
        identities = CertificateIdentities(args.identities)
    directory = args.directory or workspace_directory(args.project)
    directory.mkdir(parents=True, exist_ok=True)
    # Discovery alone is insufficient: hold ownership for the service's entire
    # lifetime, including direct CLI launches and endpoint publication.
    service_lock = open(directory / 'service.lock', 'a+b')
    if service_lock.tell() == 0:
        service_lock.write(b'0'); service_lock.flush()
    service_lock.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(service_lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(service_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        parser.error('A procedure service already owns this workspace directory')
    service = ProcedureService(args.project, directory)
    server = ProcedureServer((args.host, args.port), service, tls_context=tls_context,
                             identities=identities, public_host=args.public_host)
    endpoint = service.directory / 'endpoint.json'
    report = dict(url=server.scheme + '://' + server.authority, operator=service.operator_key,
                  monitor=service.monitor_key, project=str(service.project), pid=os.getpid(),
                  implementation=implementation_id())
    fd = os.open(endpoint, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as output:
        json.dump(report, output)
    def leases():
        while not service.closed:
            time.sleep(2); service.expire()
    threading.Thread(target=leases, daemon=True).start()
    try:
        server.serve_forever(poll_interval=.2)
    finally:
        service.close(); server.server_close()


if __name__ == '__main__':
    main()
