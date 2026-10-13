from types import SimpleNamespace
import threading
import time

import pytest

from openbexi_runtime import shared_backends


def test_missing_duplicate_and_incompatible_providers_fail_closed(monkeypatch):
    monkeypatch.setattr(shared_backends, 'entry_points', lambda **_: [])
    with pytest.raises(ValueError, match='exactly one'):
        shared_backends.load_backend('example')
    entry = SimpleNamespace(load=lambda: SimpleNamespace(api=2))
    monkeypatch.setattr(shared_backends, 'entry_points', lambda **_: [entry, entry])
    with pytest.raises(ValueError, match='exactly one'):
        shared_backends.load_backend('example')
    monkeypatch.setattr(shared_backends, 'entry_points', lambda **_: [entry])
    with pytest.raises(ValueError, match='Unsupported'):
        shared_backends.load_backend('example')


def test_runtime_binding_is_bounded_detached_json(monkeypatch):
    source = {'runtime': {'image': 'immutable image'}}
    provider = SimpleNamespace(bind=lambda: source)
    monkeypatch.setattr(shared_backends, 'load_backend', lambda _: provider)
    binding = shared_backends.bind_backend('example')
    source['runtime']['image'] = 'different image'
    assert binding['runtime']['image'] == 'immutable image'
    source['extra'] = 'x' * 8192
    with pytest.raises(ValueError, match='Invalid'):
        shared_backends.bind_backend('example')


def test_superseded_launch_attempt_cannot_close_current_worker():
    closed = []
    current_owner = SimpleNamespace(close=lambda: closed.append(True))
    session = SimpleNamespace(lock=threading.RLock(), closed=threading.Event())
    procedure = SimpleNamespace(has_token=True, thread=threading.Thread(), owner=current_owner)
    shared_backends.execute(session, procedure)
    assert procedure.owner is current_owner and not closed


@pytest.mark.parametrize('lost', ['closed','controller','lease','slot','intent','state','fence','revocation'])
def test_private_request_rechecks_authority_before_each_effect(lost):
    calls = []
    revoked = []
    def require(release):
        if revoked:
            raise PermissionError('Revoked fixture release')
    session = SimpleNamespace(id='a'*32, lock=threading.RLock(), closed=threading.Event(),
        controller='controller', deadline=time.monotonic()+10, fences={'logical':2}, epoch=3,
        authority=SimpleNamespace(require=require), event=lambda *a,**k:None)
    procedure = SimpleNamespace(id='b'*32, cancelled=False, has_token=True, wants_run=True,
        status='RUNNING', definition='logical', fence=2, version='version', release='c'*64)
    def handler(event,identity,check):
        assert identity['controller_epoch'] == 3 and identity['procedure_fence'] == 2
        assert identity['mode'] == 'Execution' and identity['release'] == 'c'*64
        check()
        calls.append('first authorized write')
        if lost == 'closed': session.closed.set()
        elif lost == 'controller': session.controller = None
        elif lost == 'lease': session.deadline = 0
        elif lost == 'slot': procedure.has_token = False
        elif lost == 'intent': procedure.wants_run = False
        elif lost == 'state': procedure.status = 'PAUSING'
        elif lost == 'fence': session.fences['logical'] = 4
        else: revoked.append(True)
        check()
        calls.append('forbidden write')
    procedure.owner = SimpleNamespace(handle_request=handler)
    with pytest.raises(PermissionError):
        shared_backends.dispatch_request(session,procedure,{'type':'backend_request'})
    assert calls == ['first authorized write']
