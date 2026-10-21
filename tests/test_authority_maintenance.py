"""Offline backup/restore with real SQLite, ownership and source captures."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import uuid
import zipfile

import pytest

from openbexi_runtime.maintenance import backup, file_hash, restore
from openbexi_runtime.session_store import SessionStore
from openbexi_runtime.session import Session


@pytest.fixture
def authority(tmp_path):
    root = tmp_path / 'authority'
    store = SessionStore(root)
    project = tmp_path / 'project'
    project.mkdir()
    capture = root / 'captures' / uuid.uuid4().hex
    capture.mkdir(parents=True)
    (capture / 'procedure.py').write_text('print("retained source")\n')
    state = dict(schema=1, id=uuid.uuid4().hex, project=str(project), mode='Development',
                 interpreter=str(Path(sys.executable).resolve()), max_parallel=1,
                 sequence=1, epoch=8, aliases={}, fences={}, procedures=[dict(
                     id=uuid.uuid4().hex, script='procedure.py', capture=str(capture),
                     arguments=[], language='python', source_sha256='a' * 64,
                     definition_id='retained-definition', version_id='b' * 64,
                     capture_sha256=None, procedure_fence=3, status='RUNNING',
                     exit_code=None, error=None, launched=True, uncertain_effects=True)])
    store.save(state, dict(sequence=1, type='fixture', time=0))
    store.db.executescript('CREATE TABLE releases(id TEXT PRIMARY KEY, manifest TEXT, approved INTEGER);'
                          "INSERT INTO releases VALUES('old-release','{}',1)")
    store.close()
    # Leave a committed WAL in a second DB; backing up raw .sqlite bytes would
    # lose this pending effect. Hold the connection open during the backup.
    driver = sqlite3.connect(capture / 'driver-effects.sqlite')
    driver.execute('PRAGMA journal_mode=WAL')
    driver.execute('CREATE TABLE effects(request TEXT, state TEXT)')
    driver.execute("INSERT INTO effects VALUES('external-write','PENDING')")
    driver.commit()
    yield root, state, driver
    driver.close()


def evidence(path, state):
    return dict(backup_sha256=file_hash(path), session=state['id'], minimum_epoch=90,
                actor='qualification operator', worker_shutdown_evidence='fixture worker shutdown verified',
                effect_settlement_evidence='fixture external ledger inspected; retain pending hold')


def test_consistent_wal_backup_restore_preserves_pending_holds_and_fences_old_tokens(authority, tmp_path):
    root, state, driver = authority
    archive = tmp_path / 'backup.zip'
    report = backup(root, archive)
    destination = tmp_path / 'restored'
    result = restore(archive, destination, evidence(archive, state))
    assert report['sha256'] == file_hash(archive)
    assert result['epoch'] == 91 and result['automatic_replay'] is False
    store = SessionStore(destination)
    try:
        saved, events = store.load()
        row = saved['procedures'][0]
        assert row['status'] == 'RECOVERY_REQUIRED' and row['uncertain_effects'] and row['launched']
        assert Path(row['capture']).is_relative_to(destination)
        assert (Path(row['capture']) / 'procedure.py').read_text() == 'print("retained source")\n'
        connection = sqlite3.connect(Path(row['capture']) / 'driver-effects.sqlite')
        try:
            assert connection.execute('SELECT * FROM effects').fetchall() == [('external-write', 'PENDING')]
        finally:
            connection.close()
        assert store.db.execute('SELECT approved FROM releases').fetchall() == [(0,)]
        assert events[-1]['type'] == 'offline_restored' and events[-1]['backup_sha256'] == report['sha256']
    finally:
        store.close()
    session = Session(Path(state['project']), state_directory=destination)
    try:
        procedure = session.procedures[state['procedures'][0]['id']]
        assert session.epoch == 92 and session.controller is None
        assert procedure.status == 'RECOVERY_REQUIRED' and procedure.process is None
        assert procedure.uncertain and procedure.has_token
    finally:
        session.close()


def test_backup_cannot_acquire_live_service_or_overwrite_retained_output(authority, tmp_path):
    root, state, _ = authority
    store = SessionStore(root)
    try:
        with pytest.raises(ValueError, match='already owned'):
            backup(root, tmp_path / 'live.zip')
    finally:
        store.close()
    output = tmp_path / 'backup.zip'
    backup(root, output)
    before = file_hash(output)
    with pytest.raises(ValueError, match='new file'):
        backup(root, output)
    assert file_hash(output) == before


@pytest.mark.parametrize('name', ['../escape', 'files/../../escape', 'files/C:/escape',
                                  'files/a\\escape', 'files/NUL', 'files/trailing.'])
def test_restore_rejects_unsafe_paths_without_creating_destination(authority, tmp_path, name):
    root, state, _ = authority
    archive = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(archive, 'w') as stream:
        item = zipfile.ZipInfo()
        item.filename = name  # Preserve a foreign ZIP's backslashes on Windows.
        stream.writestr(item, b'unsafe')
    destination = tmp_path / 'new-authority'
    with pytest.raises(ValueError, match='unsafe path'):
        restore(archive, destination, evidence(archive, state))
    assert not destination.exists() and not (tmp_path / 'escape').exists()


def test_restore_rejects_corruption_and_existing_destination(authority, tmp_path):
    root, state, _ = authority
    archive = tmp_path / 'good.zip'
    backup(root, archive)
    receipt = evidence(archive, state)
    destination = tmp_path / 'existing'
    destination.mkdir()
    (destination / 'keep').write_text('user data')
    with pytest.raises(ValueError, match='new authority'):
        restore(archive, destination, receipt)
    assert (destination / 'keep').read_text() == 'user data'
    altered = tmp_path / 'altered.zip'
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(altered, 'w') as target:
        for item in source.infolist():
            raw = source.read(item)
            target.writestr(item, b'corrupted' if item.filename.endswith('procedure.py') else raw)
    with pytest.raises(ValueError, match='backup hash'):
        restore(altered, tmp_path / 'bad1', receipt)
    with pytest.raises(ValueError, match='file hash'):
        restore(altered, tmp_path / 'bad2', evidence(altered, state))
    assert not (tmp_path / 'bad1').exists() and not (tmp_path / 'bad2').exists()


def test_restore_requires_both_evidence_and_archive_identity(authority, tmp_path):
    root, state, _ = authority
    archive = tmp_path / 'good.zip'
    backup(root, archive)
    receipt = evidence(archive, state)
    for key in ('worker_shutdown_evidence', 'effect_settlement_evidence', 'actor'):
        with pytest.raises(ValueError, match='evidence'):
            restore(archive, tmp_path / key, {**receipt, key: ''})
    with pytest.raises(ValueError, match='identity'):
        restore(archive, tmp_path / 'wrong-session', {**receipt, 'session': uuid.uuid4().hex})
