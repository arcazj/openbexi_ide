"""Two real HTTP clients share one real debugpy adapter and stopped state."""
import time
import threading
import subprocess
import sys

import pytest

from openbexi_runtime.cli import request
from openbexi_runtime.processes import process_alive
from test_sessions import serving, connect, claim, wait_for
from test_durable_sessions import git, commit, durable


def debug_call(url, actor, epoch, p, command, arguments=None, revision=None):
    return request(url, '/debug', {'epoch': epoch, 'procedure': p.id, 'command': command,
        'arguments': arguments or {}, 'revision': p.debug['revision'] if revision is None else revision}, actor['token'])


def stopped(p, line=None):
    return (p.status == 'PAUSED' and p.debug['stack_frames'] and p.debug['variables']
            and (line is None or p.debug['stack_frames'][0]['line'] == line))


def test_shared_real_breakpoint_inspection_edit_step_handoff_and_console(tmp_path):
    (tmp_path / 'main.py').write_text('def add(value):\n    shifted = value + 1\n    return shifted\n'
        'number = 7\nresult = add(number)\nprint("Result", result, flush=True)\n'
        'label = input("Name: ")\nprint("Hello", label, flush=True)\n')
    with serving(tmp_path) as (session, url):
        alice, bob = connect(session, url), connect(session, url, 'Bob')
        monitor = connect(session, url, 'Observer', monitor=True)
        epoch = claim(url, alice)
        row = request(url, '/run', {'epoch': epoch, 'script': 'main.py', 'debug': True,
            'stop_on_entry': False, 'breakpoints': {'main.py': [5]}}, alice['token'])
        p = session.procedures[row['id']]
        wait_for(lambda: stopped(p, 5) or p.error, 30)
        assert not p.error, p.error
        assert p.debug['all_threads_stopped'] and not p.has_token
        assert p.debug['breakpoints']['main.py'][0]['verified']
        frame = p.debug['stack_frames'][0]
        assert frame['source']['path'] == 'main.py'
        revision = p.debug['revision']
        snapshot = request(url, '/session', token=monitor['token'])
        cached = snapshot['procedures'][0]['debug']
        assert cached['stack_frames'] == p.debug['stack_frames']
        assert any(v['name'] == 'number' and v['value'] == '7' for values in cached['variables'].values() for v in values)
        for actor in (bob, monitor):
            with pytest.raises(ValueError, match='controller|read-only'):
                debug_call(url, actor, epoch, p, 'evaluate', {'frameId': frame['id'], 'expression': 'number'})
        evaluated = debug_call(url, alice, epoch, p, 'evaluate', {'frameId': frame['id'], 'expression': 'number + 1'})
        assert evaluated['body']['result'] == '8'
        request(url, '/handoff', {'epoch': epoch, 'target': bob['client']}, alice['token'])
        epoch2 = claim(url, bob)
        wait_for(lambda: stopped(p, 5), 10)
        with pytest.raises(ValueError, match='Stale debugger snapshot'):
            debug_call(url, bob, epoch2, p, 'setExpression', {'frameId': frame['id'], 'expression': 'number', 'value': '9'}, revision)
        with pytest.raises(ValueError, match='controller'):
            debug_call(url, alice, epoch, p, 'continue')
        reference = next(int(reference) for reference, values in p.debug['variables'].items()
                         if any(value['name'] == 'number' for value in values))
        debug_call(url, bob, epoch2, p, 'setVariable', {'variablesReference': reference, 'name': 'number', 'value': '8'})
        wait_for(lambda: stopped(p, 5))
        assert any(v['name'] == 'number' and v['value'] == '8' for values in p.debug['variables'].values() for v in values)
        frame = p.debug['stack_frames'][0]
        debug_call(url, bob, epoch2, p, 'setExpression', {'frameId': frame['id'], 'expression': 'number', 'value': '9'})
        wait_for(lambda: stopped(p, 5))
        assert any(v['name'] == 'number' and v['value'] == '9' for values in p.debug['variables'].values() for v in values)
        for command, line in [('stepIn', 2), ('stepOut', 5), ('next', 6), ('next', 7)]:
            previous = p.debug['revision']
            debug_call(url, bob, epoch2, p, command)
            wait_for(lambda: p.debug['revision'] > previous and stopped(p, line), 10)
        debug_call(url, bob, epoch2, p, 'continue')
        wait_for(lambda: any('Name:' in e.get('text', '') for e in session.events), 10)
        request(url, '/input', {'epoch': epoch2, 'procedure': p.id, 'text': 'visitor'}, bob['token'])
        wait_for(lambda: p.status in {'COMPLETED', 'FAILED'}, 15)
        assert p.status == 'COMPLETED', (p.error, p.exit_code)
        output = ''.join(e.get('text', '') for e in session.events)
        assert 'Result 10' in output and 'Hello visitor' in output
        assert p.debug['state'] == 'terminated' and not p.debug['stack_frames']


