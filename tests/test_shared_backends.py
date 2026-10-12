from types import SimpleNamespace
import threading

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
