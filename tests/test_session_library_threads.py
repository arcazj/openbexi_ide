import time

from openbexi_runtime.cli import request
from test_sessions import serving, connect, claim, script, submit, wait_for


def test_untraced_library_thread_keeps_token_until_it_finishes(tmp_path):
    script(tmp_path, 'first.py', "import threading,time\ntimer=threading.Timer(0.8,print,args=('timer-finished',))\ntimer.start()\nfor number in range(500):\n    time.sleep(0.02)\n")
    script(tmp_path, 'second.py')
    with serving(tmp_path) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        first_id, second_id = submit(url, actor, epoch, 'first.py'), submit(url, actor, epoch, 'second.py')
        first, second = session.procedures[first_id], session.procedures[second_id]
        wait_for(lambda: len(first.stacks) >= 2)
        request(url, '/pause', {'epoch': epoch, 'procedure': first_id}, actor['token'])
        time.sleep(0.15)
        assert first.status == 'PAUSING' and first.has_token and second.process is None
        wait_for(lambda: first.status == 'PAUSED' and second.status == 'RUNNING')
        assert 'timer-finished' in ''.join(e.get('text', '') for e in session.events)
