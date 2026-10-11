from openbexi_runtime.cli import request
from test_sessions import serving, connect, claim, script, submit, wait_for


def test_blocked_input_has_current_stack_and_can_complete_requested_pause(tmp_path):
    script(tmp_path, 'first.py', "def inner():\n    value=input()\n    print('after-input',flush=True)\ninner()\n")
    script(tmp_path, 'second.py')
    with serving(tmp_path) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        first_id, second_id = submit(url, actor, epoch, 'first.py'), submit(url, actor, epoch, 'second.py')
        first, second = session.procedures[first_id], session.procedures[second_id]
        wait_for(lambda: any(f['function'] == 'inner' and f['line'] == 2 for t in first.stacks.values() for f in t['stack']))
        request(url, '/pause', {'epoch': epoch, 'procedure': first_id}, actor['token'])
        assert first.status == 'PAUSING' and first.has_token
        request(url, '/input', {'epoch': epoch, 'procedure': first_id, 'text': 'finish waiting'}, actor['token'])
        wait_for(lambda: first.status == 'PAUSED' and second.status == 'RUNNING')
        assert 'after-input' not in ''.join(e.get('text', '') for e in session.events)


def test_large_primitive_local_is_bounded_without_breaking_execution(tmp_path):
    script(tmp_path, 'big.py', "import time\ndef inner():\n    big=1<<20000\n    time.sleep(0.5)\n    print('finished')\ninner()\n")
    with serving(tmp_path) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        identifier = submit(url, actor, epoch, 'big.py')
        procedure = session.procedures[identifier]
        wait_for(lambda: any(f['locals'].get('big') == '<large int>' for t in procedure.stacks.values() for f in t['stack']))
        wait_for(lambda: procedure.status == 'COMPLETED')
        assert procedure.exit_code == 0
