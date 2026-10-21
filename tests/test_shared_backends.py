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


def test_pause_racing_request_admission_keeps_quiescence_without_a_recovery_hold(tmp_path, monkeypatch):
    """Schedule pause in the former gap between the state check and dispatch."""
    from openbexi_runtime import source_capture
    admitted, pausing, paused = threading.Event(), threading.Event(), threading.Event()
    effects, events = [], []
    session = SimpleNamespace(id='a'*32, lock=threading.RLock(), closed=threading.Event(),
        controller='operator', deadline=time.monotonic()+30, fences={'logical':1}, epoch=1,
        store=SimpleNamespace(directory=tmp_path), _expire=lambda:None, _dispatch=lambda:None,
        event=lambda name,**kw:events.append(name))
    class Owner:
        process = SimpleNamespace(pid=1)
        delivered = False
        def start(self): pass
        def resume(self): pass
        def pause(self): paused.set()
        def close(self): pass
        def poll(self):
            time.sleep(.005)
            if not self.delivered:
                self.delivered = True
                return {'type':'backend_request'}
        def handle_request(self, event, identity, check):
            check()
            effects.append(identity['controller_epoch'])
    owner = Owner()
    monkeypatch.setattr(source_capture, 'verify_capture', lambda *a:None)
    monkeypatch.setattr(shared_backends, 'load_backend', lambda name:SimpleNamespace(create=lambda *a,**k:owner))
    original = shared_backends.dispatch_request
    def interleaved(*args):
        admitted.set()
        assert pausing.wait(5)
        time.sleep(.1)  # Give the competing pause thread time to acquire/wait for the lock.
        return original(*args)
    monkeypatch.setattr(shared_backends, 'dispatch_request', interleaved)
    procedure = SimpleNamespace(id='b'*32, language='fixture', backend={}, release=None,
        spec=SimpleNamespace(project=tmp_path, arguments=()), script='main.py', capture_digest='c'*64,
        definition='logical', version='d'*64, fence=1, has_token=True, wants_run=True,
        status='STARTING', cancelled=False, uncertain=False, error=None, owner=None,
        input_queue=__import__('queue').Queue(), reason=None)
    worker = threading.Thread(target=shared_backends.execute, args=(session, procedure))
    procedure.thread = worker
    def pause():
        assert admitted.wait(5)
        pausing.set()
        with session.lock:
            procedure.status, procedure.wants_run = 'PAUSING', False
            session.event('pause_requested')
    controller = threading.Thread(target=pause)
    worker.start(); controller.start()
    try:
        assert paused.wait(5)
        controller.join(5)
        with session.lock:
            assert procedure.status == 'PAUSED' and not procedure.has_token
            assert not procedure.uncertain and procedure.error is None
            assert effects == [1]
            assert events.index('backend_request_completed') < events.index('pause_requested')
    finally:
        session.closed.set()
        worker.join(5); controller.join(5)
        assert not worker.is_alive() and not controller.is_alive()
