from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from openbexi_runtime.cli import request
from openbexi_runtime.processes import process_alive
from openbexi_runtime.session import Session, SessionError
from openbexi_runtime.session_http import SessionServer


@contextmanager
def serving(project, **options):
    session = Session(project, **options)
    server = SessionServer(('127.0.0.1', 0), session)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield session, session.worker_url
    finally:
        session.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def connect(session, url, name='Alice', monitor=False):
    return request(url, '/connect', {'name': name, 'invite': session.monitor_invite if monitor else session.developer_invite})


def claim(url, actor):
    return request(url, '/claim', {}, actor['token'])['epoch']


def wait_for(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.025)
    raise AssertionError('Session condition did not arrive')


def script(project, name, body=None):
    target = project / name
    target.write_text(body or "import time\ndef inner():\n    for number in range(500):\n        print(number, flush=True)\n        time.sleep(0.02)\ndef outer():\n    inner()\nouter()\n", encoding='utf-8')
    return name


def submit(url, actor, epoch, name):
    return request(url, '/run', {'epoch': epoch, 'script': name}, actor['token'])['id']


def test_authentication_monitor_role_real_stacks_and_no_credentials_in_snapshot(tmp_path):
    script(tmp_path, 'one.py')
    with serving(tmp_path) as (session, url):
        with pytest.raises(ValueError, match='credential'):
            request(url, '/session')
        with pytest.raises(ValueError, match='Invalid invitation'):
            request(url, '/connect', {'name': 'Fake', 'invite': 'invalid'})
        alice, bob, monitor = connect(session, url), connect(session, url, 'Bob'), connect(session, url, 'Reader', True)
        epoch = claim(url, alice)
        with pytest.raises(ValueError, match='read-only'):
            claim(url, monitor)
        with pytest.raises(ValueError, match='Another developer'):
            claim(url, bob)
        identifier = submit(url, alice, epoch, 'one.py')
        procedure = session.procedures[identifier]
        wait_for(lambda: procedure.status == 'RUNNING' and any(t['stack'] for t in procedure.stacks.values()))
        status = request(url, '/session', token=monitor['token'])
        functions = {f['function'] for t in status['procedures'][0]['threads'] for f in t['stack']}
        wait_for(lambda: any('inner' in [f['function'] for f in t['stack']] for t in procedure.stacks.values()))
        assert status['controller']['id'] == alice['client']
        wire = json.dumps(status)
        assert session.developer_invite not in wire and alice['token'] not in wire and procedure.secret not in wire
        with pytest.raises(ValueError, match='read-only'):
            request(url, '/stop', {'epoch': epoch, 'procedure': identifier}, monitor['token'])
        with pytest.raises(ValueError, match='Stale'):
            request(url, '/stop', {'epoch': epoch, 'procedure': identifier}, bob['token'])
        with pytest.raises(ValueError, match='Worker credential'):
            request(url, '/worker/checkpoint', {'id': identifier, 'token': 'bad'})


def test_controller_claim_is_atomic_with_concurrent_developers(tmp_path):
    with serving(tmp_path) as (session, url):
        actors = [session.authenticate(connect(session, url, str(i))['token']) for i in range(8)]
        gate, winners = threading.Barrier(8), []
        def compete(actor):
            gate.wait()
            try:
                session.claim(actor)
                winners.append(actor['id'])
            except SessionError:
                pass
        threads = [threading.Thread(target=compete, args=(actor,)) for actor in actors]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
        assert len(winners) == 1 and session.controller == winners[0]


