"""Durable execution records and paged item history, without GUI dependencies.

This is an as-run record, not a resumable checkpoint. Every received neutral
notification is preserved; merging for the Latest and History views does not
discard the Full record. Prompt answers are deliberately never stored here.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
import uuid


class ProcedureRecords:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        with self.db:
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, project TEXT NOT NULL, script TEXT NOT NULL,
                    mode TEXT NOT NULL, started TEXT NOT NULL, status TEXT NOT NULL,
                    active INTEGER NOT NULL, snapshot TEXT NOT NULL DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, run TEXT NOT NULL,
                    path TEXT NOT NULL, line INTEGER, iteration INTEGER, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS events_line ON events(run, path, line, seq);
            ''')

    def create(self, project, script, mode, identifier=None):
        identifier = identifier or uuid.uuid4().hex
        with self.lock, self.db:
            self.db.execute('INSERT INTO runs(id,project,script,mode,started,status,active) VALUES(?,?,?,?,?,?,1)',
                (identifier, str(project), str(script), mode, datetime.now(timezone.utc).isoformat(), 'LOADED'))
        return identifier

    def append(self, identifier, event, iteration=0):
        raw_path = event.get('source', {}).get('path', '')
        path = str(Path(raw_path).resolve()) if raw_path else ''
        with self.lock, self.db:
            cursor = self.db.execute('INSERT INTO events(run,path,line,iteration,payload) VALUES(?,?,?,?,?)',
                (identifier, path, event.get('line'), iteration,
                 json.dumps(event, ensure_ascii=False, allow_nan=False)))
            return cursor.lastrowid

    def save(self, identifier, status, active, snapshot):
        with self.lock, self.db:
            sequence = self.db.execute('SELECT COALESCE(MAX(seq),0) FROM events WHERE run=?', (identifier,)).fetchone()[0]
            self.db.execute('UPDATE runs SET status=?,active=?,snapshot=? WHERE id=?',
                (status, bool(active), json.dumps(dict(snapshot, last_sequence=sequence), ensure_ascii=False, allow_nan=False), identifier))

    def recent(self, project, limit=100):
        with self.lock:
            rows = self.db.execute('SELECT id,script,mode,started,status,active,snapshot FROM runs '
                'WHERE project=? ORDER BY started DESC LIMIT ?', (str(project), min(100, limit))).fetchall()
        return [dict(id=r[0], script=r[1], mode=r[2], started=r[3], status=r[4], active=bool(r[5]),
                     snapshot=json.loads(r[6])) for r in rows]

    def events(self, identifier, *, after=0, limit=500, path=None, line=None, latest=False, until=None):
        query = 'SELECT seq,iteration,payload FROM events WHERE run=? AND seq>?'
        args = [identifier, after]
        if until is not None:
            query += ' AND seq<=?'; args.append(until)
        if path is not None:
            path = str(Path(path).resolve())
            query += ' AND path=?'; args.append(path)
        if line is not None:
            query += ' AND line=?'; args.append(line)
        if latest and path is not None and line is not None:
            query += ' AND iteration=(SELECT MAX(iteration) FROM events WHERE run=? AND path=? AND line=?)'
            args += [identifier, str(path), line]
        query += ' ORDER BY seq LIMIT ?'; args.append(min(2000, max(1, limit)))
        with self.lock:
            rows = self.db.execute(query, args).fetchall()
        return [dict(sequence=r[0], iteration=r[1], event=json.loads(r[2])) for r in rows]

    def snapshot(self, identifier):
        with self.lock:
            row = self.db.execute('SELECT snapshot FROM runs WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise ValueError('Unknown procedure record')
        return json.loads(row[0])

    def close(self):
        with self.lock:
            self.db.close()

    def export(self, identifier, stream):
        snapshot = self.snapshot(identifier)
        stream.write(json.dumps({'schema': 'openbexi.as-run/1', 'snapshot': snapshot}, ensure_ascii=False) + '\n')
        cursor = 0
        while entries := self.events(identifier, after=cursor, limit=500, until=snapshot.get('last_sequence')):
            for entry in entries:
                stream.write(json.dumps(entry, ensure_ascii=False) + '\n')
            cursor = entries[-1]['sequence']
