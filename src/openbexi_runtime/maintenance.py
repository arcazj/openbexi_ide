"""Offline, bounded authority backups. Restoration never resumes procedures."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import tempfile
import time
import zipfile

from .session_identity import unique_object
from .session_store import SessionStore, canonical

MAX_FILES = 16384
MAX_FILE = 128 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
SCHEMA = 'openbexi.authority-backup/1'


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(name):
    path = PurePosixPath(name)
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
                *(f'LPT{i}' for i in range(1, 10))}
    if (not name or path.is_absolute() or path.as_posix() != name
            or any(not part or part in {'.', '..'} or part.endswith(('.', ' '))
                   or part.split('.')[0].upper() in reserved
                   or any(ord(c) < 32 or c in '<>:"\\|?*' for c in part)
                   for part in name.split('/'))):
        raise ValueError('Backup contains an unsafe path')
    return path


def _regular(path):
    if path.is_symlink() or path.is_junction() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Authority backups require regular files without links')


def backup(directory, output):
    directory = Path(directory).absolute()
    output = Path(output).absolute()
    if (directory.is_symlink() or directory.is_junction()
            or not (directory / 'session.sqlite3').is_file()):
        raise ValueError('Backup requires an existing durable authority')
    directory = directory.resolve()
    if output.resolve().is_relative_to(directory) or output.exists():
        raise ValueError('Backup output must be a new file outside the authority')
    output.parent.mkdir(parents=True, exist_ok=True)
    store = SessionStore(directory)  # Exclusive OS lock, also excludes a live server.
    try:
        state, _ = store.load()
        if state is None:
            raise ValueError('Cannot back up an empty authority')
        with tempfile.TemporaryDirectory(prefix='openbexi-backup-') as temporary:
            root = Path(temporary)
            inventory, total = {}, 0
            for base, directories, files in os.walk(directory, followlinks=False):
                for name in directories:
                    candidate = Path(base) / name
                    if candidate.is_symlink() or candidate.is_junction():
                        raise ValueError('Authority backups do not follow links')
                for name in sorted(files):
                    source = Path(base) / name
                    _regular(source)
                    relative = source.relative_to(directory).as_posix()
                    safe_name(relative)
                    if relative == 'service.lock' or name.endswith(('-wal', '-shm', '-journal')):
                        continue
                    if len(inventory) >= MAX_FILES or source.stat().st_size > MAX_FILE:
                        raise ValueError('Authority backup exceeds its file bound')
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with source.open('rb') as stream:
                        database = stream.read(16) == b'SQLite format 3\x00'
                    if database:
                        # SQLite's backup API includes committed WAL pages and
                        # produces a standalone, checked database.
                        connection = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
                        destination = sqlite3.connect(target)
                        try:
                            connection.backup(destination)
                            if destination.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                                raise ValueError('Authority database integrity check failed')
                        finally:
                            destination.close()
                            connection.close()
                    else:
                        shutil.copyfile(source, target)
                    size = target.stat().st_size
                    total += size
                    if size > MAX_FILE or total > MAX_TOTAL:
                        raise ValueError('Authority backup exceeds its byte bound')
                    inventory[relative] = dict(sha256=file_hash(target), bytes=size,
                                               executable=bool(source.stat().st_mode & stat.S_IXUSR))
            manifest = dict(schema=SCHEMA, session=state['id'], epoch=state['epoch'],
                            source_directory=str(directory), created=time.time(), files=inventory)
            # Exclusive creation avoids overwriting a retained backup.
            with output.open('xb') as stream:
                if os.name != 'nt':
                    os.fchmod(stream.fileno(), 0o600)
                with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr('BACKUP.json', canonical(manifest))
                    for name in sorted(inventory):
                        archive.write(root / name, 'files/' + name)
        return dict(backup=str(output), sha256=file_hash(output), session=state['id'],
                    files=len(inventory), bytes=total, automatic_replay=False)
    finally:
        store.close()


def restore(archive_path, directory, receipt):
    archive_path, directory = Path(archive_path).resolve(strict=True), Path(directory).absolute()
    required = {'backup_sha256', 'session', 'minimum_epoch', 'actor',
                'worker_shutdown_evidence', 'effect_settlement_evidence'}
    if type(receipt) is not dict or set(receipt) != required:
        raise ValueError('Restore requires backup identity, epoch and shutdown/effect evidence')
    for key in ('actor', 'worker_shutdown_evidence', 'effect_settlement_evidence'):
        if type(receipt[key]) is not str or not receipt[key].strip() or len(receipt[key]) > 2000:
            raise ValueError('Restore evidence must be 1..2000 characters')
    if (type(receipt['minimum_epoch']) is not int or receipt['minimum_epoch'] < 0
            or receipt['backup_sha256'] != file_hash(archive_path)):
        raise ValueError('Restore backup hash or minimum epoch differs')
    if directory.exists() or directory.is_symlink() or directory.is_junction():
        raise ValueError('Restore requires a new authority directory')
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='openbexi-restore-', dir=directory.parent) as temporary:
        staging = Path(temporary) / 'authority'
        staging.mkdir(mode=0o700)
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if (len(entries) > MAX_FILES + 1 or sum(item.file_size for item in entries) > MAX_TOTAL + 4 * 1024 * 1024
                    or len({item.filename.casefold() for item in entries}) != len(entries)):
                raise ValueError('Backup inventory exceeds bounds or contains duplicate paths')
            for item in entries:
                if item.orig_filename != item.filename:
                    raise ValueError('Backup contains an unsafe path')
                safe_name(item.filename)
                if (item.is_dir() or item.flag_bits & 1 or item.file_size > MAX_FILE
                        or stat.S_IFMT(item.external_attr >> 16) not in {0, stat.S_IFREG}):
                    raise ValueError('Backup requires bounded regular unencrypted files')
            if 'BACKUP.json' not in archive.namelist():
                raise ValueError('Backup manifest is missing')
            info = archive.getinfo('BACKUP.json')
            if info.file_size > 4 * 1024 * 1024:
                raise ValueError('Backup manifest exceeds its bound')
            manifest = json.loads(archive.read(info), object_pairs_hook=unique_object)
            if (manifest.get('schema') != SCHEMA or manifest.get('session') != receipt['session']
                    or type(manifest.get('files')) is not dict
                    or {item.filename for item in entries} != {'BACKUP.json', *('files/' + n for n in manifest['files'])}):
                raise ValueError('Backup identity or inventory differs')
            for name, row in manifest['files'].items():
                safe_name(name)
                if name == 'service.lock' or name.endswith(('-wal', '-shm', '-journal')):
                    raise ValueError('Backup contains transient authority state')
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open('files/' + name) as source, target.open('xb') as stream:
                    shutil.copyfileobj(source, stream, length=1024 * 1024)
                if target.stat().st_size != row['bytes'] or file_hash(target) != row['sha256']:
                    raise ValueError('Backup file hash or size differs')
                target.chmod(0o700 if row['executable'] else 0o600)
        store = SessionStore(staging)
        try:
            if store.db.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise ValueError('Restored authority integrity check failed')
            state, _ = store.load()
            if state is None or state['id'] != receipt['session'] or state['epoch'] != manifest['epoch']:
                raise ValueError('Restored state identity differs')
            original = Path(manifest['source_directory'])
            for row in state['procedures']:
                capture = Path(row['capture'])
                if capture.is_relative_to(original):
                    row['capture'] = str(directory.resolve() / capture.relative_to(original))
                # A restored snapshot cannot prove what ran after it was taken.
                # Require offline reconciliation for every nonterminal row.
                if row['status'] not in {'COMPLETED', 'FAILED', 'CANCELLED'}:
                    row.update(status='RECOVERY_REQUIRED', launched=True, has_token=True,
                               uncertain_effects=True, pause_reason='BACKUP_RESTORED')
            # Historical approval must not resurrect a subsequently revoked release.
            if store.db.execute("SELECT 1 FROM sqlite_master WHERE name='releases'").fetchone():
                with store.db:
                    store.db.execute('UPDATE releases SET approved=0')
            state['epoch'] = max(state['epoch'], receipt['minimum_epoch']) + 1
            state['sequence'] += 1
            store.save(state, dict(sequence=state['sequence'], time=time.time(),
                                   type='offline_restored', **receipt))
        finally:
            store.close()
        # Rename into a new name only after every byte and database was checked.
        if directory.exists():
            raise ValueError('Restore destination was created during validation')
        staging.rename(directory)
    return dict(restored=str(directory), session=state['id'], epoch=state['epoch'],
                approvals_revoked=True, automatic_replay=False)
