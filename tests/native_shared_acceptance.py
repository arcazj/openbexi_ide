"""Explicit real native/Docker acceptance; requires the optional installed provider.

Run separately from the dependency-free core suite:
python -m pytest tests/native_shared_acceptance.py -W error
"""
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import time
import uuid

import pytest

from openbexi_runtime.cli import request
from openbexi_runtime.session import Session
from openbexi_runtime.shared_backends import load_backend
from test_durable_sessions import git, commit, durable
from test_sessions import connect, claim, wait_for


@pytest.fixture
def project(tmp_path):
    path = tmp_path / 'project'
    path.mkdir()
    git(path, 'init', '-q')
    (path / 'main.py').write_text("from spell.lang.functions import Display\nfrom pathlib import Path\nDisplay('NATIVE_SHARED_OK')\nPath('result.txt').write_text('native result')\n")
    (path / 'wait.py').write_text("import time\nfrom spell.lang.functions import Display\nDisplay('NATIVE_READY')\nwhile True:\n    time.sleep(.02)\n")
    commit(path)
    return path


def run(url, actor, epoch, name, **extra):
    return request(url, '/run', {'epoch': epoch, 'script': name, 'language': 'spell', **extra}, actor['token'])['id']


def output(session, identifier):
    return ''.join(e.get('text', '') for e in session.events if e.get('procedure') == identifier)


def complete(session, identifier):
    procedure = session.procedures[identifier]
    wait_for(lambda: procedure.status in {'COMPLETED', 'FAILED', 'RECOVERY_REQUIRED'}, timeout=60)
    assert procedure.status == 'COMPLETED', (procedure.public(), output(session, identifier))
    return procedure


def read_file(owner, name):
    data = subprocess.check_output(['docker', 'cp', owner.identifier + ':/workspace/' + name, '-'], timeout=10)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        return archive.extractfile(archive.getmembers()[0]).read()


def test_original_native_runtime_outputs_and_result_export(project, tmp_path):
    with durable(project, tmp_path / 'authority') as (session, url):
        actor = connect(session, url)
        identifier = run(url, actor, claim(url, actor), 'main.py')
        procedure = complete(session, identifier)
        assert 'NATIVE_SHARED_OK' in output(session, identifier)
        assert procedure.backend['profile'] == 'spell-native-shared-development/1'
        assert procedure.backend['image'].startswith('sha256:')
        result = session.store.directory / 'results/.openbexi/runs' / identifier
        assert (result / 'artifacts/result.txt').read_text() == 'native result'
        assert not (project / 'result.txt').exists()
        assert not (procedure.spec.project / 'result.txt').exists()
        assert json.loads((result / 'manifest.json').read_text())['image'] == procedure.backend['image']


def test_freeze_descendant_queue_monitor_and_handoff(project, tmp_path):
    (project / 'child.py').write_text("import time\nfrom pathlib import Path\nfor i in range(100000):\n    Path('ticks.txt').write_text(str(i))\n    time.sleep(.02)\n")
    (project / 'wait.py').write_text("import subprocess, sys, time\nfrom spell.lang.functions import Display\nchild = subprocess.Popen([sys.executable, 'child.py'])\nDisplay('CHILD_READY')\nwhile True:\n    time.sleep(.02)\n")
    commit(project)
    with durable(project, tmp_path / 'authority') as (session, url):
        alice, bob, monitor = connect(session, url), connect(session, url, 'Bob'), connect(session, url, 'Reader', True)
        epoch = claim(url, alice)
        identifier = run(url, alice, epoch, 'wait.py')
        p = session.procedures[identifier]
        wait_for(lambda: 'CHILD_READY' in output(session, identifier), timeout=60)
        queued = run(url, alice, epoch, 'main.py')
        assert session.procedures[queued].process is None
        with pytest.raises(ValueError, match='read-only'):
            request(url, '/pause', {'epoch': epoch, 'procedure': identifier}, monitor['token'])
        request(url, '/handoff', {'epoch': epoch, 'target': bob['client']}, alice['token'])
        wait_for(lambda: p.status == 'PAUSED', timeout=15)
        assert not p.has_token and p.owner.inspect()['State']['Paused']
        before = read_file(p.owner, 'ticks.txt')
        time.sleep(.3)
        assert read_file(p.owner, 'ticks.txt') == before
        with pytest.raises(ValueError, match='Stale'):
            request(url, '/resume', {'epoch': epoch, 'procedure': identifier}, alice['token'])
        new_epoch = claim(url, bob)
        request(url, '/resume', {'epoch': new_epoch, 'procedure': queued}, bob['token'])
        complete(session, queued)
        assert read_file(p.owner, 'ticks.txt') == before
        request(url, '/resume', {'epoch': new_epoch, 'procedure': identifier}, bob['token'])
        wait_for(lambda: not p.owner.inspect()['State']['Paused'], timeout=15)
        wait_for(lambda: read_file(p.owner, 'ticks.txt') != before)
        request(url, '/stop', {'epoch': new_epoch, 'procedure': identifier}, bob['token'])
        wait_for(lambda: p.status == 'RECOVERY_REQUIRED', timeout=20)


