"""Single-authority durable state and bounded event journal.

An OS-owned lock excludes a second service before recovery begins. SQLite commits
state, logical reservations and events together, before any process is launched.
The lock has no TTL; process exit releases it. Uncertain reservations have no TTL.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


class SessionStore:
    def __init__(self, directory, *, event_limit=2048, byte_limit=8 * 1024 * 1024):
        if type(event_limit) is not int or not 1 <= event_limit <= 100000:
            raise ValueError('Invalid durable event bound')
        if type(byte_limit) is not int or not 65536 <= byte_limit <= 64 * 1024 * 1024:
            raise ValueError('Invalid durable event byte bound')
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.event_limit, self.byte_limit = event_limit, byte_limit
        self.guard = (self.directory / 'service.lock').open('a+b')
        self.db = None
        try:
            self.guard.seek(0)
            if os.name == 'nt':
                import msvcrt
                # Locking past EOF is supported; never truncate a live lock file.
                msvcrt.locking(self.guard.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.guard.close()
            raise ValueError('Durable service directory is already owned') from error
        try:
            self.db = sqlite3.connect(self.directory / 'session.sqlite3', check_same_thread=False)
            self.db.execute('PRAGMA journal_mode=DELETE')
            self.db.execute('PRAGMA synchronous=FULL')
            version = self.db.execute('PRAGMA user_version').fetchone()[0]
            if version not in {0, 1, 2}:
                raise ValueError('Unsupported durable session schema')
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY, value TEXT NOT NULL, bytes INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (sequence INTEGER PRIMARY KEY, value TEXT NOT NULL, bytes INTEGER NOT NULL);
                PRAGMA user_version=2;
            ''')
        except BaseException:
            self.close()
            raise

    def load(self):
        row = self.db.execute('SELECT value FROM state WHERE id=1').fetchone()
        events = [json.loads(row[0]) for row in self.db.execute('SELECT value FROM events ORDER BY sequence')]
        return (json.loads(row[0]) if row else None), events

    def save(self, state, event):
        raw, encoded = canonical(state), canonical(event)
        size = len(encoded.encode())
        if size > 65536:
            raise ValueError('Durable event exceeds 64 KiB')
        with self.db:
            if event['type'] != 'output':
                count, total = self.db.execute('SELECT COUNT(*),COALESCE(SUM(bytes),0) FROM audit').fetchone()
                if count >= 100000 or total + size > 16 * 1024 * 1024:
                    raise ValueError('Durable audit capacity reached; archive and provision a new authority')
                self.db.execute('INSERT INTO audit VALUES (?,?,?)', (event['sequence'], encoded, size))
            self.db.execute('INSERT INTO state VALUES (1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value', (raw,))
            self.db.execute('INSERT INTO events VALUES (?,?,?)', (event['sequence'], encoded, size))
            self.db.execute('DELETE FROM events WHERE sequence <= ?', (event['sequence'] - self.event_limit,))
            total = self.db.execute('SELECT COALESCE(SUM(bytes),0) FROM events').fetchone()[0]
            if total > self.byte_limit:
                for sequence, count in self.db.execute('SELECT sequence,bytes FROM events ORDER BY sequence').fetchall():
                    self.db.execute('DELETE FROM events WHERE sequence=?', (sequence,))
                    total -= count
                    if total <= self.byte_limit:
                        break
        return self.db.execute('SELECT MIN(sequence) FROM events').fetchone()[0]

    def reconcile(self, receipt):
        """Trusted offline maintenance; caller supplies two independent proofs.

        Holding service.lock excludes every active server. An operator attests
        shutdown and settlement, with retained evidence, for the exact fence.
        No endpoint or lease expiry can clear these holds or replay work.
        """
        import time
        required = {'session', 'procedure', 'fence', 'worker_shutdown_evidence', 'effect_settlement_evidence'}
        if type(receipt) is not dict or set(receipt) != required:
            raise ValueError('Reconciliation requires exact identity and shutdown/effect evidence')
        for key in ('worker_shutdown_evidence', 'effect_settlement_evidence'):
            if not isinstance(receipt[key], str) or not receipt[key].strip() or len(receipt[key]) > 2000:
                raise ValueError('Reconciliation evidence must be 1..2000 characters')
        state, _ = self.load()
        if state is None or receipt['session'] != state['id']:
            raise ValueError('Reconciliation session identity differs')
        row = next((p for p in state['procedures'] if p['id'] == receipt['procedure']), None)
        if (row is None or type(receipt['fence']) is not int or row['procedure_fence'] != receipt['fence']
                or (row['status'] not in {'RECOVERY_REQUIRED', 'STARTING', 'RUNNING', 'PAUSING', 'STOPPING'}
                    and not (row['status'] == 'PAUSED' and row['launched']))):
            raise ValueError('Reconciliation procedure fence or recovery state differs')
        row.update(status='CANCELLED', pause_reason='OFFLINE_RECONCILED', has_token=False,
                   uncertain_effects=False, launched=False)
        state['epoch'] += 1
        state['sequence'] += 1
        self.save(state, {'sequence': state['sequence'], 'time': time.time(),
                          'type': 'offline_reconciled', **receipt})
        return {'reconciled': row['id'], 'epoch': state['epoch'], 'automatic_replay': False}

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None
        if not self.guard.closed:
            # Closing a handle releases its OS lock on both supported families.
            self.guard.close()