def test_shared_debug_rejects_unsupported_and_source_escapes(tmp_path):
    (tmp_path / 'main.py').write_text('pass\n')
    with serving(tmp_path) as (session, url):
        alice = connect(session, url)
        epoch = claim(url, alice)
        for fields, pattern in [({'language': 'spell'}, 'unavailable'),
                                ({'breakpoints': {'../escape.py': [1]}}, 'inside'),
                                ({'breakpoints': {'main.py': [True]}}, 'integers')]:
            with pytest.raises(ValueError, match=pattern):
                request(url, '/run', {'epoch': epoch, 'script': 'main.py', 'debug': True, **fields}, alice['token'])
        assert not session.procedures


@pytest.mark.parametrize('loss', ['handoff', 'disconnect', 'expiry'])
def test_running_debugger_pauses_on_control_loss_and_never_silently_resumes(tmp_path, loss):
    marker = tmp_path / 'effects.txt'
    (tmp_path / 'main.py').write_text('from pathlib import Path\nimport time\n'
        'while True:\n    with Path("effects.txt").open("a") as stream:\n'
        '        stream.write("effect\\n")\n    time.sleep(0.015)\n')
    with serving(tmp_path, lease_seconds=30) as (session, url):
        alice, bob = connect(session, url), connect(session, url, 'Bob')
        epoch = claim(url, alice)
        row = request(url, '/run', {'epoch': epoch, 'script': 'main.py', 'debug': True,
                                  'stop_on_entry': False}, alice['token'])
        p = session.procedures[row['id']]
        wait_for(lambda: marker.exists() and marker.stat().st_size > 10, 30)
        pids = p.owner.process_ids() | p.debugger.adapter_owner.process_ids()
        if loss == 'handoff':
            request(url, '/handoff', {'epoch': epoch, 'target': bob['client']}, alice['token'])
        elif loss == 'disconnect':
            request(url, '/disconnect', {}, alice['token'])
        else:
            with session.lock:
                session.deadline = time.monotonic() - 1
        wait_for(lambda: stopped(p), 15)
        first = marker.read_text()
        time.sleep(0.15)
        assert marker.read_text() == first
        assert not p.has_token and p.debug['all_threads_stopped']
        next_epoch = claim(url, bob)
        time.sleep(0.15)
        assert marker.read_text() == first
        debug_call(url, bob, next_epoch, p, 'continue')
        wait_for(lambda: marker.read_text() != first, 10)
        request(url, '/stop', {'epoch': next_epoch, 'procedure': p.id}, bob['token'])
        wait_for(lambda: p.status == 'CANCELLED', 10)
        wait_for(lambda: all(not process_alive(pid) for pid in pids), 10)