def test_native_prompt_and_arguments(project, tmp_path):
    (project / 'main.py').write_text("from spell.lang.functions import Prompt, Display\nfrom spell.lang.constants import YES_NO\nfrom spell.lang.modifiers import Type\nanswer = Prompt('Continue shared native?', {Type:YES_NO})\nassert answer is True\nDisplay('SHARED_PROMPT_ANSWERED')\n")
    commit(project)
    with durable(project, tmp_path / 'authority') as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        identifier = run(url, actor, epoch, 'main.py', arguments=['{}'])
        wait_for(lambda: 'Native prompt choices:' in output(session, identifier), timeout=60)
        request(url, '/input', {'epoch': epoch, 'procedure': identifier, 'text': '0'}, actor['token'])
        complete(session, identifier)
        assert 'SHARED_PROMPT_ANSWERED' in output(session, identifier)


def test_native_alias_capture_and_runtime_binding_survive_restart(project, tmp_path, monkeypatch):
    marker = str(uuid.uuid4())
    (project / 'wait.py').write_text(f'# @procedure-id {marker}\n' + (project / 'wait.py').read_text())
    (project / 'alias.py').write_text(f'# @procedure-id {marker}\nprint("alias")\n')
    commit(project)
    state = tmp_path / 'authority'
    with durable(project, state) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        active = run(url, actor, epoch, 'wait.py')
        wait_for(lambda: 'NATIVE_READY' in output(session, active), timeout=60)
        queued = run(url, actor, epoch, 'main.py')
        binding = session.procedures[queued].backend
        with pytest.raises(ValueError, match='already active'):
            run(url, actor, epoch, 'alias.py')
    (project / 'main.py').write_text('raise RuntimeError("live source must not run")\n')
    monkeypatch.setenv('OPENBEXI_SPELL_SHARED_IMAGE', 'missing-image-not-for-pull')
    with durable(project, state) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        assert session.procedures[active].status == 'RECOVERY_REQUIRED'
        assert session.procedures[queued].backend == binding
        request(url, '/configure', {'epoch': epoch, 'max_parallel': 2}, actor['token'])
        request(url, '/resume', {'epoch': epoch, 'procedure': queued}, actor['token'])
        complete(session, queued)
        assert 'NATIVE_SHARED_OK' in output(session, queued)
        with pytest.raises(ValueError, match='reconciliation'):
            request(url, '/resume', {'epoch': epoch, 'procedure': active}, actor['token'])


def test_capture_tamper_and_worker_http_cannot_release_native_slot(project, tmp_path):
    with durable(project, tmp_path / 'authority') as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        active = run(url, actor, epoch, 'wait.py')
        wait_for(lambda: 'NATIVE_READY' in output(session, active), timeout=60)
        p = session.procedures[active]
        with pytest.raises(ValueError, match='cannot use Python checkpoints'):
            request(url, '/worker/checkpoint', {'id': active, 'token': p.secret})
        queued = run(url, actor, epoch, 'main.py')
        q = session.procedures[queued]
        q.spec.script.write_text('raise RuntimeError("tampered")\n')
        request(url, '/pause', {'epoch': epoch, 'procedure': active}, actor['token'])
        wait_for(lambda: q.status == 'FAILED', timeout=20)
        assert q.process is None and 'dependency changed' in q.error
        assert p.status == 'PAUSED' and not p.has_token


