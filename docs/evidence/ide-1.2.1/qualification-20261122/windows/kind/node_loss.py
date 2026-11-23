"""Stop one verified disposable KinD worker during native RUNNING and restore that same node."""

import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import time
import uuid

from openbexi_runtime.spell_server_client import SpellServerClient, SpellServerError


helpers = runpy.run_path(str(Path(__file__).with_name('collect.py')))
cluster = helpers['u']
assert (cluster['CASE_NAME'],cluster['NAMESPACE']) in {('node47','obx-native-node47'),('node47b','obx-native-node47b')}
ns, kube, run = (cluster[name] for name in ('namespace', 'kubectl', 'run'))
healthy, target = cluster['NODES']
case = cluster['CASE']


def stamp(): return datetime.now(timezone.utc).isoformat()


def obj(*args): return json.loads(ns('get', *args, '-o', 'json'))


def snapshot():
    result = {}
    leases = {l['metadata']['name']: l['spec']['renewTime'] for l in json.loads(kube('-n','kube-node-lease','get','leases','-o','json'))['items']}
    for n in json.loads(kube('get','nodes','-o','json'))['items']:
        name = n['metadata']['name']
        condition = next(c for c in n['status']['conditions'] if c['type'] == 'Ready')
        result[name] = {'uid':n['metadata']['uid'],'ready':condition['status'],'reason':condition['reason'],
                        'transition':condition['lastTransitionTime'],'lease_renewed':leases[name],
                        'unschedulable':n['spec'].get('unschedulable',False)}
    return result


def wait_for(test, seconds, description):
    until = time.monotonic()+seconds
    while time.monotonic() < until:
        value = test()
        if value: return value
        time.sleep(.35)
    raise TimeoutError(description)


def container(name):
    item = json.loads(run(['docker','container','inspect',name]).stdout)[0]
    assert item['Name'] == '/'+target
    labels = item['Config']['Labels']
    assert labels['io.x-k8s.kind.cluster'] == 'obxqual2211' and labels['io.x-k8s.kind.role'] == 'worker'
    return {'id':item['Id'],'image':item['Image'],'name':item['Name'],'state':item['State']['Status'],
            'pid':item['State']['Pid'],'exit':item['State']['ExitCode'],'started':item['State']['StartedAt'],'finished':item['State']['FinishedAt']}


def pod(role):
    matches = [p for p in obj('pods','-l','app='+role)['items'] if p['metadata'].get('deletionTimestamp') is None]
    assert len(matches)==1
    item=matches[0]; c=item['status']['containerStatuses'][0]
    return {'name':item['metadata']['name'],'uid':item['metadata']['uid'],'node':item['spec']['nodeName'],
            'container_id':c['containerID'].split('://')[-1],'image':c['imageID']}


def state(limit=None):
    args=['exec','deployment/context','-c','context','--','python','-I','-c',helpers['CHECK_DB'],'/state/context.sqlite3']
    if limit is not None: args.append(str(limit))
    return json.loads(ns(*args))


def observed(client):
    rows=client.read('A','executions')['executions'];assert len(rows)==1
    return {key:rows[0].get(key) for key in ('id','lifecycle','control_state','native_root_result')}


def reserve(owner):
    item=next(p for p in owner.read('A','procedures')['procedures'] if p['procedure_id']=='procedure-01')
    cid=owner.authority('A','session.open',{},key=str(uuid.uuid4()))['connection_id']
    fields={key:item[key] for key in ('procedure_id','source_revision','source_sha256','runtime_image','driver_binding')}
    issued=owner.authority('A','execution.reserve',dict(fields,connection_id=cid),key=str(uuid.uuid4()))
    assert owner.remember_controller('A',issued)
    stale={'execution_id':issued['id'],'connection_id':issued['connection_id'],'connection_generation':issued['connection_generation'],
           'expected_epoch':issued['epoch'],'capability':issued['capability'],'command':'CMD_RUN','target_admission_id':None}
    return issued['id'],stale


def log_event(execution, wanted):
    raw=ns('logs','job/worker-01','-c','worker','--timestamps')
    events=[]; ancestry=[]
    for line in raw.splitlines():
        at,_,message=line.partition(b' ')
        if not message.startswith(b'{'):continue
        row=json.loads(message)
        if row.get('event')=='native-startup-diagnostics':
            ancestry=[{k:p[k] for k in ('executable','pid','ppid')} for p in row['diagnostic']['processes']]
        if row.get('execution_id')==execution and row.get('event') in {'native-ready','native-running','native-finished'}:
            events.append({'time':at.decode(), **{k:row[k] for k in ('event','native_status','execution_id') if k in row}})
    if not any(r['event']==wanted for r in events):return None
    assert not any(r['event']=='native-finished' for r in events)
    return {'events':events,'original_processes':ancestry,'log_sha256':hashlib.sha256(raw).hexdigest()}


