"""Owned debugpy DAP transport and shared, revision-fenced debugger state.

The service is the sole DAP client. Session peers read cached observations and
the current controller alone can ask the service to send debugger requests.
"""
from __future__ import annotations

from concurrent.futures import Future, TimeoutError
import copy
import hashlib
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

from .dap import MessageReader, encode_message
from .launch import clean_environment, console_interpreter
from .processes import process_alive, start_owned_process


CONTROL = frozenset({'continue', 'next', 'stepIn', 'stepOut'})
READ = frozenset({'threads', 'stackTrace', 'scopes', 'variables', 'exceptionInfo'})
COMMANDS = CONTROL | READ | {'pause', 'setBreakpoints', 'evaluate', 'setVariable', 'setExpression'}


def initial_state(breakpoints=None):
    return {'enabled': True, 'backend': 'debugpy', 'state': 'queued', 'reason': 'WAITING_TOKEN',
            'revision': 0, 'thread_id': None, 'all_threads_stopped': False,
            'threads': [], 'stack_frames': [], 'stacks': {}, 'scopes': {}, 'variables': {},
            'breakpoints': copy.deepcopy(breakpoints or {}), 'capabilities': {}, 'error': None}


def source_path(project, name):
    if not isinstance(name, str) or not name or '\0' in name or Path(name).is_absolute():
        raise ValueError('Debugger sources must be project-relative paths')
    root = Path(project).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() != '.py':
        raise ValueError('Debugger source must be a Python file inside the captured project')
    return path


def validate_breakpoints(project, values):
    if type(values) is not dict or len(values) > 128:
        raise ValueError('Invalid shared breakpoint mapping')
    result = {}
    for name, lines in values.items():
        path = source_path(project, name)
        if (type(lines) is not list or len(lines) > 512
                or any(type(line) is not int or not 1 <= line <= 10_000_000 for line in lines)):
            raise ValueError('Breakpoint lines must be positive integers')
        result[path.relative_to(Path(project).resolve()).as_posix()] = sorted(set(lines))
    return result