def test_debug_pause_waits_for_owned_child_before_reusing_slot(tmp_path):
    (tmp_path / 'main.py').write_text('import subprocess,sys,time\n'
        'child=subprocess.Popen([sys.executable,"-I","-c","import time;time.sleep(1.5)"])\n'
        'while True:\n    time.sleep(0.01)\n')
    (tmp_path / 'queued.py').write_text('from pathlib import Path\nPath("queued-effect").write_text("ran")\n')
    with serving(tmp_path) as (session, url):
        alice = connect(session, url)
        epoch = claim(url, alice)
        first = request(url, '/run', {'epoch': epoch, 'script': 'main.py', 'debug': True,
                                     'stop_on_entry': False}, alice['token'])
        p = session.procedures[first['id']]
        wait_for(lambda: p.bootstrap_pids and p.owner.process_ids() - p.bootstrap_pids, 30)
        second = request(url, '/run', {'epoch': epoch, 'script': 'queued.py', 'debug': True}, alice['token'])
        queued = session.procedures[second['id']]
        assert queued.status == 'PAUSED' and queued.process is None
        request(url, '/pause', {'epoch': epoch, 'procedure': p.id}, alice['token'])
        wait_for(lambda: p.debug['all_threads_stopped'], 10)
        assert p.status == 'PAUSING' and p.has_token and queued.process is None
        wait_for(lambda: stopped(p) and stopped(queued), 30)
        assert not (tmp_path / 'queued-effect').exists()
        assert sum(proc.has_token for proc in session.procedures.values()) == 0
        request(url, '/stop', {'epoch': epoch, 'procedure': p.id}, alice['token'])
        debug_call(url, alice, epoch, queued, 'continue')
        wait_for(lambda: queued.status == 'COMPLETED', 10)
        assert (tmp_path / 'queued-effect').read_text() == 'ran'


def test_evaluation_retains_slot_until_actual_completion_across_handoff(tmp_path):
    (tmp_path / 'main.py').write_text('number = 7\nprint(number)\n')
    (tmp_path / 'queued.py').write_text('print("QUEUED")\n')
    with serving(tmp_path) as (session, url):
        alice, bob = connect(session, url), connect(session, url, 'Bob')
        epoch = claim(url, alice)
        row = request(url, '/run', {'epoch': epoch, 'script': 'main.py', 'debug': True,
            'stop_on_entry': False, 'breakpoints': {'main.py': [2]}}, alice['token'])
        p = session.procedures[row['id']]
        wait_for(lambda: stopped(p, 2), 30)
        errors = []
        def evaluate():
            try:
                debug_call(url, alice, epoch, p, 'evaluate', {'frameId': p.debug['stack_frames'][0]['id'],
                    'expression': '(__import__("time").sleep(1.0), number)[1]'})
            except ValueError as error:
                errors.append(str(error))
        caller = threading.Thread(target=evaluate)
        caller.start()
        wait_for(lambda: p.debug['state'] == 'evaluating')
        row2 = request(url, '/run', {'epoch': epoch, 'script': 'queued.py', 'debug': True}, alice['token'])
        queued = session.procedures[row2['id']]
        request(url, '/handoff', {'epoch': epoch, 'target': bob['client']}, alice['token'])
        epoch2 = claim(url, bob)
        assert p.status == 'PAUSING' and p.has_token and not p.debug['all_threads_stopped']
        assert queued.process is None
        with pytest.raises(ValueError, match='stopped'):
            debug_call(url, bob, epoch2, p, 'continue')
        caller.join(timeout=5)
        assert errors and 'controller' in errors[0]
        wait_for(lambda: stopped(p, 2), 10)
        assert not p.has_token and queued.process is None
        request(url, '/resume', {'epoch': epoch2, 'procedure': queued.id}, bob['token'])
        wait_for(lambda: stopped(queued), 30)


def test_real_threads_share_pause_and_queued_continue_preserves_slots(tmp_path):
    (tmp_path / 'main.py').write_text('import threading,time\n'
        'def worker():\n    value = 17\n    print("worker",value,flush=True)\n'
        'thread=threading.Thread(target=worker,name="calculation")\n'
        'thread.start()\nthread.join()\nprint("joined",flush=True)\n')
    (tmp_path / 'occupied.py').write_text('import time\nprint("occupied",flush=True)\ntime.sleep(1)\n')
    with serving(tmp_path) as (session, url):
        alice = connect(session, url)
        epoch = claim(url, alice)
        row = request(url, '/run', {'epoch': epoch, 'script': 'main.py', 'debug': True,
            'stop_on_entry': False, 'breakpoints': {'main.py': [4]}}, alice['token'])
        p = session.procedures[row['id']]
        wait_for(lambda: stopped(p, 4), 30)
        assert any(item['name'] == 'calculation' for item in p.debug['threads'])
        row2 = request(url, '/run', {'epoch': epoch, 'script': 'occupied.py'}, alice['token'])
        occupied = session.procedures[row2['id']]
        wait_for(lambda: occupied.status == 'RUNNING')
        frame = p.debug['stack_frames'][0]
        with pytest.raises(ValueError, match='execution slot'):
            debug_call(url, alice, epoch, p, 'evaluate', {'frameId': frame['id'], 'expression': 'value'})
        debug_call(url, alice, epoch, p, 'continue')
        assert p.status == 'PAUSED' and p.reason == 'WAITING_TOKEN' and not p.has_token
        assert not any('worker 17' in event.get('text', '') for event in session.events)
        wait_for(lambda: p.status == 'COMPLETED', 15)
        assert occupied.status == 'COMPLETED'
        assert any('joined' in event.get('text', '') for event in session.events)