def original_processes():
    inspect="""import json
from pathlib import Path
rows=[]
for status in Path('/proc').glob('[0-9]*/status'):
    try: fields=dict(s.split(':',1) for s in status.read_text().splitlines() if ':' in s)
    except (OSError,UnicodeError):continue
    comm=fields['Name'].strip()
    if comm in ('SPELL-Listener','SPELL-Context','SPELL-Executor'):
        rows.append({'executable':comm,'pid':int(fields['Pid']),'ppid':int(fields['PPid'])})
print(json.dumps(rows))
"""
    return json.loads(ns('exec','job/worker-01','-c','worker','--','python3','-I','-c',inspect))


def stage_revocation():
    original=obj('secret','identity-context')
    payload=dict(original['data']); config=json.loads(base64.b64decode(payload['config.json']))
    identities=config['worker_credentials']['identities']
    pin=next(p for p,b in identities.items() if b['slot']=='worker-01'); del identities[pin]
    assert len(identities)==9 and all(b['slot']!='worker-01' for b in identities.values())
    payload['config.json']=base64.b64encode(json.dumps(config).encode()).decode()
    replacement={'apiVersion':'v1','kind':'Secret','metadata':{'name':'identity-context-fenced','namespace':cluster['NAMESPACE']},
                 'type':'Opaque','immutable':True,'data':payload}
    ns('create','-f','-',data=json.dumps(replacement).encode())
    return {'retired_slot':'worker-01','retired_certificate_sha256':pin,'other_worker_bindings':len(identities)}


PING_IDENTITY = """
import json, sys
from pathlib import Path
from openbexi_spell_server.contracts import Fault
from openbexi_spell_server.transport import Route,tls_context
cfg=json.loads(Path('/credentials/config.json').read_text())['assigned']
route=Route(cfg['context_url'],cfg['context_fingerprint'],tls_context(cfg['ca'],cfg['certificate'],cfg['key']))
schema='openbexi.worker-assignment/1'
try:
    result=route.call({'schema':schema,'context_id':cfg['context_id']},path='/v1/worker/assignment',schema=schema)
    assert result=={'assignment':None}
    status=200
except Fault as err:status=err.status
print(json.dumps({'slot':cfg['worker_slot'],'http':status}))
assert status==int(sys.argv[1])
"""


def worker_identity_check(core,slot,status):
    name='identity-check-'+slot
    doc={'apiVersion':'v1','kind':'Pod','metadata':{'name':name,'namespace':cluster['NAMESPACE'],'labels':{'role':'worker','app':name}},
         'spec':{'serviceAccountName':'no-api','automountServiceAccountToken':False,'restartPolicy':'Never','enableServiceLinks':False,
                 'nodeSelector':{'kubernetes.io/hostname':healthy},'securityContext':{'runAsNonRoot':True,'runAsUser':10003,'runAsGroup':10003,
                 'fsGroup':10003,'seccompProfile':{'type':'RuntimeDefault'}},'volumes':[{'name':'creds','secret':{'secretName':'identity-'+slot,'defaultMode':0o440}}],
                 'containers':[{'name':'check','image':core,'imagePullPolicy':'Never','command':['python','-I','-c',PING_IDENTITY,str(status)],
                 'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},
                 'resources':{'requests':{'cpu':'20m','memory':'32Mi'},'limits':{'cpu':'250m','memory':'96Mi'}},
                 'volumeMounts':[{'name':'creds','mountPath':'/credentials','readOnly':True}]}]}}
    ns('create','-f','-',data=json.dumps(doc).encode())
    ns('wait','pod/'+name,'--for=jsonpath={.status.phase}=Succeeded','--timeout=35s')
    return json.loads(ns('logs','pod/'+name))


