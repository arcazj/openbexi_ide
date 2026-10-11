"""Qualify installed IDE/plugin wheels with real workers and a fresh native DSS.

Run with: python -I scripts/qualify_installed.py --output .qualification/v0.1
The selected interpreter must contain both distributions; editable installs are
not accepted. This script never inserts repository packages into sys.path.
"""
import argparse
from pathlib import Path
import json
import sys
import threading
import time
import uuid

from openbexi_runtime.cli import request
from openbexi_runtime.session import Session
from openbexi_runtime.session_http import SessionServer
import openbexi_runtime
import openbexi_spell_plugin
from dss.local import create_servers

def wait(predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(0.025)
    raise AssertionError('Installed session did not reach expected state')

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=Path('.qualification/v0.1'))
root = parser.parse_args().output.resolve()
root.mkdir(parents=True, exist_ok=True)
project = root / 'installed-project'
project.mkdir(exist_ok=True)
(project/'first.py').write_text("def inner():\n    print('PYTHON café 😀',flush=True)\n    input()\ninner()\n", encoding='utf-8')
(project/'second.py').write_text("from spell.lang import Display, GetTM, BuildTC, Send\nDisplay('SPELL started')\nDisplay(str(GetTM('TM1')))\nSend(BuildTC('CMD1'))\nDisplay('SPELL complete')\n", encoding='utf-8')
runtime, tcp, api = create_servers(root/('installed-dss-'+uuid.uuid4().hex+'.sqlite'), 0)
for server in (tcp, api): threading.Thread(target=server.serve_forever, daemon=True).start()
session = Session(project, dss_url=f'http://127.0.0.1:{api.server_port}')
server = SessionServer(('127.0.0.1',0),session)
threading.Thread(target=server.serve_forever,daemon=True).start()
url=session.worker_url
try:
    assert 'site-packages' in openbexi_runtime.__file__ and 'site-packages' in openbexi_spell_plugin.__file__
    alice=request(url,'/connect',{'name':'Alice','invite':session.developer_invite})
    bob=request(url,'/connect',{'name':'Bob','invite':session.developer_invite})
    reader=request(url,'/connect',{'name':'Reader','invite':session.monitor_invite})
    epoch=request(url,'/claim',{},alice['token'])['epoch']
    first=request(url,'/run',{'script':'first.py','epoch':epoch},alice['token'])['id']
    second=request(url,'/run',{'script':'second.py','language':'spell','epoch':epoch},alice['token'])['id']
    wait(lambda:session.procedures[first].status=='RUNNING' and any(f['function']=='inner' for t in session.procedures[first].stacks.values() for f in t['stack']))
    assert session.procedures[second].status=='PAUSED' and session.procedures[second].process is None
    snapshot=request(url,'/session',token=reader['token'])
    assert any(f['function']=='inner' for t in snapshot['procedures'][0]['threads'] for f in t['stack'])
    try: request(url,'/claim',{},reader['token'])
    except ValueError: pass
    else: raise AssertionError('Monitor claimed controller')
    request(url,'/input',{'epoch':epoch,'procedure':first,'text':'finish'},alice['token'])
    wait(lambda:session.procedures[second].status in {'COMPLETED','FAILED'})
    output=''.join(event.get('text','') for event in session.events)
    assert session.procedures[first].status==session.procedures[second].status=='COMPLETED',output
    assert 'PYTHON café 😀' in output and 'SPELL complete' in output
    assert runtime.engine.state()['core']['commands_executed']==1
    request(url,'/release',{'epoch':epoch},alice['token'])
    newer=request(url,'/claim',{},bob['token'])['epoch']
    assert newer>epoch
    try: request(url,'/stop',{'epoch':epoch,'procedure':'all'},alice['token'])
    except ValueError: pass
    else: raise AssertionError('Old controller was not fenced')
    result={'version':'0.1.0','ide_origin':openbexi_runtime.__file__,'plugin_origin':openbexi_spell_plugin.__file__,
            'checks':['installed headless session','two developers and read-only monitor','real stack','serial Python/SPELL token queue','Unicode output/stdin','actual binary DSS command','controller handoff and stale-command rejection'],
            'dss_commands_executed':1,'passed':True}
    (root/'installed-smoke.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))
finally:
    session.close()
    for target in (server,api,tcp):
        target.shutdown();target.server_close()
    runtime.engine.close()