class SharedDebugger:
    def __init__(self, session, procedure):
        self.session, self.p = session, procedure
        self.adapter = self.adapter_owner = None
        self.pending, self.sequence = {}, 0
        self.io_lock = threading.RLock()
        self.events = queue.Queue()
        self.initialized, self.done = threading.Event(), threading.Event()
        self.start_epoch = session.epoch
        self.first_stop = True
        self.evaluating = False
        self.error = None
        self.pumps = []
        self.known_pids = set()

    def send(self, command, arguments=None):
        future = Future()
        with self.io_lock:
            if not self.adapter or self.adapter.poll() is not None:
                raise ValueError('Debugger adapter is unavailable')
            self.sequence += 1
            seq = self.sequence
            self.pending[seq] = future
            try:
                self.adapter.stdin.write(encode_message({'seq': seq, 'type': 'request',
                    'command': command, 'arguments': arguments or {}}))
                self.adapter.stdin.flush()
            except (OSError, ValueError):
                self.pending.pop(seq, None)
                raise
        return future

    @staticmethod
    def result(future, timeout=4):
        try:
            return future.result(timeout)
        except TimeoutError as error:
            raise ValueError('Debugger request timed out') from error

    def ask(self, command, arguments=None):
        return self.result(self.send(command, arguments))

    def reply(self, message, success=True, body=None, error=None):
        with self.io_lock:
            self.sequence += 1
            self.adapter.stdin.write(encode_message({'seq': self.sequence, 'type': 'response',
                'request_seq': message['seq'], 'command': message['command'], 'success': success,
                'body': body or {}, 'message': error or ''}))
            self.adapter.stdin.flush()

    def _read(self):
        reader = MessageReader()
        try:
            while raw := self.adapter.stdout.read1(65536):
                for message in reader.feed(raw):
                    if message['type'] == 'response':
                        with self.io_lock:
                            future = self.pending.pop(message.get('request_seq'), None)
                        if future:
                            if message.get('success'):
                                future.set_result(message.get('body', {}))
                            else:
                                future.set_exception(ValueError(message.get('message', 'Debugger rejected request')))
                    else:
                        self.events.put(message)
        except (ValueError, OSError) as error:
            self.error = str(error)
        finally:
            with self.io_lock:
                pending = list(self.pending.values())
                self.pending.clear()
            for future in pending:
                future.set_exception(ValueError('Debugger adapter disconnected'))
            self.done.set()

    def _events(self):
        while not self.done.is_set():
            try:
                message = self.events.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                if message['type'] == 'request':
                    if message.get('command') == 'runInTerminal':
                        self._terminal(message)
                    else:
                        self.reply(message, False, error='Reverse request unsupported')
                    continue
                body, event = message.get('body', {}), message.get('event')
                if event == 'initialized':
                    self.initialized.set()
                elif event == 'output' and body.get('category') != 'telemetry':
                    self.session.event('output', procedure=self.p.id, stream=body.get('category', 'console'),
                                       text=body.get('output', ''))
                elif event == 'stopped':
                    self._stopped(body)
                elif event == 'continued':
                    with self.session.lock:
                        # A response/event arriving after fencing must never
                        # turn a paused request into an authorized run.
                        if not self.p.wants_run or self.session.controller is None:
                            self.pause()
                elif event == 'exited':
                    self.p.exit_code = body.get('exitCode', 1)
                elif event == 'terminated':
                    self.done.set()
            except (ValueError, OSError, KeyError) as error:
                self.error = str(error)
                self.done.set()

    def _terminal(self, message):
        args = message.get('arguments', {})
        command = args.get('args')
        p, session = self.p, self.session
        if (not isinstance(command, list) or len(command) < 2
                or any(not isinstance(arg, str) or '\0' in arg for arg in command)
                or console_interpreter(command[0]) != p.spec.interpreter
                or args.get('argsCanBeInterpretedByShell') or p.process is not None):
            self.reply(message, False, error='Invalid integrated-console launch')
            raise ValueError('Debugger requested an invalid console launch')
        environment = clean_environment()
        for key, value in (args.get('env') or {}).items():
            if value is None:
                environment.pop(key, None)
            else:
                environment[key] = value
        with session.lock:
            if p.cancelled or session.closed.is_set():
                raise ValueError('Debug launch was cancelled')
            p.process, p.owner = start_owned_process(command, cwd=p.spec.project, env=environment,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            session.event('started', procedure=p.id, pid=p.process.pid, debugger='debugpy')
        for stream, name in ((p.process.stdout, 'stdout'), (p.process.stderr, 'stderr')):
            thread = threading.Thread(target=session._pump, args=(p.id, stream, name), daemon=True)
            thread.start()
            self.pumps.append(thread)
        writer = threading.Thread(target=session._input_pump, args=(p,), daemon=True)
        writer.start()
        self.pumps.append(writer)
        self.reply(message, body={'processId': p.process.pid})

    def invalidate(self, state=None):
        debug = self.p.debug
        debug['revision'] += 1
        debug.update(stack_frames=[], stacks={}, scopes={}, variables={})
        if state is not None:
            debug['state'] = state
        return debug['revision']

    def _stopped(self, body):
        session, p = self.session, self.p
        with session.lock:
            session._expire()
            first, self.first_stop = self.first_stop, False
            if first:
                p.bootstrap_pids = p.owner.process_ids() if p.owner else None
                self.known_pids.update(p.bootstrap_pids or ())
            self.invalidate('paused')
            p.debug.update(reason=body.get('reason'), thread_id=body.get('threadId'),
                           all_threads_stopped=body.get('allThreadsStopped') is True)
            if first and not p.stop_on_entry and p.wants_run and session.controller and session.epoch == self.start_epoch:
                self.resume('continue', {'threadId': body['threadId']})
                return
            p.wants_run = False
            p.reason = p.reason or 'DEBUG_' + str(body.get('reason', 'STOPPED')).upper()
            p.status = 'PAUSING'
            self.confirm_pause()
            revision = p.debug['revision']
            session.event('debug_stopped', procedure=p.id, reason=p.debug['reason'], revision=revision)
        self.refresh(revision)

    def confirm_pause(self):
        p, session = self.p, self.session
        if p.status != 'PAUSING' or not p.debug['all_threads_stopped']:
            return
        live = p.owner.process_ids() if p.owner else None
        if live is not None and p.bootstrap_pids is not None and live.issubset(p.bootstrap_pids):
            p.status, p.has_token = 'PAUSED', False
            session.event('paused', procedure=p.id, reason=p.reason)
            session._dispatch()

    def pause(self):
        p = self.p
        revision = self.invalidate('pausing' if p.debug['state'] != 'paused' else 'paused')
        if p.debug['all_threads_stopped']:
            self.confirm_pause()
            threading.Thread(target=self.refresh, args=(revision,), daemon=True).start()
        elif self.adapter and not self.first_stop and not self.evaluating:
            # DAP pause is asynchronous. Keep the slot until a stopped event
            # confirms all threads and the child-process inventory settles.
            try:
                self.send('pause', {'threadId': p.debug['thread_id'] or 1})
            except (ValueError, OSError) as error:
                self.error = str(error)
                self.done.set()

    def finish_evaluation(self):
        """A completed DAP response proves the stopped-thread evaluation ended."""
        with self.session.lock:
            self.evaluating = False
            p = self.p
            if p.status in {'STOPPING', 'COMPLETED', 'FAILED', 'CANCELLED', 'RECOVERY_REQUIRED'}:
                return
            p.debug['state'], p.debug['all_threads_stopped'] = 'paused', True
            p.status, p.wants_run = 'PAUSING', False
            self.confirm_pause()
            if p.debug['revision']:
                threading.Thread(target=self.refresh, args=(p.debug['revision'],), daemon=True).start()

    def resume(self, command='continue', arguments=None):
        self.invalidate('running')
        self.p.debug['all_threads_stopped'] = False
        self.p.debug['reason'] = None
        self.p.status, self.p.reason, self.p.wants_run = 'RUNNING', None, True
        future = self.send(command, arguments or {'threadId': self.p.debug['thread_id']})
        def failed(result):
            if result.exception():
                self.error = str(result.exception())
                self.done.set()
        future.add_done_callback(failed)
        return future

    def relative(self, value):
        """Map adapter source paths back to project names, retaining other data."""
        if isinstance(value, list):
            return [self.relative(item) for item in value]
        if isinstance(value, dict):
            result = {key: self.relative(item) for key, item in value.items()}
            if isinstance(result.get('path'), str):
                path = Path(result['path']).resolve()
                if path.is_relative_to(self.p.spec.project):
                    result['path'] = path.relative_to(self.p.spec.project).as_posix()
            return result
        return value

    def cache(self, command, arguments, body):
        debug = self.p.debug
        body = self.relative(body)
        if command == 'threads':
            debug['threads'] = body.get('threads', [])
        elif command == 'stackTrace':
            frames = body.get('stackFrames', [])
            debug['stacks'][str(arguments['threadId'])] = frames
            debug['stack_frames'] = frames
        elif command == 'scopes':
            debug['scopes'][str(arguments['frameId'])] = body.get('scopes', [])
        elif command == 'variables':
            debug['variables'][str(arguments['variablesReference'])] = body.get('variables', [])
        elif command == 'setBreakpoints':
            name = Path(arguments['source']['path']).relative_to(self.p.spec.project).as_posix()
            debug['breakpoints'][name] = body.get('breakpoints', [])
        return body

    def refresh(self, revision):
        def fetch(command, arguments=None):
            arguments = arguments or {}
            with self.session.lock:
                if self.p.debug['revision'] != revision or self.p.debug['state'] != 'paused':
                    return None
                future = self.send(command, arguments)
            body = self.result(future)
            with self.session.lock:
                if self.p.debug['revision'] != revision or self.p.debug['state'] != 'paused':
                    return None
                return self.cache(command, arguments, body)
        try:
            threads = fetch('threads')
            if threads is None:
                return
            for thread in threads.get('threads', [])[:32]:
                stack = fetch('stackTrace', {'threadId': thread['id'], 'startFrame': 0, 'levels': 32})
                if stack is None:
                    return
                # Automatic views use standard DAP scopes/variables; they never
                # send evaluate. Rendering remains debugpy's responsibility.
                for frame in stack.get('stackFrames', [])[:1]:
                    scopes = fetch('scopes', {'frameId': frame['id']})
                    if scopes is None:
                        return
                    for scope in scopes.get('scopes', [])[:3]:
                        if not scope.get('expensive'):
                            fetch('variables', {'variablesReference': scope['variablesReference'], 'start': 0, 'count': 64})
            with self.session.lock:
                if self.p.debug['revision'] == revision:
                    selected = self.p.debug['stacks'].get(str(self.p.debug['thread_id']))
                    if selected is not None:
                        self.p.debug['stack_frames'] = selected
                    self.session.event('debug_snapshot', procedure=self.p.id, revision=revision)
        except (ValueError, OSError):
            # Resuming or ending a session can invalidate an in-flight view.
            pass

    def run(self):
        p, session = self.p, self.session
        try:
            with session.lock:
                if not p.has_token or session.closed.is_set():
                    return
                if p.capture_digest:
                    from .source_capture import verify_capture
                    verify_capture(p.spec.project, p.capture_digest)
                if hashlib.sha256(p.spec.script.read_bytes()).hexdigest() != p.source_hash:
                    raise ValueError('Procedure changed after submission')
                self.adapter, self.adapter_owner = start_owned_process(
                    [str(p.spec.interpreter), '-I', '-B', '-X', 'utf8', '-m', 'debugpy.adapter'],
                    cwd=p.spec.project, env=clean_environment(), stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                p.debug['state'] = 'starting'
            for target in (self._read, self._events):
                threading.Thread(target=target, daemon=True).start()
            errors = threading.Thread(target=session._pump, args=(p.id, self.adapter.stderr, 'debugger'), daemon=True)
            errors.start()
            self.pumps.append(errors)
            capabilities = self.ask('initialize', {'clientID': 'openbexi-shared', 'adapterID': 'python',
                'linesStartAt1': True, 'columnsStartAt1': True, 'pathFormat': 'path',
                'supportsRunInTerminalRequest': True, 'supportsVariableType': True,
                'supportsVariablePaging': True, 'supportsArgsCanBeInterpretedByShell': False})
            with session.lock:
                supported = {'supportsSetVariable', 'supportsSetExpression', 'supportsExceptionInfoRequest',
                             'supportsEvaluateForHovers', 'supportsVariableType', 'supportsVariablePaging'}
                p.debug['capabilities'] = {name: value for name, value in capabilities.items() if name in supported}
                p.debug['capabilities']['commands'] = sorted(COMMANDS)
            launch = self.send('launch', {'name': p.script, 'type': 'python', 'request': 'launch',
                'program': p.spec.worker_arguments()[0], 'args': p.spec.worker_arguments()[1:],
                'cwd': str(p.spec.project),
                'python': str(p.spec.interpreter), 'pythonArgs': ['-I', '-B', '-u', '-X', 'utf8'],
                'console': 'integratedTerminal', 'redirectOutput': False, 'justMyCode': True,
                'subProcess': False, 'stopOnEntry': True,
                'rules': [{'path': str(Path(__file__).with_name('worker.py')), 'include': False}]})
            deadline = time.monotonic() + 20
            while not self.initialized.wait(0.05):
                if self.done.is_set() or p.cancelled or session.closed.is_set():
                    raise ValueError('Debugger initialization was cancelled')
                if time.monotonic() >= deadline:
                    raise ValueError('Debugger initialization timed out')
            for name, lines in p.debug_initial_breakpoints.items():
                arguments = {'source': {'path': str(source_path(p.spec.project, name))},
                             'breakpoints': [{'line': line} for line in lines]}
                body = self.ask('setBreakpoints', arguments)
                with session.lock:
                    self.cache('setBreakpoints', arguments, body)
            self.ask('setExceptionBreakpoints', {'filters': ['uncaught']})
            self.ask('configurationDone')
            self.result(launch, 20)
            while not self.done.wait(0.05):
                with session.lock:
                    self.known_pids.update(p.owner.process_ids() or () if p.owner else ())
                    session._expire()
                    if p.cancelled or session.closed.is_set():
                        break
                    self.confirm_pause()
            if self.error:
                raise ValueError(self.error)
            if p.exit_code is None and not p.cancelled and not session.closed.is_set():
                raise ValueError('Debugger adapter disconnected before reporting an exit status')
        except BaseException as error:
            p.error = str(error)
        finally:
            self.done.set()
            for owner in (p.owner, self.adapter_owner):
                if owner:
                    self.known_pids.update(owner.process_ids() or ())
            if p.owner:
                p.owner.close()
            if self.adapter_owner:
                self.adapter_owner.close()
            for process in (p.process, self.adapter):
                if process:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=5)
            deadline = time.monotonic() + 3
            while any(process_alive(pid) for pid in self.known_pids) and time.monotonic() < deadline:
                time.sleep(0.02)
            cleanup_pending = any(process_alive(pid) for pid in self.known_pids)
            try:
                p.input_queue.put_nowait(None)
            except queue.Full:
                pass
            for thread in self.pumps:
                thread.join(timeout=2)
            for process in (p.process, self.adapter):
                if process:
                    for stream in (process.stdin, process.stdout, process.stderr):
                        if stream and not stream.closed:
                            try:
                                stream.close()
                            except OSError:
                                stream.raw.close()
            with session.lock:
                # No adapter/debuggee admission took place if the grant was
                # revoked before this worker thread acquired the session lock.
                if self.adapter is not None or p.error:
                    p.status = 'CANCELLED' if p.cancelled else 'FAILED' if p.error or p.exit_code != 0 else 'COMPLETED'
                    p.has_token, p.wants_run = False, False
                    self.invalidate('terminated')
                    p.debug['error'] = p.error
                    if session.store and p.status != 'COMPLETED':
                        p.uncertain = True
                        p.status, p.reason = 'RECOVERY_REQUIRED', 'UNCERTAIN_EFFECTS'
                    if cleanup_pending:
                        p.error = 'Debugger process shutdown is unconfirmed'
                        p.debug['error'] = p.error
                        p.uncertain, p.has_token = True, True
                        p.status, p.reason = 'RECOVERY_REQUIRED', 'UNCONFIRMED_SHUTDOWN'
                    session.event('finished', procedure=p.id, status=p.status, exit_code=p.exit_code)
                session._dispatch()
