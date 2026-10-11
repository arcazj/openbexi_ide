"""Real Git, SQLite, HTTP workers and fresh-process recovery acceptance."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

import pytest

from openbexi_runtime.cli import request
from openbexi_runtime.procedure_identity import definition_id
from openbexi_runtime.session import Session, SessionError
from openbexi_runtime.session_http import SessionServer
from openbexi_runtime.session_store import SessionStore
from openbexi_runtime.source_capture import capture, verify_capture
from test_sessions import wait_for, connect, claim, submit


def git(project, *args):
    result = subprocess.run(['git', '-C', str(project), *args], capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    return result.stdout


def commit(project):
    git(project, 'add', '.')
    git(project, '-c', 'user.name=Qualification', '-c', 'user.email=qualification@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '-qm', 'qualification source')


@pytest.fixture
def project(tmp_path):
    path = tmp_path / 'project'
    path.mkdir()
    git(path, 'init', '-q')
    (path / 'wait.py').write_text('import time\nwhile True:\n    time.sleep(0.02)\n')
    (path / 'main.py').write_text('from dependency import value\nprint(value, flush=True)\n')
    (path / 'dependency.py').write_text("value = 'captured dependency'\n")
    commit(path)
    return path


@contextmanager
def durable(project, state, **options):
    session = Session(project, state_directory=state, **options)
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


def test_captured_dependency_executes_original_after_worktree_change_and_restart(project, tmp_path):
    state = tmp_path / 'authority'
    with durable(project, state) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        running = submit(url, actor, epoch, 'wait.py')
        queued = submit(url, actor, epoch, 'main.py')
        wait_for(lambda: session.procedures[running].status == 'RUNNING')
        old_token, old_epoch, identity = actor['token'], epoch, session.id
        assert session.procedures[queued].process is None
    (project / 'dependency.py').write_text("value = 'modified live dependency'\n")
    with durable(project, state) as (session, url):
        assert session.id == identity and session.epoch > old_epoch
        assert session.controller is None
        with pytest.raises(SessionError, match='credential'):
            session.authenticate(old_token)
        assert session.procedures[running].status == 'RECOVERY_REQUIRED'
        assert session.procedures[queued].status == 'PAUSED'
        actor = connect(session, url)
        epoch = claim(url, actor)
        assert session.procedures[queued].process is None
        # Recovered uncertain worker retains a conservative slot reservation.
        request(url, '/configure', {'epoch': epoch, 'max_parallel': 2}, actor['token'])
        request(url, '/resume', {'epoch': epoch, 'procedure': queued}, actor['token'])
        wait_for(lambda: session.procedures[queued].status == 'COMPLETED')
        output = ''.join(e.get('text', '') for e in session.events if e.get('procedure') == queued)
        assert 'captured dependency' in output and 'modified live dependency' not in output
        with pytest.raises(ValueError, match='reconciliation'):
            request(url, '/stop', {'epoch': epoch, 'procedure': running}, actor['token'])


def test_global_logical_alias_survives_versions_context_paths_and_restart(project, tmp_path):
    marker = str(uuid.uuid4())
    (project / 'one.py').write_text(f'# @procedure-id {marker}\nimport time\nwhile True: time.sleep(0.02)\n')
    (project / 'other').mkdir()
    (project / 'other/two.py').write_text(f'# @procedure-id {marker}\nprint("new version")\n')
    commit(project)
    state = tmp_path / 'authority'
    with durable(project, state) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        first = submit(url, actor, epoch, 'one.py')
        wait_for(lambda: session.procedures[first].status == 'RUNNING')
        with pytest.raises(ValueError, match='already active'):
            submit(url, actor, epoch, 'other/two.py')
    with durable(project, state) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        with pytest.raises(ValueError, match='reconciliation'):
            submit(url, actor, epoch, 'other/two.py')
        with pytest.raises(ValueError, match='reconciliation'):
            request(url, '/resume', {'epoch': epoch, 'procedure': first}, actor['token'])


def test_terminal_alias_cannot_be_rebound_and_fence_increases(project, tmp_path):
    with durable(project, tmp_path / 'authority') as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        first = submit(url, actor, epoch, 'main.py')
        wait_for(lambda: session.procedures[first].status == 'COMPLETED')
        second = submit(url, actor, epoch, 'main.py')
        wait_for(lambda: session.procedures[second].status == 'COMPLETED')
        assert session.procedures[second].fence == session.procedures[first].fence + 1
        (project / 'main.py').write_text(f'# @procedure-id {uuid.uuid4()}\nprint("changed identity")\n')
        commit(project)
        with pytest.raises(ValueError, match='already bound'):
            submit(url, actor, epoch, 'main.py')


def test_dependency_tamper_and_dirty_worktree_rejected_before_execution(project, tmp_path):
    with durable(project, tmp_path / 'authority') as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        running = submit(url, actor, epoch, 'wait.py')
        queued = submit(url, actor, epoch, 'main.py')
        wait_for(lambda: session.procedures[running].status == 'RUNNING')
        (session.procedures[queued].spec.project / 'dependency.py').write_text('raise RuntimeError("tampered")\n')
        request(url, '/pause', {'epoch': epoch, 'procedure': running}, actor['token'])
        wait_for(lambda: session.procedures[queued].status == 'FAILED')
        assert session.procedures[queued].process is None
        assert 'dependency changed' in session.procedures[queued].error
        (project / 'dependency.py').write_text("value = 'dirty'\n")
        with pytest.raises(ValueError, match='Commit tracked'):
            submit(url, actor, epoch, 'main.py')


def test_bounded_durable_events_replay_and_handoff_audit(project, tmp_path):
    state = tmp_path / 'authority'
    with durable(project, state) as (session, url):
        alice, bob = connect(session, url), connect(session, url, 'Bob')
        epoch = claim(url, alice)
        identifier = submit(url, alice, epoch, 'wait.py')
        wait_for(lambda: session.procedures[identifier].status == 'RUNNING')
        result = request(url, '/handoff', {'epoch': epoch, 'target': bob['client']}, alice['token'])
        wait_for(lambda: session.procedures[identifier].status == 'PAUSED')
        assert session.controller == bob['client'] and result['requires_claim']
        assert not session.procedures[identifier].wants_run
        with pytest.raises(ValueError, match='Stale'):
            request(url, '/resume', {'epoch': epoch, 'procedure': identifier}, alice['token'])
        assert claim(url, bob) > epoch
        assert session.procedures[identifier].status == 'PAUSED'
        assert any(e['type'] == 'controller_handoff' and e['target'] == bob['client'] for e in session.events)
        for i in range(2050):
            session.event('output', number=i, text='x' * 4096)
        assert session.snapshot(1)['replay_gap']
        assert len(session.events) <= 2048
        sequence = session.sequence
    with SessionStoreForTest(state) as store:
        saved, events = store.load()
        assert saved['sequence'] > sequence
        assert len(events) <= 2048
        assert store.db.execute('SELECT SUM(bytes) FROM events').fetchone()[0] <= 8 * 1024 * 1024
        audit = [json.loads(row[0]) for row in store.db.execute('SELECT value FROM audit')]
        assert any(e['type'] == 'controller_handoff' for e in audit)
        assert not any(e['type'] == 'output' for e in audit)
        raw = json.dumps(saved)
        assert alice['token'] not in raw and 'developer_invite' not in raw


@contextmanager
def SessionStoreForTest(path):
    store = SessionStore(path)
    try:
        yield store
    finally:
        store.close()


def test_second_service_process_is_excluded_before_recovery(project, tmp_path):
    state = tmp_path / 'authority'
    with durable(project, state) as (session, url):
        code = ('import sys; sys.path.insert(0,sys.argv[1]); from openbexi_runtime.session_store import SessionStore; '
                'SessionStore(sys.argv[2])')
        result = subprocess.run([sys.executable, '-I', '-c', code,
                                 str(Path(__file__).resolve().parents[1] / 'src'), str(state)],
                                capture_output=True, timeout=15)
        assert result.returncode != 0 and b'already owned' in result.stderr
        assert request(url, '/healthz')['session'] == session.id


def test_persistence_failure_fails_closed_before_launch(project, tmp_path, monkeypatch):
    with durable(project, tmp_path / 'authority') as (session, url):
        actor = session.authenticate(connect(session, url)['token'])
        epoch = session.claim(actor)['epoch']
        def fail(*args):
            raise sqlite3.OperationalError('injected disk failure')
        monkeypatch.setattr(session.store, 'save', fail)
        with pytest.raises(SessionError, match='persistence unavailable'):
            session.submit(actor, epoch, 'main.py')
        assert session.closed.is_set()
        assert all(p.process is None for p in session.procedures.values())
        with pytest.raises(SessionError, match='not accepting'):
            session.claim(actor)


def test_actual_service_kill_restart_holds_worker_and_revokes_credentials(project, tmp_path):
    state, info = tmp_path / 'authority', tmp_path / 'server.json'
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, '-I', str(root / 'run_cli.py'), 'serve', '--project', str(project),
               '--state-directory', str(state), '--info', str(info), '--port', '0']
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        wait_for(info.exists, timeout=15)
        config = json.loads(info.read_text())
        url = config['url']
        actor = request(url, '/connect', {'name': 'Crash qualification', 'invite': config['developer_invite']})
        epoch = claim(url, actor)
        identifier = submit(url, actor, epoch, 'wait.py')
        wait_for(lambda: request(url, '/session', token=actor['token'])['procedures'][0]['status'] == 'RUNNING')
        child.kill()
        child.wait(timeout=10)
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)
    with durable(project, state) as (session, url):
        assert session.id == config['session']
        p = session.procedures[identifier]
        assert p.status == 'RECOVERY_REQUIRED' and p.uncertain and p.has_token
        assert p.process is None and not p.wants_run
        with pytest.raises(ValueError, match='credential'):
            request(url, '/session', token=actor['token'])
        fresh = connect(session, url)
        assert claim(url, fresh) > epoch
        with pytest.raises(ValueError, match='already active'):
            submit(url, fresh, session.epoch, 'wait.py')


@pytest.mark.parametrize('source', [
    '# @procedure-id invalid\n',
    '# @procedure-id 4DA54162-8D0D-4946-B25C-797B52884CE6\n',
    '\n' * 64 + '# @procedure-id 4da54162-8d0d-4946-b25c-797b52884ce6\n',
    '# @procedure-id 4da54162-8d0d-4946-b25c-797b52884ce6\n' * 2,
])
def test_legacy_identity_boundary_rules_preserved(source):
    with pytest.raises(ValueError):
        definition_id('catalog', source)


def test_identity_uses_comments_not_strings_and_preserves_legacy_namespace():
    assert definition_id('A', 'print("# @procedure-id invalid")') == definition_id('a', '')
    assert definition_id('A', '') == str(uuid.uuid5(uuid.UUID('d5e918ab-c027-5d31-94c0-cb9fb09c5743'), 'a'))


def test_capture_inventory_rejects_added_dependency(project, tmp_path):
    root, digest, manifest = capture(project, 'main.py', tmp_path / 'captures')
    assert verify_capture(root, digest) == manifest
    (root / 'extra.py').write_text('print("injected dependency")')
    with pytest.raises(ValueError, match='inventory changed'):
        verify_capture(root, digest)


def test_offline_reconciliation_requires_exact_fence_and_both_evidence_records(project, tmp_path):
    state = tmp_path / 'authority'
    with durable(project, state) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        identifier = submit(url, actor, epoch, 'wait.py')
        wait_for(lambda: session.procedures[identifier].status == 'RUNNING')
        receipt = {'session': session.id, 'procedure': identifier,
                   'fence': session.procedures[identifier].fence,
                   'worker_shutdown_evidence': 'Fixture joined owned worker and closed its job',
                   'effect_settlement_evidence': 'Fixture only sleeps; reviewed captured tree has no external commands'}
        with pytest.raises(ValueError, match='already owned'):
            SessionStore(state)
    with SessionStoreForTest(state) as store:
        with pytest.raises(ValueError, match='fence'):
            store.reconcile({**receipt, 'fence': receipt['fence'] + 1})
        with pytest.raises(ValueError, match='evidence'):
            store.reconcile({**receipt, 'effect_settlement_evidence': ''})
        assert store.reconcile(receipt)['automatic_replay'] is False
        with pytest.raises(ValueError, match='recovery state'):
            store.reconcile(receipt)
    with durable(project, state) as (session, url):
        assert session.procedures[identifier].status == 'CANCELLED'
        assert session.procedures[identifier].process is None
        actor = connect(session, url)
        epoch = claim(url, actor)
        next_id = submit(url, actor, epoch, 'wait.py')
        assert session.procedures[next_id].fence > receipt['fence']


def test_capture_does_not_block_worker_checkpoints_and_rechecks_revoked_controller(project, tmp_path, monkeypatch):
    from openbexi_runtime import source_capture
    original = source_capture.capture
    entered, proceed, outcome = threading.Event(), threading.Event(), []
    def delayed(*args):
        entered.set()
        assert proceed.wait(10)
        return original(*args)
    with durable(project, tmp_path / 'authority') as (session, url):
        actor = session.authenticate(connect(session, url)['token'])
        epoch = session.claim(actor)['epoch']
        identifier = session.submit(actor, epoch, 'wait.py')['id']
        wait_for(lambda: session.procedures[identifier].status == 'RUNNING')
        monkeypatch.setattr(source_capture, 'capture', delayed)
        def submit_late():
            try:
                session.submit(actor, epoch, 'main.py')
            except SessionError as error:
                outcome.append(str(error))
        thread = threading.Thread(target=submit_late)
        thread.start()
        try:
            assert entered.wait(5)
            session.release(actor, epoch)
            wait_for(lambda: session.procedures[identifier].status == 'PAUSED')
            assert session.procedures[identifier].process.poll() is None
        finally:
            proceed.set()
            thread.join(timeout=10)
        assert outcome and 'Stale' in outcome[0]
        assert len(session.procedures) == 1


def test_atomic_concurrent_alias_admission_uses_one_reservation(project, tmp_path):
    marker = str(uuid.uuid4())
    for name in ('first.py', 'second.py'):
        (project / name).write_text(f'# @procedure-id {marker}\nimport time\nwhile True: time.sleep(0.02)\n')
    commit(project)
    with durable(project, tmp_path / 'authority', max_parallel=2) as (session, url):
        actor = session.authenticate(connect(session, url)['token'])
        epoch = session.claim(actor)['epoch']
        barrier, outcomes = threading.Barrier(2), []
        def compete(name):
            barrier.wait()
            try:
                outcomes.append(session.submit(actor, epoch, name)['id'])
            except SessionError:
                outcomes.append('conflict')
        threads = [threading.Thread(target=compete, args=(name,)) for name in ('first.py', 'second.py')]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
            assert not thread.is_alive()
        assert outcomes.count('conflict') == 1 and len(session.procedures) == 1


def test_persistence_failure_terminates_owned_worker_and_retains_recovery_hold(project, tmp_path, monkeypatch):
    state = tmp_path / 'authority'
    with durable(project, state) as (session, url):
        actor = session.authenticate(connect(session, url)['token'])
        epoch = session.claim(actor)['epoch']
        identifier = session.submit(actor, epoch, 'wait.py')['id']
        wait_for(lambda: session.procedures[identifier].status == 'RUNNING')
        def fail(*args):
            raise sqlite3.OperationalError('injected disk failure')
        monkeypatch.setattr(session.store, 'save', fail)
        with pytest.raises(SessionError, match='service fenced'):
            session.event('persistence_probe')
        assert session.snapshot()['controller'] is None
        assert session.snapshot()['storage_healthy'] is False
        with pytest.raises(ValueError, match='HTTP Error 503'):
            request(url, '/healthz')
        wait_for(lambda: session.procedures[identifier].process.poll() is not None)
    with durable(project, state) as (session, _url):
        assert session.procedures[identifier].status == 'RECOVERY_REQUIRED'
