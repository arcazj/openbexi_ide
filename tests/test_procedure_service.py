"""Control ownership and durable records are enforced independently of the UI."""
import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from openbexi_runtime.procedure_model import ProcedureRun
from openbexi_runtime.procedure_service import ProcedureService, Handler
from openbexi_runtime.bounded_http import BoundedHTTPServer


class Adapter:
    def __init__(self):
        self.calls = []

    def request(self, command, arguments):
        self.calls.append((command, arguments)); return {}

    def close(self):
        pass


@pytest.fixture
def workspace(tmp_path):
    service = ProcedureService(tmp_path, tmp_path / 'service')
    controller = service.connect(service.operator_key, 'Controller')['client']
    other = service.connect(service.operator_key, 'Other operator')['client']
    monitor = service.connect(service.monitor_key, 'Monitor')['client']
    run = ProcedureRun(tmp_path, tmp_path / 'main.py', 'Run')
    run.status = 'PAUSED'; run.sources[run.script] = 'first\nsecond\n'
    service.records.create(tmp_path, run.script, 'Run', run.identifier)
    run.journal = service.records; run.persist()
    service.runs[run.identifier] = run; service.adapters[run.identifier] = Adapter()
    service.claim(controller, run.identifier)
    yield service, run, controller, other, monitor
    service.close(); service.records.close()


def test_control_claim_monitor_and_stale_prompt_enforced(workspace):
    service, run, controller, other, monitor = workspace
    with pytest.raises(PermissionError): service.claim(monitor, run.identifier)
    with pytest.raises(PermissionError): service.claim(other, run.identifier)
    with pytest.raises(PermissionError): service.command(monitor, run.identifier, 'continue', {})
    with pytest.raises(PermissionError): service.command(monitor, run.identifier, 'evaluate', {'expression': 'danger()'})
    service.command(monitor, run.identifier, 'threads', {})
    assert service.adapters[run.identifier].calls == [('threads', {})]
    run.prompt = {'promptId': 'new', 'choices': [{'label': 'Yes', 'value': '0'}]}
    run.status = 'PROMPT'
    with pytest.raises(ValueError): service.command(controller, run.identifier, 'spell/promptAnswer', {'promptId': 'old', 'value': '0'})
    with pytest.raises(ValueError): service.command(controller, run.identifier, 'spell/promptAnswer', {'promptId': 'new', 'value': 'bad'})
    service.command(controller, run.identifier, 'spell/promptAnswer', {'promptId': 'new', 'value': '0'})
    with pytest.raises(ValueError): service.command(controller, run.identifier, 'spell/promptAnswer', {'promptId': 'new', 'value': '0'})
    assert run.prompt is None


def test_release_and_controller_loss_never_invent_paused(workspace):
    service, run, controller, other, monitor = workspace
    service.claim(controller, run.identifier, release=True); service.claim(other, run.identifier)
    run.status = 'RUNNING'
    with pytest.raises(ValueError): service.claim(other, run.identifier, release=True)
    service.clients[other]['seen'] = time.monotonic() - 100
    service.expire()
    assert run.status == 'RUNNING' and not run.controller
    assert service.adapters[run.identifier].calls[-1] == ('pause', {'threadId': 1})
    service.event(run, {'type': 'event', 'event': 'stopped', 'body': {}})
    assert run.status == 'PAUSED'


def test_service_restart_preserves_source_and_never_resumes(workspace):
    service, run, *_ = workspace
    source = dict(path=str(run.script))
    run.apply(dict(kind='line', source=source, line=1, current=True, details={'SCount': '7'}))
    run.apply(dict(kind='line', source=source, line=1, item='TEMP', value='20', status='SUCCESS', details={'SCount': '7', 'Csp': 'main:1/7'}))
    run.persist()
    restored = ProcedureService(service.project, service.directory)
    try:
        previous = restored.runs[run.identifier]
        assert previous.sources[run.script] == 'first\nsecond\n'
        assert not previous.active and previous.status == 'UNKNOWN' and previous.connection == 'Disconnected'
        assert not restored.adapters
        assert restored.records.events(run.identifier, path=run.script, line=1)[-1]['iteration'] == 7
    finally:
        restored.records.close()


