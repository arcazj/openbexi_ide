"""Delayed lease replies cannot revoke or restore a different controller fence."""
import pytest

from openbexi_ide.session_client import SessionClient


@pytest.mark.parametrize('new_epoch', [None, 3])
@pytest.mark.parametrize('failure', [False, True])
def test_delayed_renew_does_not_replace_release_or_reclaimed_control(app, new_epoch, failure):
    client = SessionClient()
    client.state = 'joined'
    client.healthy = True
    client.identity = {'role':'developer', 'client':'alice'}
    client.snapshot = {'epoch':3, 'controller':{'id':'alice'}}
    client.epoch = new_epoch
    client._pending.add('renew')
    errors = []
    client.error.connect(errors.append)
    job = {'generation':client._generation, 'kind':'renew', 'body':{'epoch':1}}
    result = {'job':job, 'error':'Stale or missing controller token', 'http_status':409} if failure else {
        'job':job, 'value':{'epoch':1, 'lease_seconds':1.2}}
    client._receive(result)
    assert client.epoch == new_epoch
    assert client.healthy and not errors
    assert client.can_control is (new_epoch == 3)
    assert 'renew' not in client._pending


def test_current_renew_failure_still_disables_control(app):
    client = SessionClient()
    client.state = 'joined'
    client.healthy = True
    client.identity = {'role':'developer', 'client':'alice'}
    client.snapshot = {'epoch':3, 'controller':{'id':'alice'}}
    client.epoch = 3
    client._receive({'job':{'generation':client._generation, 'kind':'renew', 'body':{'epoch':3}},
                     'error':'Stale or missing controller token', 'http_status':409})
    assert client.epoch is None and not client.healthy and not client.can_control
