"""Explicit installed native driver/isolated worker/real DSS acceptance."""
from contextlib import closing
import threading
import json
import hashlib
import sqlite3
import time
import os
import pytest
from dss.local import create_servers
from openbexi_runtime.cli import request
from test_durable_sessions import git,commit,durable
from test_sessions import connect,claim,wait_for
from openbexi_runtime.execution_release import prepare,read_manifest,docker
from test_execution_sessions import approve


NATIVE_IMAGE = os.environ.get('OPENBEXI_NATIVE_TEST_IMAGE','openbexi-spell-dss:0.4.0')


@pytest.fixture
def dss(tmp_path,monkeypatch):
    runtime,tcp,http = create_servers(tmp_path/'dss.sqlite',0)
    threads = [threading.Thread(target=s.serve_forever) for s in (tcp,http)]
    for thread in threads:
        thread.start()
    monkeypatch.setenv('OPENBEXI_SPELL_SHARED_IMAGE',NATIVE_IMAGE)
    monkeypatch.setenv('OPENBEXI_SPELL_DSS_URL','http://127.0.0.1:' + str(http.server_port))
    monkeypatch.setenv('OPENBEXI_SPELL_DSS_TCP','127.0.0.1:' + str(tcp.server_address[1]))
    try:
        yield runtime
    finally:
        for server in (http,tcp):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(5)
            assert not thread.is_alive()
        runtime.engine.close()


def test_original_native_driver_manager_rpc_binary_command(dss,tmp_path):
    project = tmp_path/'project'
    project.mkdir()
    git(project,'init','-q')
    name = dss.database.telemetry[0]['item_id']
    (project/'main.py').write_text("from spell.lang.functions import Display, Send, GetTM\n"
        "from spell.lang.modifiers import *\nfrom spell.lang.constants import *\n"
        "assert Send(command='CMD1', config={Confirm:False, PromptUser:False})\n"
        f"Display('NATIVE_DSS_TM=' + str(GetTM({name!r}, {{Wait:False}})))\n"
        "Display('NATIVE_DSS_COMPLETE')\n")
    commit(project)
    with durable(project,tmp_path/'authority',lease_seconds=120) as (session,url):
        actor = connect(session,url)
        result = request(url,'/run',dict(epoch=claim(url,actor),script='main.py',language='spell'),actor['token'])
        procedure = session.procedures[result['id']]
        wait_for(lambda:procedure.status in {'COMPLETED','RECOVERY_REQUIRED','FAILED'},timeout=80)
        output = ''.join(e.get('text','') for e in session.events if e.get('procedure') == procedure.id)
        assert procedure.status == 'COMPLETED', (procedure.public(),output)
        assert 'NATIVE_DSS_COMPLETE' in output
        assert dss.engine.state()['core']['commands_executed'] == 1
        evidence = dss.engine.evidence(dss.engine.state()['scenario_id'])
        assert len(evidence['operations']) == 5
        assert all(row['acknowledgement']['execution_id'] == procedure.id for row in evidence['operations'])