def test_captured_sources_and_queued_debug_options_survive_restart(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    git(project, 'init', '-q')
    (project / 'main.py').write_text('from dependency import value\nprint(value, flush=True)\n')
    (project / 'dependency.py').write_text('value = "captured value"\n')
    (project / 'occupied.py').write_text('import time\nwhile True:\n    time.sleep(0.01)\n')
    commit(project)
    state = tmp_path / 'authority'
    with durable(project, state) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        request(url, '/run', {'epoch': epoch, 'script': 'occupied.py'}, actor['token'])
        row = request(url, '/run', {'epoch': epoch, 'script': 'main.py', 'debug': True,
            'stop_on_entry': False, 'breakpoints': {'main.py': [2]}}, actor['token'])
        assert session.procedures[row['id']].process is None
    (project / 'dependency.py').write_text('value = "changed live value"\n')
    with durable(project, state) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        p = session.procedures[row['id']]
        assert p.status == 'PAUSED' and p.debug['state'] == 'queued'
        assert p.debug_initial_breakpoints == {'main.py': [2]}
        assert not p.stop_on_entry
        request(url, '/configure', {'epoch': epoch, 'max_parallel': 2}, actor['token'])
        request(url, '/resume', {'epoch': epoch, 'procedure': p.id}, actor['token'])
        wait_for(lambda: stopped(p, 2) or p.error, 30)
        assert not p.error, p.error
        assert p.debug['stack_frames'][0]['source']['path'] == 'main.py'
        assert any(v['name'] == 'value' and v['value'] == "'captured value'"
                   for values in p.debug['variables'].values() for v in values)
        debug_call(url, actor, epoch, p, 'setBreakpoints',
                   {'source': {'path': 'main.py'}, 'breakpoints': []})
        assert p.debug['breakpoints']['main.py'] == []
        debug_call(url, actor, epoch, p, 'continue')
        wait_for(lambda: p.status == 'COMPLETED', 15)
        output = ''.join(e.get('text', '') for e in session.events if e.get('procedure') == p.id)
        assert 'captured value' in output and 'changed live value' not in output


def test_control_loss_during_bootstrap_keeps_user_code_untouched(tmp_path):
    (tmp_path / 'main.py').write_text('from pathlib import Path\nPath("effect").write_text("ran")\n')
    with serving(tmp_path) as (session, url):
        actor, bob = connect(session, url), connect(session, url, 'Bob')
        epoch = claim(url, actor)
        row = request(url, '/run', {'epoch': epoch, 'script': 'main.py', 'debug': True,
                                  'stop_on_entry': False}, actor['token'])
        p = session.procedures[row['id']]
        request(url, '/handoff', {'epoch': epoch, 'target': bob['client']}, actor['token'])
        wait_for(lambda: stopped(p, 1) or (p.process is None and p.status == 'PAUSED'), 30)
        assert not (tmp_path / 'effect').exists()
        epoch2 = claim(url, bob)
        request(url, '/resume', {'epoch': epoch2, 'procedure': p.id}, bob['token'])
        wait_for(lambda: p.status == 'COMPLETED', 15)
        assert (tmp_path / 'effect').read_text() == 'ran'


def test_service_shutdown_during_debugger_startup_reaps_owned_processes(tmp_path):
    (tmp_path / 'main.py').write_text('raise RuntimeError("must never run")\n')
    with serving(tmp_path) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        row = request(url, '/run', {'epoch': epoch, 'script': 'main.py', 'debug': True}, actor['token'])
        p = session.procedures[row['id']]
        wait_for(lambda: p.debugger and p.debugger.adapter, 5)
        adapter_pid = p.debugger.adapter.pid
    assert not process_alive(adapter_pid)


def test_missing_debugpy_is_reported_before_worker_admission(tmp_path):
    environment = tmp_path / 'bare-runtime'
    subprocess.run([sys.executable, '-I', '-m', 'venv', '--without-pip', str(environment)], check=True, timeout=20)
    interpreter = environment / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    (tmp_path / 'main.py').write_text('print("must not start")\n')
    with serving(tmp_path, interpreter=interpreter) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        assert not session.snapshot()['debug_capabilities']['python']['available']
        with pytest.raises(ValueError, match='requires debugpy 1.8.22'):
            request(url, '/run', {'epoch': epoch, 'script': 'main.py', 'debug': True}, actor['token'])
        assert not session.procedures


def test_exception_snapshot_and_adapter_failure_are_real_and_recoverable(tmp_path):
    (tmp_path / 'main.py').write_text('value = 42\nraise ValueError("inspect this failure")\n')
    (tmp_path / 'next.py').write_text('print("new debug session")\n')
    with serving(tmp_path) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        row = request(url, '/run', {'epoch': epoch, 'script': 'main.py', 'debug': True,
                                  'stop_on_entry': False}, actor['token'])
        p = session.procedures[row['id']]
        wait_for(lambda: stopped(p, 2), 30)
        assert p.debug['reason'] == 'exception'
        result = debug_call(url, actor, epoch, p, 'exceptionInfo', {'threadId': p.debug['thread_id']})
        assert 'ValueError' in result['body']['exceptionId']
        assert 'inspect this failure' in result['body']['description']
        debug_call(url, actor, epoch, p, 'continue')
        wait_for(lambda: p.status == 'FAILED', 15)
        assert p.exit_code == 1
        row = request(url, '/run', {'epoch': epoch, 'script': 'next.py', 'debug': True}, actor['token'])
        p = session.procedures[row['id']]
        wait_for(lambda: stopped(p), 30)
        pids = p.owner.process_ids() | p.debugger.adapter_owner.process_ids()
        p.debugger.adapter.kill()
        wait_for(lambda: p.status == 'FAILED', 15)
        assert p.error == 'Debugger adapter disconnected before reporting an exit status'
        assert p.debug['state'] == 'terminated' and not p.has_token
        assert all(not process_alive(pid) for pid in pids)


def test_async_desktop_client_debug_result_keeps_request_identity(app, tmp_path):
    from openbexi_ide.session_client import SessionClient
    (tmp_path / 'main.py').write_text('number = 7\nprint(number)\n')
    def spin(predicate, timeout=20):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            app.processEvents()
            # Let the real in-process HTTP/DAP server's Python threads run.
            time.sleep(0.01)
        assert predicate()
    with serving(tmp_path) as (session, url):
        client = SessionClient()
        errors, results = [], []
        client.error.connect(errors.append)
        client.debug_result.connect(results.append)
        try:
            assert client.join(user='Alice', url=url, invite=session.developer_invite)
            spin(lambda: client.can_claim)
            assert client.command('claim')
            spin(lambda: client.can_control)
            assert client.submit('main.py', debug=True, stop_on_entry=False, breakpoints={'main.py': [2]})
            spin(lambda: bool(client.snapshot.get('procedures')) and
                 client.snapshot['procedures'][0].get('debug', {}).get('variables'))
            row = client.snapshot['procedures'][0]
            frame = row['debug']['stack_frames'][0]
            revision = row['debug']['revision']
            arguments = {'frameId': frame['id'], 'expression': 'number + 1'}
            spin(lambda: client.can_control)
            assert client.debug_command(row['id'], 'evaluate', arguments, revision)
            # The request runs on the session HTTP worker, never the GUI thread.
            spin(lambda: bool(results))
            result = results[-1]
            assert result['procedure'] == row['id'] and result['command'] == 'evaluate'
            assert result['arguments'] == arguments and result['revision'] == revision
            assert result['epoch'] == client.epoch and result['body']['result'] == '8'
            assert result['debug']['revision'] > revision
            assert not errors, errors
        finally:
            client.disconnect()
            spin(lambda: not client.active)