def main():
    uids=cluster['validate_cluster']()
    deployment=json.loads((case/'deployment.json').read_text());assert deployment['ready']
    identity=container(target); assert identity['state']=='running' and identity['pid']>0
    nodes=snapshot();assert all(n['ready']=='True' for n in nodes.values()) and not nodes[target]['unschedulable']
    services={r:pod(r) for r in ('gateway','listener','context')};original_worker=pod('worker-01')
    assert all(s['node']==healthy for s in services.values()) and original_worker['node']==target
    assert original_worker['image'] in (deployment['oci_refs']['worker'],deployment['oci_refs']['worker'].split('@')[1])
    job=obj('job','worker-01');pvc=obj('pvc','context-state')['metadata']['uid'];original_audit=obj('pvc','audit-worker-01')['metadata']['uid']
    current=json.loads(kube('get','pods','--all-namespaces','--field-selector','spec.nodeName='+target,'-o','json'))['items']
    active=[{'namespace':p['metadata']['namespace'],'name':p['metadata']['name']} for p in current if p['status']['phase'] not in ('Succeeded','Failed')]
    individual=[p for p in active if p['namespace'] not in {'calico-system','kube-system','tigera-operator'}]
    assert individual==[{'namespace':cluster['NAMESPACE'],'name':original_worker['name']}]
    folder=case/'node-loss';folder.mkdir(exist_ok=False)
    report={'passed':False,'phases':{},'images':deployment['oci_refs'],'cluster':cluster['CONTEXT'],'namespace':cluster['NAMESPACE'],
            'source_commit':'47e0cb376dac1e49e1f6745318c0eb3e43b2ec4d','harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    def note(name,data):
        report['phases'][name]={'at':stamp(),**data};(folder/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(name,flush=True)
    owner=SpellServerClient.from_config(case/'clients/alice/connection.json');reader=SpellServerClient.from_config(case/'clients/watch-01/connection.json')
    stopped=False;cordoned=False
    try:
        note('preflight',{'node':identity,'nodes':nodes,'active_pods_on_target':active,'services':services,'worker':original_worker,
             'job_uid':job['metadata']['uid'],'context_pvc_uid':pvc,'audit_pvc_uid':original_audit,'retirement_prepared':stage_revocation()})
        execution,stale=reserve(owner);admit=owner.launch('A',execution,key=str(uuid.uuid4()));assert admit['state']=='ADMITTED'
        ready=wait_for(lambda:log_event(execution,'native-ready'),40,'No native PAUSED')
        direct=original_processes(); tree={p['executable']:p for p in direct}
        assert tree['SPELL-Executor']['ppid']==tree['SPELL-Context']['pid'] and tree['SPELL-Context']['ppid']==tree['SPELL-Listener']['pid']
        kube('cordon',target);cordoned=True
        owner.command('A',execution,'CMD_RUN',key=str(uuid.uuid4()))
        running=wait_for(lambda:log_event(execution,'native-running'),30,'No native RUNNING')
        before=state();assert not before['results'] and before['holds'][0]['execution_id']==execution
        note('running',{'execution':execution,'native':running,'processes_from_live_worker_procfs':direct,'client':observed(reader),'audit_sha256':before['audit_sha256'],
                         'event_count':len(before['events']),'hold':before['holds'],'spent':sum(w['spent'] for w in before['workers'])})
        stopped=True
        run(['docker','stop','--signal','SIGKILL','--timeout','0',identity['id']],timeout=25)
        off=container(identity['id']);assert off['state']=='exited' and off['pid']==0
        during=observed(reader);assert during['id']==execution and during['native_root_result'] is None
        assert all(pod(r)['uid']==s['uid'] for r,s in services.items())
        note('node_stopped',{'node':off,'public_observer':during,'same_service_pods':True})
        def lost():
            values=snapshot();return values if values[target]['ready']!='True' else None
        down=wait_for(lost,125,'Kubernetes did not mark the powered-off node NotReady');assert down[healthy]['ready']=='True'
        assert down[target]['uid']==uids[target] and down[healthy]['uid']==uids[healthy]
        audit_at_loss=state(len(before['events']));assert audit_at_loss['prefix_sha256']==before['audit_sha256'] and not audit_at_loss['results']
        note('node_not_ready',{'nodes':down,'public_observer':observed(reader),'audit_prefix_sha256':audit_at_loss['prefix_sha256'],
                               'unaffected_service_uids':{r:pod(r)['uid'] for r in services}})
        ns('patch','job','worker-01','--type=merge','-p',json.dumps({'spec':{'suspend':True}}))
        cred={'spec':{'template':{'spec':{'volumes':[{'name':'creds','secret':{'secretName':'identity-context-fenced','defaultMode':0o440}}]}}}}
        ns('patch','deployment','context','--type=strategic','-p',json.dumps(cred))
        ns('rollout','status','deployment/context','--timeout=90s',timeout=95)
        replaced=pod('context');assert replaced['node']==healthy and replaced['uid']!=services['context']['uid']
        now=state(len(before['events']));assert now['integrity']=='ok' and now['prefix_sha256']==before['audit_sha256'] and now['holds']==before['holds']
        assert now['workers']==before['workers'] and now['incarnation']!=before['incarnation'] and not now['results']
        post=observed(reader);assert post['id']==execution and post['lifecycle']==post['control_state']=='RECOVERY_REQUIRED' and post['native_root_result'] is None
        try:owner.request('POST','/v1/contexts/A/commands',stale,key=str(uuid.uuid4()))
        except SpellServerError as err:assert err.status==403;stale_result={'http':err.status,'code':err.code}
        else:raise AssertionError('Old controller was accepted after fencing')
        pin_checks=[worker_identity_check(deployment['oci_refs']['core'],slot,status) for slot,status in [('worker-01',403),('worker-02',200)]]
        note('operator_fenced',{'job_suspended':obj('job','worker-01')['spec']['suspend'],'replacement_context':replaced,
             'pvc_uid':obj('pvc','context-state')['metadata']['uid'],'old_controller':stale_result,'worker_identity_checks':pin_checks,
             'old_authority_incarnation':before['incarnation'],'new_authority_incarnation':now['incarnation'],'unchanged_original_prefix':now['prefix_sha256'],
             'old_events':len(before['events']),'new_events':len(now['events']),'hold':now['holds'],'spent':sum(w['spent'] for w in now['workers']),
             'public_observer':post,'old_node_still_stopped':container(identity['id'])['state']=='exited'})
        run(['docker','start',identity['id']],timeout=30)
        kube('wait','node/'+target,'--for=condition=Ready','--timeout=120s',timeout=130)
        def removed():
            old=run(['docker','exec',target,'crictl','inspect',original_worker['container_id']],check=False)
            if old.returncode:
                if b'not found' in old.stderr.lower():return {'state':'removed','container_id':original_worker['container_id']}
                return None
            status=json.loads(old.stdout)['status']
            assert status['labels']['io.kubernetes.pod.uid']==original_worker['uid']
            if status['state']=='CONTAINER_EXITED':return {'state':status['state'],'exit':status['exitCode'],'container_id':original_worker['container_id']}
        old_runtime=wait_for(removed,50,'Old worker runtime did not remain fenced on node return')
        kube('uncordon',target);cordoned=False
        asrun=helpers['audit_volumes']({target:['worker-01']},deployment['oci_refs']['core'])['worker-01']
        for namespace,selector in [('kube-system','k8s-app=kube-proxy'),('calico-system','k8s-app=calico-node')]:
            kube('-n',namespace,'wait','pod','-l',selector,'--field-selector','spec.nodeName='+target,'--for=condition=Ready','--timeout=70s',timeout=75)
        after=snapshot();assert all(n['ready']=='True' for n in after.values()) and not after[target]['unschedulable']
        assert {n:v['uid'] for n,v in after.items()}==uids and after[target]['lease_renewed']!=down[target]['lease_renewed']
        new_node=container(identity['id']);assert new_node['state']=='running' and new_node['pid']>0 and new_node['started']!=identity['started']
        assert obj('pvc','audit-worker-01')['metadata']['uid']==original_audit and obj('pvc','context-state')['metadata']['uid']==pvc
        wait_for(lambda:not any(p['status']['phase'] in ('Pending','Running') for p in obj('pods','-l','app=worker-01')['items']),
                 50,'Terminating worker Pod did not leave the Kubernetes API')
        final=state(len(before['events']));assert final['prefix_sha256']==before['audit_sha256'] and final['holds']==before['holds'] and not final['results']
        assert observed(reader)==post;assert pod('listener')['uid']==services['listener']['uid'] and pod('gateway')['uid']==services['gateway']['uid']
        report['passed']=True
        note('restored',{'original_node':new_node,'nodes':after,'old_worker_runtime':old_runtime,'active_native_worker_pods':0,
             'job_suspended':obj('job','worker-01')['spec']['suspend'],'final_public_observer':post,'retained_asrun_files':asrun,
             'context_pvc_uid':pvc,'audit_pvc_uid':original_audit,'original_audit_prefix_sha256':final['prefix_sha256'],'database_integrity':final['integrity'],
             'public_gateway_and_listener_original_pods':True,'cluster_workloads_ready':['kube-proxy','calico-node']})
    except BaseException as e:
        note('failure',{'error':str(e),'type':type(e).__name__});raise
    finally:
        owner.forget();reader.forget()
        if stopped and container(identity['id'])['state']!='running':
            ns('patch','job','worker-01','--type=merge','-p',json.dumps({'spec':{'suspend':True}}))
            run(['docker','start',identity['id']],timeout=30)
            kube('wait','node/'+target,'--for=condition=Ready','--timeout=120s',timeout=130)
        if cordoned:kube('uncordon',target)


if __name__=='__main__': main()
