"""Toolkit-independent procedure snapshots and bounded live presentation state."""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import uuid

@dataclass(eq=False)
class ProcedureRun:
    project: Path
    script: Path
    mode: str
    started: datetime = field(default_factory=lambda: datetime.now().astimezone())
    status: str = 'Starting'
    active: bool = True
    aborted: bool = False
    root_id: str = ''
    sources: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)
    current: dict = field(default_factory=dict)
    current_path: Path | None = None
    output: str = ''
    prompt: dict | None = None
    answering: bool = False
    error: str = ''
    reminder: bool = False
    identifier: str = field(default_factory=lambda: uuid.uuid4().hex)
    iterations: dict = field(default_factory=dict)
    items: dict = field(default_factory=dict)
    history: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)
    journal: object = None
    connection: str = 'Connected'
    controller: str = ''
    step: str = ''
    exit_code: int | None = None
    service_id: str = ''

    def snapshot(self):
        return dict(id=self.identifier, project=str(self.project), script=str(self.script),
            mode=self.mode, started=self.started.isoformat(), status=self.status,
            active=self.active, aborted=self.aborted, root_id=self.root_id,
            sources={str(k): v for k, v in self.sources.items()},
            results={str(k): v for k, v in self.results.items()},
            current={str(k): v for k, v in self.current.items()},
            current_path=str(self.current_path) if self.current_path else None,
            output=self.output, prompt=self.prompt, step=self.step, connection=self.connection,
            controller=self.controller, exit_code=self.exit_code, error=self.error, answering=self.answering,
            reminder=self.reminder, service_id=self.service_id)

    @classmethod
    def restore(cls, data):
        run = cls(Path(data['project']), Path(data['script']), data['mode'])
        run.identifier = data['id']; run.started = datetime.fromisoformat(data['started'])
        for key in ('status', 'active', 'aborted', 'root_id', 'output', 'prompt', 'step',
                    'connection', 'controller', 'exit_code', 'error', 'answering', 'reminder', 'service_id'):
            if key in data:
                setattr(run, key, data[key])
        run.sources = {Path(k): v for k, v in data.get('sources', {}).items()}
        run.results = {Path(k): {int(n): r for n, r in rows.items()} for k, rows in data.get('results', {}).items()}
        run.current = {Path(k): v for k, v in data.get('current', {}).items()}
        run.current_path = Path(data['current_path']) if data.get('current_path') else None
        return run

    def persist(self):
        if self.journal:
            self.journal.save(self.identifier, self.status, self.active, self.snapshot())

    def item_rows(self, path, line, mode='Latest information'):
        key = (path, line)
        if mode == 'Full':
            return list(self.raw.get(key, []))
        if mode == 'History':
            return list(self.history.get(key, [])) + list(self.items.get(key, {}).values())
        return list(self.items.get(key, {}).values())


    def source_path(self, source):
        raw = source.get('path', '')
        if not raw:
            return None
        path = Path(raw).resolve()
        return path if path.is_relative_to(self.project) else None

    def apply(self, event):
        if not self.active:
            return
        kind = event.get('kind')
        path = self.source_path(event.get('source', {}))
        key = (path, event.get('line'))
        if kind == 'line' and event.get('current') and path in self.sources:
            old = self.items.pop(key, {})
            if old:
                self.history[key] = (self.history.get(key, []) + list(old.values()))[-200:]
            self.iterations[key] = self.iterations.get(key, 0) + 1
        iteration = self.iterations.get(key, 0)
        native_count = (event.get('details') or {}).get('SCount')
        if str(native_count).isdigit():
            iteration = int(native_count)
            self.iterations[key] = iteration
        if self.journal:
            self.journal.append(self.identifier, event, iteration)

        self.root_id = event.get('rootProcedureId') or self.root_id
        if kind == 'source':
            path = self.source_path(event.get('source', {}))
            if path is None:
                return
            offset = event.get('offset', 0)
            previous = '' if offset == 0 else self.sources.get(path, '')
            # Never concatenate reordered chunks or display unbounded source.
            if offset == len(previous) and len(previous) + len(event['text']) <= 2 * 1024 * 1024:
                self.sources[path] = previous + event['text']
        elif kind == 'line':
            path = self.source_path(event.get('source', {}))
            line = event.get('line')
            if path not in self.sources or type(line) is not int or not 1 <= line <= len(self.sources[path].splitlines()):
                return
            row = self.results.setdefault(path, {}).setdefault(line, {})
            if event.get('current'):
                self.current[path] = line
                self.current_path = path
                row.setdefault('status', 'Reached')
            if event.get('status') or event.get('item') or event.get('value'):
                detail = dict(event.get('details') or {})
                items = self.items.setdefault(key, {})
                values = notification_items(event, iteration)
                for value in values:
                    identity = (str(value['item']), str(detail.get('ItemType', '')))
                    items[identity] = value
                row.update(values[-1])
                if len(items) > 1:
                    entries = list(items.values())
                    row['item'] = ' | '.join(str(v['item']) for v in entries)
                    row['value'] = ' | '.join(str(v['value']) for v in entries)
                    successes = sum(v['status'] == 'SUCCESS' for v in entries)
                    row['status'] = ('FAILED' if any(v['status'] in {'FAILED', 'ERROR'} for v in entries)
                        else 'SUCCESS' if successes == len(entries) else f'IN PROGRESS ({successes}/{len(entries)})')
                self.raw[key] = (self.raw.get(key, []) + [dict(event, iteration=iteration)])[-200:]

            elif not row.get('timestamp'):
                row['timestamp'] = event.get('timestamp', '')
        elif kind == 'status':
            if event.get('procedureId') == self.root_id:
                self.status = event.get('status') or self.status
            if (self.prompt and event.get('procedureId') == self.prompt.get('procedureId')
                    and event.get('status') != 'PROMPT'):
                self.prompt = None
                self.answering = False
        elif kind == 'prompt':
            self.prompt = dict(event)
            self.answering = self.reminder = False
            self.error = ''
        elif kind == 'promptClosed' and self.prompt and event.get('promptId') == self.prompt.get('promptId'):
            self.prompt = None
            self.answering = False
        elif kind == 'reminder' and self.prompt and event.get('promptId') in ('', None, self.prompt.get('promptId')):
            self.reminder = True



def notification_items(event, iteration):
    """Expand native compound fields without dropping partial item updates."""
    details = event.get('details') or {}
    fields = {key: str(event.get(key, '')).split('\4') for key in ('item', 'value', 'status')}
    count = max(map(len, fields.values()))
    result = []
    for index in range(count):
        row = {}
        for key, parts in fields.items():
            row[key] = parts[index] if index < len(parts) else parts[0] if key == 'status' and len(parts) == 1 else ''
        row.update(iteration=iteration, timestamp=event.get('timestamp', ''),
            stack=details.get('Csp', details.get('Stack', '')),
            comments=details.get('ItemReason', details.get('Comments', details.get('Comment', ''))),
            details=details)
        result.append(row)
    return result
