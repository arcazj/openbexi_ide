"""Read-only verification of a previously powered-off and restored disposable worker node."""

import hashlib
import json
from pathlib import Path
import runpy

from openbexi_runtime.spell_server_client import SpellServerClient


def main():
    h=runpy.run_path(str(Path(__file__).with_name('node_loss.py')))
    cluster,ns,kube,run=(h[key] for key in ('cluster','ns','kube','run'))
    obj=h['obj']; target,healthy=h['target'],h['healthy']
    folder=cluster['CASE']/'node-loss'; raw=folder/'result.json'
    source=json.loads(raw.read_text());phases=source['phases']
    baseline=phases['preflight']; lost=phases['node_not_ready']; fence=phases['operator_fenced']; active=phases['running']
    assert phases['node_stopped']['node']['pid']==0 and phases['node_stopped']['node']['exit']==137
    assert lost['nodes'][target]['ready']=='Unknown' and lost['nodes'][healthy]['ready']=='True'
    assert baseline['retirement_prepared']['retired_slot']=='worker-01' and fence['old_node_still_stopped']
    assert fence['worker_identity_checks']==[{'slot':'worker-01','http':403},{'slot':'worker-02','http':200}] and fence['old_controller']['http']==403
    old_node=baseline['node']; actual=h['container'](old_node['id']);uids=cluster['validate_cluster']()
    nodes=h['snapshot']();assert all(n['ready']=='True' and n['uid']==uids[name] for name,n in nodes.items())
    assert not nodes[target]['unschedulable'] and nodes[target]['lease_renewed']!=lost['nodes'][target]['lease_renewed']
    assert actual['id']==old_node['id'] and actual['state']=='running' and actual['pid']>0 and actual['started']!=old_node['started']
    previous=baseline['worker'];cr=json.loads(run(['docker','exec',target,'crictl','ps','-a','-o','json']).stdout)['containers']
    native=[c for c in cr if c['labels'].get('io.kubernetes.pod.uid')==previous['uid'] and c['metadata']['name']=='worker']
    assert all(c['state']=='CONTAINER_EXITED' for c in native) and not any(c['metadata']['attempt'] for c in native)
    status=run(['docker','exec',target,'crictl','inspect',previous['container_id']],check=False)
    if status.returncode:
        assert b'not found' in status.stderr.lower(); old_runtime={'state':'removed','id':previous['container_id']}
    else:
        record=json.loads(status.stdout)['status']; assert record['state']=='CONTAINER_EXITED'
        old_runtime={k:record[k] for k in ('id','state','exitCode','startedAt','finishedAt')}
    assert obj('job','worker-01')['spec']['suspend'] and obj('job','worker-01')['metadata']['uid']==baseline['job_uid']
    h['wait_for'](lambda:not any(p['status']['phase'] in ('Pending','Running') for p in obj('pods','-l','app=worker-01')['items']),
                  50,'Original Kubernetes Pod is still terminating')
    ready={}
    for namespace,selector in [('kube-system','k8s-app=kube-proxy'),('calico-system','k8s-app=calico-node')]:
        pods=json.loads(kube('-n',namespace,'get','pods','-l',selector,'--field-selector','spec.nodeName='+target,'-o','json'))['items']
        assert len(pods)==1 and any(c['type']=='Ready' and c['status']=='True' for c in pods[0]['status']['conditions'])
        ready[selector]=pods[0]['metadata']['uid']
    readback=obj('pod','audit-readback-0');assert readback['status']['phase']=='Succeeded' and readback['spec']['nodeName']==target
    assert readback['spec']['containers'][0]['volumeMounts'][0]['readOnly']
    asrun=json.loads(ns('logs','pod/audit-readback-0'))['worker-01']
    assert obj('pvc','audit-worker-01')['metadata']['uid']==baseline['audit_pvc_uid'] and obj('pvc','context-state')['metadata']['uid']==baseline['context_pvc_uid']
    assert not any(p['status']['phase'] in ('Pending','Running') for p in obj('pods','-l','app=worker-01')['items'])
    assert h['pod']('gateway')['uid']==baseline['services']['gateway']['uid'] and h['pod']('listener')['uid']==baseline['services']['listener']['uid']
    assert h['pod']('context')['uid']==fence['replacement_context']['uid']
    durable=h['state'](active['event_count']);assert durable['integrity']=='ok' and durable['prefix_sha256']==active['audit_sha256']
    assert durable['holds']==active['hold'] and sum(w['spent'] for w in durable['workers'])==1 and not durable['results']
    reader=SpellServerClient.from_config(cluster['CASE']/'clients/watch-01/connection.json')
    try: row=h['observed'](reader)
    finally:reader.forget()
    assert row==fence['public_observer'] and row['lifecycle']==row['control_state']=='RECOVERY_REQUIRED' and not row['native_root_result']
    result={'passed':True,'at':h['stamp'](),'source_commit':source['source_commit'],'case':cluster['NAMESPACE'],'execution':active['execution'],
        'original_node':actual,'node_identities_after':nodes,'retired_worker_cri':old_runtime,'runtime_attempts':[{'state':c['state'],'attempt':c['metadata']['attempt']} for c in native],
        'remaining_live_native_pods':0,'job_suspended':True,'original_job_uid':baseline['job_uid'],'core_daemons_ready_on_return':ready,
        'same_public_gateway_and_listener_pods':True,'context_pvc_uid':baseline['context_pvc_uid'],'audit_pvc_uid':baseline['audit_pvc_uid'],
        'asrun_read_from_restored_worker_node':asrun,'readback_pod_uid':readback['metadata']['uid'],'public_observer':row,'held_reservation':durable['holds'],
        'old_audit_events':active['event_count'],'original_audit_prefix_sha256':durable['prefix_sha256'],'database_integrity':durable['integrity'],
        'durable_terminal_results':len(durable['results']),'spent_incarnations':sum(w['spent'] for w in durable['workers']),
        'node_trial_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'verification_harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    target_path=folder/'restoration.json';target_path.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'passed':True,'node':actual['name'],'phase':row['lifecycle'],'asrun':len(asrun)}))


if __name__=='__main__':main()