def test_record_retains_all_iterations_and_page_cursor(tmp_path):
    service = ProcedureService(tmp_path, tmp_path / 'state')
    run = ProcedureRun(tmp_path, tmp_path / 'main.py', 'Run'); run.sources[run.script] = 'loop\n'
    run.journal = service.records; service.records.create(tmp_path, run.script, 'Run', run.identifier)
    source = {'path': str(run.script)}
    for number in range(220):
        run.apply(dict(kind='line', source=source, line=1, current=True))
        run.apply(dict(kind='line', source=source, line=1, item='TEMP', value=str(number), status='SUCCESS'))
    first = service.records.events(run.identifier, limit=300)
    second = service.records.events(run.identifier, after=first[-1]['sequence'], limit=300)
    assert len(first) + len(second) == 440
    assert first[-1]['sequence'] < second[0]['sequence']
    assert len(run.history[(run.script, 1)]) == 200 and len(run.raw[(run.script, 1)]) == 200
    assert run.item_rows(run.script, 1)[0]['value'] == '219'
    last = service.records.events(run.identifier, path=run.script, line=1, latest=True)
    assert len(last) == 2 and {event['iteration'] for event in last} == {220}
    service.records.close()


def test_http_authentication_origin_and_host_checks(workspace):
    service, run, controller, _, monitor = workspace
    server = BoundedHTTPServer(('127.0.0.1', 0), Handler)
    server.service = service; server.authority = f'127.0.0.1:{server.server_port}'
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    def get(path='/api/state', headers=None, data=None):
        req = Request('http://' + server.authority + path, headers=headers or {}, data=data)
        return urlopen(req, timeout=3)
    try:
        with pytest.raises(HTTPError) as invalid: get()
        assert invalid.value.code == 403
        headers = {'Authorization': 'Bearer ' + monitor}
        with get(headers=headers) as response:
            snapshot = json.load(response)
        assert snapshot['role'] == 'monitor' and not snapshot['runs'][0]['controlling']
        for extra in ({'Origin': 'https://untrusted.example'}, {'Host': 'untrusted.example'}, {'Sec-Fetch-Site': 'cross-site'}):
            with pytest.raises(HTTPError) as denied: get(headers=headers | extra)
            assert denied.value.code == 403
        with get('/') as response:
            assert b'Procedure instances and history' in response.read()
        with pytest.raises(HTTPError) as denied:
            get('/api/command', headers | {'Content-Type': 'application/json'}, json.dumps(dict(id=run.identifier, command='continue')).encode())
        assert denied.value.code == 403
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_compound_items_merge_and_native_counts_are_preserved(tmp_path):
    run = ProcedureRun(tmp_path, tmp_path / 'main.py', 'Run'); run.sources[run.script] = 'verify\n'
    source = {'path': str(run.script)}
    run.apply(dict(kind='line', source=source, line=1, current=True, details={'SCount': '12'}))
    run.apply(dict(kind='line', source=source, line=1, item='TEMP\4PRESSURE', value='20\x0430',
        status='SUCCESS\4IN PROGRESS', details={'SCount': '12', 'Csp': 'main:1/12', 'ItemReason': 'Waiting for pressure'}))
    assert run.results[run.script][1]['status'] == 'IN PROGRESS (1/2)'
    assert [row['item'] for row in run.item_rows(run.script, 1)] == ['TEMP', 'PRESSURE']
    assert {row['iteration'] for row in run.item_rows(run.script, 1)} == {12}
    run.apply(dict(kind='line', source=source, line=1, item='PRESSURE', value='25', status='SUCCESS', details={'SCount': '12'}))
    assert run.results[run.script][1]['status'] == 'SUCCESS'
    assert run.results[run.script][1]['value'] == '20 | 25'


def test_acknowledgement_reserves_slot_until_native_state(workspace):
    service, run, controller, *_ = workspace
    service.command(controller, run.identifier, 'continue', {'threadId': 1})
    assert run.status == 'PAUSED' and service.pending[run.identifier] == 'continue'
    with pytest.raises(ValueError, match='awaiting native'):
        service.command(controller, run.identifier, 'next', {'threadId': 1})
    service.event(run, dict(type='event', event='continued', body={}))
    assert run.status == 'RUNNING' and run.identifier not in service.pending
    service.command(controller, run.identifier, 'pause', {'threadId': 1})
    assert run.status == 'RUNNING' and service.pending[run.identifier] == 'pause'
    service.event(run, dict(type='event', event='stopped', body={}))
    assert run.status == 'PAUSED' and run.identifier not in service.pending


def test_export_is_a_finite_snapshot_while_execution_continues(workspace):
    import io
    service, run, *_ = workspace
    service.records.append(run.identifier, {'kind': 'output', 'text': 'captured'})
    run.persist()
    service.records.append(run.identifier, {'kind': 'output', 'text': 'later'})
    output = io.StringIO(); service.records.export(run.identifier, output)
    entries = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [entry['event']['text'] for entry in entries[1:]] == ['captured']