def test_original_time_timeouts_reject_invalid_values_and_recover(dss,tmp_path):
    """Native TIME travels through original models, RPC and actual binary DSS."""
    project = tmp_path/'project'
    project.mkdir()
    git(project,'init','-q')
    name = dss.database.telemetry[0]['item_id']
    source = '''from spell.lib.registry import REGISTRY
from spell.lib.adapter.utctime import TIME
from spell.lib.exception import DriverException
from spell.lang.functions import Display, Send, GetTM
from spell.lang.modifiers import Timeout, Wait, Confirm, PromptUser
from openbexi_dss_proxy.tc import descriptor
from spell.utils.grpc_utils import UnpackValue
tm,tc = REGISTRY['TM'],REGISTRY['TC']
item = tm._createTmItem(TM_NAME)
command = tc._createTcItem('CMD1')
for value in (TIME(.000001), TIME(30), .5, 30):
    wire = UnpackValue(descriptor(command,{Timeout:value}).config)
    expected = value.rel() if isinstance(value,TIME) else value
    assert wire['Timeout'] == expected
for invalid in (TIME('2026-01-01'),TIME(0),TIME(-1),TIME(31),True,float('nan'),float('inf'),2**4096):
    for operation in (lambda: tc._sendCommand(command,{Timeout:invalid}),
                      lambda: tm._refreshItem(item,{Timeout:invalid,Wait:False})):
        try: operation()
        except DriverException: pass
        else: raise AssertionError('Invalid timeout reached the service')
assert Send(command='CMD1',config={Timeout:TIME(2),Confirm:False,PromptUser:False})
assert GetTM(TM_NAME,{Timeout:TIME(.25),Wait:False}) is not None
assert tm._refreshItem(item,{Timeout:TIME(30),Wait:False})[1]
Display('NATIVE_TIME_TIMEOUT_PASS')
'''.replace('TM_NAME',repr(name))
    (project/'main.py').write_text(source)
    commit(project)
    with durable(project,tmp_path/'authority',lease_seconds=120) as (session,url):
        actor = connect(session,url)
        epoch = claim(url,actor)
        # Fresh second executor proves the rejected requests leave no recovery
        # hold or lingering original driver state; each run has exactly one TC.
        for expected_commands in (1,2):
            result = request(url,'/run',dict(epoch=epoch,script='main.py',language='spell'),actor['token'])
            procedure = session.procedures[result['id']]
            wait_for(lambda:procedure.status in {'COMPLETED','RECOVERY_REQUIRED','FAILED'},timeout=80)
            output = ''.join(e.get('text','') for e in session.events if e.get('procedure') == procedure.id)
            assert procedure.status == 'COMPLETED',(procedure.public(),output)
            assert 'NATIVE_TIME_TIMEOUT_PASS' in output
            assert dss.engine.state()['core']['commands_executed'] == expected_commands
        receipts = dss.engine.evidence(dss.engine.state()['scenario_id'])['operations']
        assert len(receipts) == 10 and all(row['ingress_delivery_count'] == 1 for row in receipts)


@pytest.mark.parametrize('action',['handoff','revoke'])
def test_native_release_authority_and_alias_admission(dss,tmp_path,action):
    project = tmp_path/'project'
    project.mkdir()
    git(project,'init','-q')
    source = "# @procedure-id 7c476d1e-fc7d-4611-a4a7-3e73fe910963\n"
    source += "from spell.lang.functions import Display,Send\nimport time\nDisplay('AUTHORITY_READY')\ntime.sleep(10)\nassert Send(command='CMD1')\n"
    for name in ('main.py','alias.py'):
        (project/name).write_text(source)
    commit(project)
    image = json.loads(docker('image','inspect',NATIVE_IMAGE))[0]['Id']
    prepared = prepare(project,'main.py',image,tmp_path/'prepared',backend='spell',additional_procedures=['alias.py'])
    manifest,state = read_manifest(prepared['manifest']),tmp_path/'authority'
    approve(state,manifest)
    identifier = None
    with durable(project,state,lease_seconds=120,execution_release=prepared['release']) as (session,url):
        actor,peer,reader = connect(session,url),connect(session,url,'Peer'),connect(session,url,'Reader',True)
        epoch = claim(url,actor)
        with pytest.raises(ValueError,match='read-only'):
            claim(url,reader)
        run = dict(epoch=epoch,script='main.py',language='spell')
        identifier = request(url,'/run',run,actor['token'])['id']
        procedure = session.procedures[identifier]
        wait_for(lambda:any('AUTHORITY_READY' in e.get('text','') for e in session.events),timeout=45)
        with pytest.raises(ValueError,match='already active'):
            request(url,'/run',dict(run,script='alias.py'),actor['token'])
        if action == 'revoke':
            with session.lock:
                session.authority.decide(manifest,approved=False,actor='Qualification',evidence='Synthetic revocation fixture')
            wait_for(lambda:procedure.status == 'RECOVERY_REQUIRED',timeout=15)
            assert dss.engine.state()['core']['commands_executed'] == 0
        else:
            request(url,'/release',{'epoch':epoch},actor['token'])
            wait_for(lambda:procedure.status == 'PAUSED',timeout=15)
            next_epoch = claim(url,peer)
            with pytest.raises(ValueError,match='Stale|controller'):
                request(url,'/resume',dict(epoch=epoch,procedure=identifier),actor['token'])
            assert procedure.owner.inspect()['State']['Paused']
            assert dss.engine.state()['core']['commands_executed'] == 0
            request(url,'/resume',dict(epoch=next_epoch,procedure=identifier),peer['token'])
            wait_for(lambda:procedure.status in {'COMPLETED','RECOVERY_REQUIRED'},timeout=30)
            assert procedure.status == 'COMPLETED',procedure.public()
            assert dss.engine.state()['core']['commands_executed'] == 1
            with closing(sqlite3.connect(state/'driver-effects.sqlite')) as db:
                rows = db.execute('SELECT authority FROM effects WHERE procedure=?',(identifier,)).fetchall()
            assert any(json.loads(row[0])['controller_epoch']==next_epoch for row in rows)
    if action == 'revoke':
        with pytest.raises(ValueError,match='revoked'):
            with durable(project,state,execution_release=prepared['release']):
                pass
        approve(state,manifest)  # Explicit fixture reapproval cannot clear the run's hold.
        with durable(project,state,execution_release=prepared['release']) as (session,url):
            assert session.procedures[identifier].status == 'RECOVERY_REQUIRED'
            assert dss.engine.state()['core']['commands_executed'] == 0