def test_service_kill_native_container_recovered_without_replay(project, tmp_path):
    # A real independent service process owns the authority and Docker attachment.
    state, invite = tmp_path / 'authority', tmp_path / 'invite.json'
    cli = Path(__file__).resolve().parents[1] / 'run_cli.py'
    process = subprocess.Popen([sys.executable, '-I', str(cli), 'serve', '--project', str(project),
        '--state-directory', str(state), '--port', '0', '--info', str(invite)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        wait_for(invite.exists, timeout=20)
        info = json.loads(invite.read_text())
        actor = request(info['url'], '/connect', {'name': 'Kill qualification', 'invite': info['developer_invite']})
        epoch = claim(info['url'], actor)
        identifier = run(info['url'], actor, epoch, 'wait.py')
        wait_for(lambda: any('NATIVE_READY' in e.get('text', '') for e in request(info['url'], '/session', token=actor['token'])['events']), timeout=60)
        snapshot = request(info['url'], '/session', token=actor['token'])
        row = snapshot['procedures'][0]
        process.kill()
        process.wait(timeout=10)
        with durable(project, state) as (session, url):
            assert session.id == snapshot['session']
            p = session.procedures[identifier]
            assert p.status == 'RECOVERY_REQUIRED' and p.uncertain and p.has_token
            assert p.backend == row['backend'] and p.process is None
            assert session.controller is None
            from openbexi_spell_shared import identities, owned
            name, labels = identities(session.id, identifier)
            assert owned(name, labels, p.backend['image']) is None
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)
        for stream in (process.stdout, process.stderr):
            stream.close()


def test_native_desktop_operator_and_monitor(project, tmp_path, app):
    from PySide6.QtCore import QSettings
    from openbexi_ide.app import MainWindow
    from test_shared_ui import wait, claim as desktop_claim
    with durable(project, tmp_path / 'authority') as (session, url):
        invitation = tmp_path / 'invite.json'
        invitation.write_text(json.dumps({'url': url, 'developer_invite': session.developer_invite,
                                         'monitor_invite': session.monitor_invite}))
        windows = []
        try:
            for name, role in [('Operator', 'developer'), ('Reader', 'monitor')]:
                view = MainWindow(project, QSettings(str(tmp_path / (name + '.ini')), QSettings.IniFormat))
                windows.append(view)
                view.show()
                view.open_file(project / 'main.py')
                assert view.join_shared_session(user=name, invite_file=invitation, role=role)
                wait(app, lambda: view.session_client.healthy)
            operator, reader = windows
            desktop_claim(app, operator)
            index = operator.language.findData('spell')
            assert index >= 0
            operator.language.setCurrentIndex(index)
            assert not reader.run_action.isEnabled() and reader.current_editor().isReadOnly()
            operator.run_script()
            wait(app, lambda: bool(session.procedures), timeout=15)
            wait(app, lambda: next(iter(session.procedures.values())).status == 'COMPLETED', timeout=60)
            wait(app, lambda: 'NATIVE_SHARED_OK' in reader.console.toPlainText())
            assert next(iter(session.procedures.values())).backend['profile'] == 'spell-native-shared-development/1'
        finally:
            for view in windows:
                view.close()
                wait(app, lambda: not view.session_client.active)


def test_failed_freeze_retains_hold_without_false_pause(project, tmp_path, monkeypatch):
    with durable(project, tmp_path / 'authority') as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        identifier = run(url, actor, epoch, 'wait.py')
        p = session.procedures[identifier]
        wait_for(lambda: 'NATIVE_READY' in output(session, identifier), timeout=60)
        def failed_pause():
            raise RuntimeError('Injected Docker pause failure')
        monkeypatch.setattr(p.owner, 'pause', failed_pause)
        request(url, '/pause', {'epoch': epoch, 'procedure': identifier}, actor['token'])
        wait_for(lambda: p.status == 'RECOVERY_REQUIRED', timeout=20)
        assert p.uncertain and 'Injected Docker pause failure' in p.error
        assert not any(e['type'] == 'paused' and e.get('procedure') == identifier for e in session.events)
        with pytest.raises(ValueError, match='already active|reconciliation'):
            run(url, actor, epoch, 'wait.py')


def test_lease_expiry_freezes_native_worker_until_explicit_resume(project, tmp_path):
    with durable(project, tmp_path / 'authority') as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        identifier = run(url, actor, epoch, 'wait.py')
        p = session.procedures[identifier]
        wait_for(lambda: 'NATIVE_READY' in output(session, identifier), timeout=60)
        session.lease_seconds = .7
        request(url, '/renew', {'epoch': epoch}, actor['token'])
        wait_for(lambda: p.status == 'PAUSED', timeout=15)
        assert session.controller is None and p.owner.inspect()['State']['Paused']
        assert p.reason == 'CONTROLLER_EXPIRED' and not p.has_token
        session.lease_seconds = 30
        new_epoch = claim(url, actor)
        assert new_epoch > epoch and p.status == 'PAUSED'
        request(url, '/resume', {'epoch': new_epoch, 'procedure': identifier}, actor['token'])
        wait_for(lambda: not p.owner.inspect()['State']['Paused'], timeout=15)


def test_recovery_refuses_foreign_container_with_matching_name():
    from openbexi_spell_shared import provider, docker, identities
    session, procedure = uuid.uuid4().hex, uuid.uuid4().hex
    binding = provider.bind()
    name, _ = identities(session, procedure)
    identifier = docker('create', '--name', name, binding['image']).decode().strip()
    try:
        with pytest.raises(ValueError, match='ownership differs'):
            provider.recover(session, procedure, binding)
        assert json.loads(docker('inspect', identifier))[0]['Id'] == identifier
    finally:
        docker('rm', '--force', identifier)


def test_detached_descendant_prevents_clean_completion(project, tmp_path):
    (project / 'main.py').write_text("import subprocess\nfrom spell.lang.functions import Display\nsubprocess.Popen(['/usr/local/bin/python', '-c', 'import time; time.sleep(90)'], start_new_session=True)\nDisplay('DETACHED_STARTED')\n")
    commit(project)
    with durable(project, tmp_path / 'authority') as (session, url):
        actor = connect(session, url)
        identifier = run(url, actor, claim(url, actor), 'main.py')
        p = session.procedures[identifier]
        wait_for(lambda: p.status in {'RECOVERY_REQUIRED', 'COMPLETED', 'FAILED'}, timeout=60)
        assert p.status == 'RECOVERY_REQUIRED', (p.public(), output(session, identifier))
        assert p.uncertain and 'descendant shutdown unconfirmed' in p.error
        assert p.owner.closed
