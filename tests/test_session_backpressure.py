import time

import pytest

from openbexi_runtime.cli import request
from test_sessions import serving, connect, claim, script, submit, wait_for


def test_nonreading_input_cannot_block_session_control(tmp_path):
    script(tmp_path, 'busy.py')
    with serving(tmp_path) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        identifier = submit(url, actor, epoch, 'busy.py')
        wait_for(lambda: session.procedures[identifier].status == 'RUNNING')
        for index in range(64):
            try:
                request(url, '/input', {'epoch': epoch, 'procedure': identifier, 'text': 'x' * 8000}, actor['token'])
            except ValueError as error:
                assert 'queue is full' in str(error)
                break
        else:
            pytest.fail('Nonreading input was not bounded')
        before = time.monotonic()
        assert request(url, '/session', token=actor['token'])['controller']
        request(url, '/stop', {'epoch': epoch, 'procedure': identifier}, actor['token'])
        wait_for(lambda: session.procedures[identifier].status == 'CANCELLED')
        assert time.monotonic() - before < 3