def test_approved_native_execution_uses_readonly_image_and_real_dss(dss,tmp_path):
    project = tmp_path/'project'
    project.mkdir()
    git(project,'init','-q')
    (project/'main.py').write_text("from pathlib import Path\nfrom spell.lang.functions import Send, Display\n"
        "denied=[]\nfor path in ['/release/main.py','/etc/probe','/workspace/probe']:\n"
        "    try: Path(path).write_text('tamper')\n    except OSError: denied.append(path)\n"
        "assert len(denied)==3\nassert Send(command='CMD1')\nDisplay('APPROVED_NATIVE_COMPLETE')\n")
    commit(project)
    image = json.loads(docker('image','inspect',NATIVE_IMAGE))[0]['Id']
    prepared = prepare(project,'main.py',image,tmp_path/'prepared',backend='spell')
    manifest = read_manifest(prepared['manifest'])
    state = tmp_path/'authority'
    approve(state,manifest)
    (project/'main.py').write_text("raise RuntimeError('mutable worktree must not run')\n")
    with durable(project,state,lease_seconds=120,execution_release=prepared['release']) as (session,url):
        actor = connect(session,url)
        result = request(url,'/run',dict(epoch=claim(url,actor),script='main.py',language='spell'),actor['token'])
        procedure = session.procedures[result['id']]
        wait_for(lambda:procedure.status in {'COMPLETED','RECOVERY_REQUIRED','FAILED'},timeout=80)
        output = ''.join(e.get('text','') for e in session.events if e.get('procedure') == procedure.id)
        assert procedure.status == 'COMPLETED',(procedure.public(),output)
        assert 'APPROVED_NATIVE_COMPLETE' in output
        assert procedure.backend['release'] == prepared['release']
        assert dss.engine.state()['core']['commands_executed'] == 1


@pytest.mark.parametrize('fault',['lost_ack','watchdog','pause'])
def test_native_driver_failure_and_freeze_boundaries(dss,tmp_path,fault):
    if fault == 'lost_ack':
        dss.engine.reset('lost-native-ack',faults={'lost_ack':True},expected_epoch=dss.engine.state()['epoch'])
    project = tmp_path/'project'
    project.mkdir()
    git(project,'init','-q')
    text = "from spell.lang.functions import Send, Display\nimport time\nDisplay('READY')\n"
    text += "Send(command='CMD1')\n" if fault == 'lost_ack' else "while True:\n    time.sleep(.02)\n"
    if fault == 'pause':
        name = dss.database.telemetry[0]['item_id']
        text = ("from spell.lang.functions import Display\nfrom spell.lib.registry import REGISTRY\nimport time\n"
            f"item=REGISTRY['TM']._createTmItem({name!r})\nDisplay('READY')\n"
            "while True:\n    REGISTRY['TM']._refreshItem(item,{})\n    time.sleep(.02)\n")
    (project/'main.py').write_text(text)
    commit(project)
    with durable(project,tmp_path/'authority',lease_seconds=120) as (session,url):
        actor = connect(session,url)
        epoch = claim(url,actor)
        result = request(url,'/run',dict(epoch=epoch,script='main.py',language='spell'),actor['token'])
        procedure = session.procedures[result['id']]
        if fault != 'lost_ack':
            wait_for(lambda:any('READY' in e.get('text','') for e in session.events),timeout=45)
        if fault == 'watchdog':
            procedure.owner.heartbeat_done.set()
            wait_for(lambda:procedure.status == 'RECOVERY_REQUIRED',timeout=15)
        elif fault == 'pause':
            request(url,'/pause',dict(epoch=epoch,procedure=procedure.id),actor['token'])
            wait_for(lambda:procedure.status == 'PAUSED',timeout=15)
            time.sleep(5)  # Longer than the independent parent watchdog interval.
            assert procedure.owner.inspect()['State']['Paused']
            request(url,'/resume',dict(epoch=epoch,procedure=procedure.id),actor['token'])
            wait_for(lambda:not procedure.owner.inspect()['State']['Paused'],timeout=15)
            time.sleep(1)
            assert procedure.status == 'RUNNING'
        else:
            wait_for(lambda:procedure.status == 'RECOVERY_REQUIRED',timeout=45)
            assert dss.engine.state()['core']['commands_executed'] == 1
            operations = dss.engine.evidence(dss.engine.state()['scenario_id'])['operations']
            assert all(row['ingress_delivery_count'] == 1 for row in operations)


