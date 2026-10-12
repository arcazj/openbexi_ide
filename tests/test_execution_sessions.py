"""Real immutable images, offline approvals, HTTP peers and container isolation."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

from openbexi_runtime.cli import main, request
from openbexi_runtime.execution_release import ReleaseAuthority, digest, docker, prepare, read_manifest
from openbexi_runtime.procedure_identity import version_id
from openbexi_runtime.session import Session
from openbexi_runtime.session_store import SessionStore
from test_durable_sessions import commit, git, durable
from test_sessions import claim, connect, submit, wait_for

pytestmark = pytest.mark.skipif(not os.environ.get('OPENBEXI_EXECUTION_TEST_IMAGE'),
                                reason='Set OPENBEXI_EXECUTION_TEST_IMAGE to an exact Docker image ID')

SOURCE = '''# @procedure-id 184ad12b-8ad4-435d-96b3-b2de45e4abb1
import json, os, pathlib, socket, subprocess, sys, time
from dependency import value
mode = sys.argv[1] if len(sys.argv)>1 else 'inspect'
if mode == 'inspect':
    denied = []
    for path in ('/release/main.py', '/release/dependency.py', '/usr/local/lib/probe', '/etc/probe'):
        try: pathlib.Path(path).write_text('tamper')
        except OSError: denied.append(path)
    pathlib.Path('/tmp/result').write_text('private output')
    sock = socket.socket()
    sock.settimeout(.2)
    try: sock.connect(('192.0.2.1', 9)); network = True
    except OSError: network = False
    finally: sock.close()
    status = pathlib.Path('/proc/self/status').read_text()
    print(json.dumps(dict(value=value, denied=denied, network=network, uid=os.getuid(),
        status=status, socket=pathlib.Path('/var/run/docker.sock').exists())), flush=True)
elif mode == 'input':
    print('input-ready', flush=True)
    print('answer=' + input(), flush=True)
elif mode == 'burst':
    import atexit, ctypes
    atexit.register(lambda: print('exit-handler-ran', flush=True))
    ctypes.CDLL(None).printf(b'c-buffered-output\\n')
    for i in range(200):
        os.write(1, ('native-out-%s\\n'%i).encode())
        os.write(2, ('native-err-%s\\n'%i).encode())
elif mode == 'child':
    child = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(2)'])
    print('child-ready', flush=True)
    while True: time.sleep(.02)
elif mode == 'fail':
    raise RuntimeError('deliberate failure')
else:
    print('wait-ready', flush=True)
    while True: time.sleep(.02)
'''


@pytest.fixture(scope='module')
def released(tmp_path_factory):
    root = tmp_path_factory.mktemp('execution-release')
    project = root / 'project'
    project.mkdir()
    git(project, 'init', '-q')
    (project / 'main.py').write_text(SOURCE, encoding='utf-8')
    (project / 'dependency.py').write_text("value = 'approved dependency'\n")
    (project / 'second.py').write_text("from dependency import value\nprint('second: ' + value, flush=True)\n")
    (project / 'alias.py').write_text(SOURCE, encoding='utf-8')
    commit(project)
    result = prepare(project, 'main.py', os.environ['OPENBEXI_EXECUTION_TEST_IMAGE'], root / 'prepared',
                     additional_procedures=['second.py', 'alias.py'])
    manifest = read_manifest(result['manifest'])
    # Retained preparation path is included in pytest's fixture output on failure.
    return project, manifest, result


def approve(state, manifest):
    store = SessionStore(state)
    try:
        ReleaseAuthority(store).decide(manifest, approved=True, actor='Qualification operator',
                                       evidence='Synthetic acceptance fixture; no operational approval')
    finally:
        store.close()


def output(session, identifier):
    return ''.join(e.get('text', '') for e in session.events if e.get('procedure') == identifier)


def run(url, actor, epoch, mode='inspect'):
    return request(url, '/run', {'epoch': epoch, 'script': 'main.py', 'arguments': [mode]}, actor['token'])['id']


def test_offline_approval_exact_identity_and_tamper(released, tmp_path):
    project, manifest, result = released
    state = tmp_path / 'state'
    with pytest.raises(ValueError, match='not approved'):
        Session(project, state_directory=state, execution_release=result['release'])
    assert main(['release-approve', '--manifest', result['manifest'], '--expected-release', '0'*64,
                 '--state-directory', str(state), '--actor', 'Tester', '--evidence', 'review']) == 2
    approve(state, manifest)
    store = SessionStore(state)
    try:
        authority = ReleaseAuthority(store)
        altered = copy.deepcopy(manifest)
        altered['procedures']['main.py']['definition'] = str(uuid.uuid4())
        altered['procedures']['main.py']['version'] = version_id(altered['procedures']['main.py']['definition'], altered['source']['files']['main.py']['sha256'],
                                       altered['image'], altered['source_digest'])
        with pytest.raises(ValueError, match='definition differs'):
            authority.decide(altered, approved=True, actor='Tester', evidence='incorrect identity')
        altered = copy.deepcopy(manifest)
        altered['source']['files']['dependency.py']['sha256'] = '0'*64
        altered['source_digest'] = digest(altered['source'])
        for name, row in altered['procedures'].items():
            row['version'] = version_id(row['definition'], altered['source']['files'][name]['sha256'],
                                       altered['image'], altered['source_digest'])
        with pytest.raises(ValueError, match='source differs'):
            authority.decide(altered, approved=True, actor='Tester', evidence='incorrect inventory')
        authority.decide(manifest, approved=False, actor='Tester', evidence='revoked fixture')
        with pytest.raises(ValueError, match='revoked'):
            authority.require(result['release'])
        assert store.db.execute('SELECT COUNT(*) FROM release_audit').fetchone()[0] == 2
    finally:
        store.close()


def test_actual_isolation_source_runtime_output_and_monitor(released, tmp_path):
    project, manifest, result = released
    state = tmp_path / 'state'
    approve(state, manifest)
    with durable(project, state, execution_release=result['release']) as (session, url):
        actor, reader = connect(session, url), connect(session, url, 'Reader', True)
        epoch = claim(url, actor)
        with pytest.raises(ValueError, match='already owned'):
            SessionStore(state)
        with pytest.raises(ValueError, match='read-only'):
            claim(url, reader)
        with pytest.raises(ValueError, match='outside'):
            submit(url, actor, epoch, 'dependency.py')
        identifier = run(url, actor, epoch)
        p = session.procedures[identifier]
        wait_for(lambda: p.status in {'COMPLETED', 'FAILED', 'RECOVERY_REQUIRED'}, timeout=20)
        assert p.status == 'COMPLETED', (p.public(), output(session, identifier))
        report = json.loads(output(session, identifier))
        assert report['value'] == 'approved dependency'
        assert len(report['denied']) == 4 and not report['network'] and not report['socket']
        assert report['uid'] == 65532
        assert 'NoNewPrivs:\t1' in report['status'] and 'Seccomp:\t2' in report['status']
        snapshot = request(url, '/session', token=reader['token'])
        assert snapshot['mode'] == 'Execution' and snapshot['execution_approved']
        assert snapshot['release_id'] == result['release']
        assert p.version == manifest['procedures']['main.py']['version'] and p.release == result['release']
        identifier = run(url, actor, epoch, 'burst')
        wait_for(lambda: session.procedures[identifier].status == 'COMPLETED', timeout=20)
        text = output(session, identifier)
        assert text.count('native-out-') == 200 and text.count('native-err-') == 200
        assert 'exit-handler-ran' in text and 'c-buffered-output' in text


def test_pause_handoff_input_stop_and_uncertainty(released, tmp_path):
    project, manifest, result = released
    state = tmp_path / 'state'
    approve(state, manifest)
    with durable(project, state, execution_release=result['release']) as (session, url):
        alice, bob = connect(session, url), connect(session, url, 'Bob')
        epoch = claim(url, alice)
        identifier = run(url, alice, epoch, 'wait')
        p = session.procedures[identifier]
        wait_for(lambda: 'wait-ready' in output(session, identifier), timeout=20)
        with pytest.raises(ValueError, match='already active'):
            run(url, alice, epoch)
        with pytest.raises(ValueError, match='already active'):
            submit(url, alice, epoch, 'alias.py')
        queued = submit(url, alice, epoch, 'second.py')
        assert session.procedures[queued].status == 'PAUSED'
        request(url, '/release', {'epoch': epoch}, alice['token'])
        wait_for(lambda: p.status == 'PAUSED', timeout=12)
        assert not p.has_token and p.owner.process_ids()
        epoch2 = claim(url, bob)
        assert p.status == 'PAUSED'
        with pytest.raises(ValueError, match='Stale|controller'):
            request(url, '/resume', {'epoch': epoch, 'procedure': identifier}, alice['token'])
        request(url, '/resume', {'epoch': epoch2, 'procedure': identifier}, bob['token'])
        wait_for(lambda: p.status == 'RUNNING')
        request(url, '/stop', {'epoch': epoch2, 'procedure': identifier}, bob['token'])
        wait_for(lambda: p.status == 'RECOVERY_REQUIRED', timeout=15)
        assert p.owner.closed and p.uncertain
        with pytest.raises(ValueError, match='active|reconciliation'):
            run(url, bob, epoch2)
        request(url, '/resume', {'epoch': epoch2, 'procedure': queued}, bob['token'])
        wait_for(lambda: session.procedures[queued].status == 'COMPLETED', timeout=20)
    # A fresh authority exercises real console input independently of that hold.
    state2 = tmp_path / 'input-state'
    approve(state2, manifest)
    with durable(project, state2, execution_release=result['release']) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        identifier = run(url, actor, epoch, 'input')
        wait_for(lambda: 'input-ready' in output(session, identifier), timeout=20)
        request(url, '/input', {'epoch': epoch, 'procedure': identifier, 'text': 'café'}, actor['token'])
        wait_for(lambda: session.procedures[identifier].status == 'COMPLETED', timeout=20)
        assert 'answer=café' in output(session, identifier)


def test_child_retains_slot_until_real_exit(released, tmp_path):
    project, manifest, result = released
    state = tmp_path / 'state'
    approve(state, manifest)
    with durable(project, state, execution_release=result['release']) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        identifier = run(url, actor, epoch, 'child')
        p = session.procedures[identifier]
        wait_for(lambda: 'child-ready' in output(session, identifier), timeout=20)
        request(url, '/pause', {'epoch': epoch, 'procedure': identifier}, actor['token'])
        time.sleep(.3)
        assert p.status == 'PAUSING' and p.has_token
        wait_for(lambda: p.status == 'PAUSED', timeout=10)


def test_worker_control_loss_terminates_container_and_holds(released, tmp_path):
    project, manifest, result = released
    state = tmp_path / 'state'
    approve(state, manifest)
    with durable(project, state, execution_release=result['release']) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        identifier = run(url, actor, epoch, 'wait')
        p = session.procedures[identifier]
        wait_for(lambda: 'wait-ready' in output(session, identifier), timeout=20)
        p.channel.done.set()
        p.process.stdin.close()
        wait_for(lambda: p.status == 'RECOVERY_REQUIRED', timeout=15)
        assert p.uncertain and p.owner.closed
    with durable(project, state, execution_release=result['release']) as (session, url):
        assert session.procedures[identifier].status == 'RECOVERY_REQUIRED'
        assert session.controller is None


def test_revoked_queued_release_cannot_run_after_restart(released, tmp_path):
    project, manifest, result = released
    state = tmp_path / 'state'
    approve(state, manifest)
    with durable(project, state, execution_release=result['release']) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        first = run(url, actor, epoch, 'wait')
        wait_for(lambda: 'wait-ready' in output(session, first), timeout=20)
        queued = submit(url, actor, epoch, 'second.py')
        assert session.procedures[queued].process is None
    replacement = copy.deepcopy(manifest)
    del replacement['procedures']['alias.py']
    approve(state, replacement)
    store = SessionStore(state)
    try:
        ReleaseAuthority(store).decide(manifest, approved=False, actor='Tester', evidence='revoked original catalog')
    finally:
        store.close()
    with durable(project, state, execution_release=digest(replacement)) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        assert session.procedures[first].status == 'RECOVERY_REQUIRED'
        request(url, '/configure', {'epoch': epoch, 'max_parallel': 2}, actor['token'])
        request(url, '/resume', {'epoch': epoch, 'procedure': queued}, actor['token'])
        wait_for(lambda: session.procedures[queued].status == 'FAILED')
        assert session.procedures[queued].process is None
        assert 'revoked' in session.procedures[queued].error
        new = submit(url, actor, epoch, 'second.py')
        wait_for(lambda: session.procedures[new].status == 'COMPLETED', timeout=20)
        assert session.procedures[new].fence > session.procedures[queued].fence


def test_actual_service_kill_stops_container_and_recovery_never_replays(released, tmp_path):
    project, manifest, result = released
    state, info_path = tmp_path / 'state', tmp_path / 'connection.json'
    approve(state, manifest)
    server = subprocess.Popen([sys.executable, '-I', str(Path(__file__).parents[1] / 'run_cli.py'),
        'serve', '--project', str(project), '--state-directory', str(state),
        '--execution-release', result['release'], '--port', '0', '--info', str(info_path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        wait_for(lambda: info_path.exists(), timeout=15)
        info = json.loads(info_path.read_text())
        url = info['url']
        actor = request(url, '/connect', {'name': 'Crash tester', 'invite': info['developer_invite']})
        epoch = claim(url, actor)
        identifier = run(url, actor, epoch, 'wait')
        wait_for(lambda: any(e.get('text', '').startswith('wait-ready')
            for e in request(url, '/session', token=actor['token'])['events']), timeout=20)
        queued = submit(url, actor, epoch, 'second.py')
        from openbexi_runtime.execution_container import container_name
        name = container_name(info['session'], identifier)
        server.kill()
        server.wait(timeout=10)
        wait_for(lambda: not json.loads(docker('inspect', name))[0]['State']['Running'], timeout=12)
        with durable(project, state, execution_release=result['release']) as (session, new_url):
            assert session.id == info['session']
            assert session.procedures[identifier].status == 'RECOVERY_REQUIRED'
            assert session.procedures[queued].status == 'PAUSED'
            assert session.controller is None
            assert not docker('ps', '-a', '--filter', 'name=^/' + name + '$', '--format', '{{.ID}}').strip()
            with pytest.raises(ValueError, match='credential'):
                request(new_url, '/session', token=actor['token'])
    finally:
        if server.poll() is None:
            server.kill()
        server.communicate(timeout=10)


def test_execution_desktop_is_read_only_and_runs_approved_image(released, tmp_path, app):
    from PySide6.QtCore import QSettings
    from openbexi_ide.app import MainWindow
    from test_shared_ui import wait, claim as desktop_claim
    project, manifest, result = released
    state = tmp_path / 'state'
    approve(state, manifest)
    with durable(project, state, execution_release=result['release']) as (session, url):
        invitation = tmp_path / 'invite.json'
        invitation.write_text(json.dumps({'url': url, 'developer_invite': session.developer_invite,
                                         'monitor_invite': session.monitor_invite}))
        windows = []
        try:
            for name, role in [('Operator', 'developer'), ('Reader', 'monitor')]:
                view = MainWindow(project, QSettings(str(tmp_path / (name+'.ini')), QSettings.IniFormat))
                windows.append(view)
                view.show()
                view.open_file(project / 'main.py')
                assert view.join_shared_session(user=name, invite_file=invitation, role=role)
                wait(app, lambda: view.session_client.healthy)
            operator, reader = windows
            desktop_claim(app, operator)
            assert operator.current_editor().isReadOnly() and reader.current_editor().isReadOnly()
            assert not operator.save_action.isEnabled() and not operator.new_action.isEnabled()
            assert not reader.run_action.isEnabled() and not reader.input.isEnabled()
            assert 'Execution' in operator.session_panel.status.text()
            assert 'Monitoring' in reader.session_panel.status.text()
            operator.run_script()
            wait(app, lambda: bool(session.procedures), timeout=15)
            wait(app, lambda: list(session.procedures.values())[0].status == 'COMPLETED', timeout=20)
            wait(app, lambda: 'approved dependency' in reader.console.toPlainText())
            original = (project / 'main.py').read_bytes()
            try:
                (project / 'main.py').write_bytes(original + b'\nprint("unapproved edit")\n')
                operator.run_script()
                assert len(session.procedures) == 1
                assert 'differs from the approved version' in operator.console.toPlainText()
            finally:
                (project / 'main.py').write_bytes(original)
        finally:
            for view in windows:
                view.close()
                wait(app, lambda: not view.session_client.active)