def test_serial_fifo_pause_releases_slot_only_after_ack_then_resume(tmp_path):
    script(tmp_path, 'first.py')
    script(tmp_path, 'second.py')
    with serving(tmp_path, max_parallel=1) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        first_id, second_id = submit(url, actor, epoch, 'first.py'), submit(url, actor, epoch, 'second.py')
        first, second = session.procedures[first_id], session.procedures[second_id]
        wait_for(lambda: first.status == 'RUNNING')
        assert second.status == 'PAUSED' and second.reason == 'WAITING_TOKEN' and second.process is None
        request(url, '/pause', {'epoch': epoch, 'procedure': first_id}, actor['token'])
        wait_for(lambda: first.status == 'PAUSED' and second.status == 'RUNNING')
        assert not first.has_token and second.has_token
        stack = json.dumps(first.stacks)
        time.sleep(0.15)
        assert json.dumps(first.stacks) == stack
        request(url, '/pause', {'epoch': epoch, 'procedure': second_id}, actor['token'])
        wait_for(lambda: second.status == 'PAUSED')
        request(url, '/resume', {'epoch': epoch, 'procedure': first_id}, actor['token'])
        wait_for(lambda: first.status == 'RUNNING')
        assert sum(p.has_token for p in session.procedures.values()) == 1


def test_parallel_limit_logical_identity_and_stop_cleanup(tmp_path):
    for name in ('first.py', 'second.py', 'third.py'):
        script(tmp_path, name)
    with serving(tmp_path, max_parallel=2) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        identifiers = [submit(url, actor, epoch, name) for name in ('first.py', 'second.py', 'third.py')]
        first, second, third = (session.procedures[i] for i in identifiers)
        wait_for(lambda: first.status == second.status == 'RUNNING')
        assert third.process is None
        with pytest.raises(ValueError, match='already active'):
            submit(url, actor, epoch, './first.py')
        pid = first.process.pid
        request(url, '/stop', {'epoch': epoch, 'procedure': first.id}, actor['token'])
        wait_for(lambda: first.status == 'CANCELLED' and third.status == 'RUNNING')
        assert not process_alive(pid)
        assert sum(p.has_token for p in session.procedures.values()) == 2
        pids = [p.process.pid for p in session.procedures.values()]
    assert not any(process_alive(pid) for pid in pids)


def test_lease_expiry_fences_old_controller_and_requires_explicit_resume(tmp_path):
    script(tmp_path, 'one.py')
    with serving(tmp_path, lease_seconds=0.9) as (session, url):
        alice, bob = connect(session, url), connect(session, url, 'Bob')
        epoch = claim(url, alice)
        identifier = submit(url, alice, epoch, 'one.py')
        procedure = session.procedures[identifier]
        def started():
            # Keep the intentionally short lease while a cold interpreter starts;
            # expiry is tested after the worker has actually begun executing.
            request(url, '/renew', {'epoch': epoch}, alice['token'])
            return procedure.status == 'RUNNING'
        wait_for(started)
        wait_for(lambda: session.controller is None and procedure.status == 'PAUSED')
        assert procedure.reason == 'CONTROLLER_EXPIRED' and not procedure.has_token
        with pytest.raises(ValueError, match='Stale'):
            request(url, '/resume', {'epoch': epoch, 'procedure': identifier}, alice['token'])
        newer = claim(url, bob)
        assert newer > epoch
        time.sleep(0.1)
        assert procedure.status == 'PAUSED'
        request(url, '/resume', {'epoch': newer, 'procedure': identifier}, bob['token'])
        wait_for(lambda: procedure.status == 'RUNNING')


def test_handoff_pauses_running_and_queued_and_rejects_stale_generation(tmp_path):
    script(tmp_path, 'one.py')
    script(tmp_path, 'two.py')
    with serving(tmp_path) as (session, url):
        alice, bob = connect(session, url), connect(session, url, 'Bob')
        epoch = claim(url, alice)
        first_id, second_id = submit(url, alice, epoch, 'one.py'), submit(url, alice, epoch, 'two.py')
        request(url, '/release', {'epoch': epoch}, alice['token'])
        wait_for(lambda: all(p.status == 'PAUSED' for p in session.procedures.values()))
        new_epoch = claim(url, bob)
        assert all(not p.wants_run for p in session.procedures.values())
        request(url, '/resume', {'epoch': new_epoch, 'procedure': 'all'}, bob['token'])
        wait_for(lambda: session.procedures[first_id].status == 'RUNNING')
        assert session.procedures[second_id].process is None
        with pytest.raises(ValueError, match='Stale'):
            request(url, '/stop', {'epoch': epoch, 'procedure': 'all'}, alice['token'])