def test_original_factory_instantiates_every_family_and_uses_native_models(dss,tmp_path,monkeypatch):
    accounts = tmp_path/'simulator-accounts.json'
    accounts.write_text(json.dumps({'qualification':hashlib.sha256(b'simulator-only').hexdigest()}))
    monkeypatch.setenv('OPENBEXI_SPELL_DSS_USERS',str(accounts))
    project = tmp_path/'project'
    project.mkdir()
    git(project,'init','-q')
    (project/'main.py').write_text('''from spell.lib.registry import REGISTRY
from spell.lang.functions import Display
from spell.lib.adapter.utctime import TIME,NOW
from spell.lang.modifiers import Host
for family in ['CONFIG','TM','TC','EV','PCS','MEM','RSC','TASK','RNG','USER','TIME']:
    assert type(REGISTRY[family]).__module__.startswith('openbexi_dss_proxy.')
REGISTRY['EV'].raiseEvent('Native family event')
assert REGISTRY['RSC'].setResource('fixture', 42, False)
assert REGISTRY['RSC'].getResource('fixture', False) == 42
assert REGISTRY['MEM'].createGoldenImage('GENERIC', 'native-snapshot')
assert REGISTRY['MEM'].dataObjectLookup('DSS_STATE', 'JSON')['satellite_id'] == 'GENERIC'
assert REGISTRY['TASK'].checkTask('DSS_CLOCK') == 0
assert REGISTRY['RNG'].enableRanging()
assert REGISTRY['RNG'].startRanging('DSS-BBE-1', 'DSS-ANTENNA-1')
assert REGISTRY['RNG'].getRangingStatus() == 'RANGING'
assert REGISTRY['RNG'].abortRanging()
assert REGISTRY['USER'].login('qualification','simulator-only')
assert REGISTRY['USER'].isLoggedIn('qualification')
assert REGISTRY['USER'].logout('qualification')
assert REGISTRY['PCS']._PCS_ReadyToCommand({}) == 'READY'
item=REGISTRY['PCS']._createPtcItem('CMD1')
result=REGISTRY['PCS']._sendPtcCommand(item,{})
assert result['success'] == [True]
assert item.getIsCompleted() and item.getIsSuccess()
assert TIME(NOW).isAbs()
Display('ALL_NATIVE_DRIVER_FAMILIES_COMPLETE')
''')
    commit(project)
    with durable(project,tmp_path/'authority',lease_seconds=120) as (session,url):
        actor = connect(session,url)
        result = request(url,'/run',dict(epoch=claim(url,actor),script='main.py',language='spell'),actor['token'])
        procedure = session.procedures[result['id']]
        wait_for(lambda:procedure.status in {'COMPLETED','RECOVERY_REQUIRED','FAILED'},timeout=80)
        output = ''.join(e.get('text','') for e in session.events if e.get('procedure') == procedure.id)
        assert procedure.status == 'COMPLETED',(procedure.public(),output)
        assert 'ALL_NATIVE_DRIVER_FAMILIES_COMPLETE' in output
        assert dss.engine.state()['core']['commands_executed'] == 1
