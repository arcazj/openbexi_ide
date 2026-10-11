from openbexi_runtime.cli import request
from test_sessions import serving, connect, claim, script, submit, wait_for


def test_snapshot_does_not_call_custom_metaclass_properties(tmp_path):
    script(tmp_path, 'objects.py', "import time\nfrom pathlib import Path\nclass Meta(type):\n    def __getattribute__(cls,name):\n        if name=='__name__':\n            Path('inspector-called-user-code').write_text('bad')\n        return super().__getattribute__(name)\nclass Value(metaclass=Meta): pass\ndef inner():\n    value=Value()\n    time.sleep(0.5)\ninner()\n")
    with serving(tmp_path) as (session, url):
        actor = connect(session, url)
        epoch = claim(url, actor)
        identifier = submit(url, actor, epoch, 'objects.py')
        procedure = session.procedures[identifier]
        wait_for(lambda: any(f['locals'].get('value') == '<object>' for t in procedure.stacks.values() for f in t['stack']))
        wait_for(lambda: procedure.status == 'COMPLETED')
        assert not (tmp_path/'inspector-called-user-code').exists()