def test_queued_source_change_rejected_and_next_token_is_reusable(tmp_path):
    script(tmp_path, 'one.py')
    script(tmp_path, 'two.py', "print('original')\n")
    with serving(tmp_path) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        first, second = submit(url, actor, epoch, 'one.py'), submit(url, actor, epoch, 'two.py')
        (tmp_path / 'two.py').write_text("raise RuntimeError('must not execute changed code')\n")
        request(url, '/stop', {'epoch': epoch, 'procedure': first}, actor['token'])
        wait_for(lambda: session.procedures[second].status == 'FAILED')
        text = ''.join(e.get('text', '') for e in session.events)
        assert 'Procedure changed after submission' in text and 'must not execute changed code' not in text
        assert not any(p.has_token for p in session.procedures.values())


def test_python_flags_unicode_stdin_and_unavailable_spell_plugin(tmp_path):
    environment = tmp_path / 'plain-python'
    subprocess.run([sys.executable, '-I', '-m', 'venv', '--without-pip', str(environment)], check=True)
    interpreter = environment / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    script(tmp_path, 'one.py', "import json,sys\nprint(json.dumps({'isolated':sys.flags.isolated,'qt':'PySide6' in sys.modules,'spell':'spell' in sys.modules}))\nprint(input(), flush=True)\n")
    with serving(tmp_path, interpreter=interpreter) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        identifier = submit(url, actor, epoch, 'one.py')
        procedure = session.procedures[identifier]
        wait_for(lambda: procedure.status == 'RUNNING')
        request(url, '/input', {'epoch': epoch, 'procedure': identifier, 'text': 'café 😀'}, actor['token'])
        wait_for(lambda: procedure.status == 'COMPLETED')
        text = ''.join(e.get('text', '') for e in session.events)
        assert '"isolated": 1' in text and '"qt": false' in text and '"spell": false' in text and 'café 😀' in text
        with pytest.raises(ValueError, match='SPELL requires'):
            request(url, '/run', {'epoch': epoch, 'script': 'one.py', 'language': 'spell'}, actor['token'])


def test_owned_child_keeps_token_until_real_process_quiescence(tmp_path):
    script(tmp_path, 'one.py', "import subprocess,sys,time\nchild=subprocess.Popen([sys.executable,'-I','-c','import time;time.sleep(2)'])\nprint(child.pid,flush=True)\nfor number in range(500):\n    time.sleep(0.02)\n")
    script(tmp_path, 'two.py')
    with serving(tmp_path) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        first_id, second_id = submit(url, actor, epoch, 'one.py'), submit(url, actor, epoch, 'two.py')
        first, second = session.procedures[first_id], session.procedures[second_id]
        wait_for(lambda: first.bootstrap_pids and first.owner.process_ids() - first.bootstrap_pids)
        request(url, '/pause', {'epoch': epoch, 'procedure': first_id}, actor['token'])
        time.sleep(0.2)
        assert first.status == 'PAUSING' and first.has_token and second.process is None
        wait_for(lambda: first.status == 'PAUSED' and second.status == 'RUNNING')


def test_headless_cli_help_and_run(tmp_path):
    from importlib.metadata import version
    root = Path(__file__).resolve().parents[1]
    script(tmp_path, 'hello.py', "print('CLI café 😀')\n")
    command = [sys.executable, '-I', '-X', 'utf8', str(root / 'run_cli.py')]
    result = subprocess.run([*command, '--version'], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0 and 'openbexi_ide ' + version('openbexi-ide') in result.stdout
    result = subprocess.run([*command, 'run', 'hello.py', '--project', str(tmp_path)], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0 and 'CLI café 😀' in result.stdout


def test_event_replay_gap_and_invalid_network_or_parallel_configuration(tmp_path):
    with serving(tmp_path) as (session, url):
        for number in range(2100):
            session.event('bounded', number=number)
        snapshot = session.snapshot(1)
        assert snapshot['replay_gap'] and len(snapshot['events']) == 2048
        with pytest.raises(ValueError, match='loopback'):
            SessionServer(('0.0.0.0', 0), session)
    with pytest.raises(ValueError, match='max_parallel'):
        Session(tmp_path, max_parallel=0)
