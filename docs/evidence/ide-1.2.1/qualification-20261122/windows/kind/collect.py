"""Cross-check native Jobs, logs, restrictive Pod specs and durable volumes after completion."""

from datetime import datetime
import hashlib
import json
from pathlib import Path
import runpy
import time

u=runpy.run_path(str(Path(__file__).with_name("cluster.py")))
ns=u["namespace"]
CHECK_DB="""
import hashlib,json,sqlite3,sys
from pathlib import Path
db=sqlite3.connect(Path(sys.argv[1]).as_uri()+'?mode=ro',uri=True)
db.row_factory=sqlite3.Row
def rows(q):return [dict(r) for r in db.execute(q)]
hashes=hashlib.sha256()
events=[]
for row in db.execute('select sequence,type,body from events order by sequence'):
    hashes.update(json.dumps(list(row),ensure_ascii=False,separators=(',',':')).encode()+b'\\n')
    events.append([row[0],row[1]])
limit=int(sys.argv[2]) if len(sys.argv)>2 else len(events)
prefix=hashlib.sha256()
for row in db.execute('select sequence,type,body from events where sequence<=? order by sequence',(limit,)):
    prefix.update(json.dumps(list(row),ensure_ascii=False,separators=(',',':')).encode()+b'\\n')
print(json.dumps(dict(integrity=db.execute('pragma integrity_check').fetchone()[0],
    incarnation=db.execute("select value from meta where name='incarnation'").fetchone()[0],
    audit_sha256=hashes.hexdigest(),prefix_sha256=prefix.hexdigest(),events=events,
    executions=rows('select id,procedure_id,owner,worker_slot,worker_incarnation,lifecycle,control_state from executions order by procedure_id'),
    workers=rows('select slot,incarnation,spent from workers order by slot'),
    holds=rows('select procedure_id,execution_id from reservations order by procedure_id'),
    natives=rows('select execution_id,instance_id,pid,executable_sha256,state from native_members order by execution_id'),
    results=rows('select execution_id,native_status from assigned_native_results order by execution_id'))))
"""
READ_AUDIT="""
import hashlib,json,sys
from pathlib import Path
root=Path('/audits');result={}
for volume in sorted(root.iterdir()):
    result[volume.name]=[dict(name=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                        for p in sorted(volume.rglob('*.ASRUN')) if p.is_file()]
print(json.dumps(result))
"""


def object_json(*args):
    return json.loads(ns("get",*args,"-o","json"))


def audit_volumes(groups, core):
    scanned={}
    for index,(node,names) in enumerate(sorted(groups.items())):
        name="audit-readback-"+str(index)
        vols=[{"name":w,"persistentVolumeClaim":{"claimName":"audit-"+w,"readOnly":True}} for w in names]
        mounts=[{"name":w,"mountPath":"/audits/"+w,"readOnly":True} for w in names]
        doc={"apiVersion":"v1","kind":"Pod","metadata":{"name":name,"namespace":u["NAMESPACE"],"labels":{"role":"offline-readback"}},
             "spec":{"restartPolicy":"Never","automountServiceAccountToken":False,"serviceAccountName":"no-api",
                     "enableServiceLinks":False,"nodeSelector":{"kubernetes.io/hostname":node},
                     "securityContext":{"runAsNonRoot":True,"runAsUser":10003,"runAsGroup":10003,"seccompProfile":{"type":"RuntimeDefault"}},
                     "containers":[{"name":"read","image":core,"imagePullPolicy":"Never","command":["python","-I","-c",READ_AUDIT],
                                    "securityContext":{"readOnlyRootFilesystem":True,"allowPrivilegeEscalation":False,"capabilities":{"drop":["ALL"]}},
                                    "resources":{"limits":{"cpu":"250m","memory":"64Mi"},"requests":{"cpu":"25m","memory":"16Mi"}},"volumeMounts":mounts}],
                     "volumes":vols}}
        if not ns("get","pod",name,"--ignore-not-found","-o","name").strip():
            ns("create","-f","-",data=json.dumps(doc).encode())
        ns("wait","pod/"+name,"--for=jsonpath={.status.phase}=Succeeded","--timeout=35s")
        scanned.update(json.loads(ns("logs","pod/"+name)))
    return scanned


def main():
    nodes=u["validate_cluster"]()
    path=u["CASE"]; run=path/("probe" if u["CASE_NAME"] in {"cohort2","final47"} else "single")
    proof=json.loads((run/"result.json").read_text());assert proof["passed"]
    deployment=json.loads((path/"deployment.json").read_text())
    evidence={"passed":False,"context":u["CONTEXT"],"namespace":u["NAMESPACE"],"node_uids":nodes,
              "harness_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"pods":{}}
    expected=set(proof["ten_public_reservations"].values()) if "ten_public_reservations" in proof else {proof["reservation"]["execution_id"]}
    workers=object_json("pods","-l","role=worker")["items"]
    assert len(workers)==len(expected)
    starts=[];ends=[];groups={};observed=set()
    for p in workers:
        role=p["metadata"]["labels"]["app"];spec=p["spec"];node=spec["nodeName"];groups.setdefault(node,[]).append(role)
        ns("wait","job/"+role,"--for=condition=complete","--timeout=25s")
        job=object_json("job",role);container=p["status"]["containerStatuses"][0]
        assert container["state"]["terminated"]["exitCode"]==0 and container["restartCount"]==0
        assert container["imageID"] in {deployment["oci_refs"]["worker"],deployment["worker_image"],deployment["oci_refs"]["worker"].split("@")[1]}
        assert spec["automountServiceAccountToken"] is False and spec["securityContext"]["runAsUser"]==10003
        app=spec["containers"][0];sec=app["securityContext"]
        assert sec["readOnlyRootFilesystem"] and not sec["allowPrivilegeEscalation"] and sec["capabilities"]["drop"]==["ALL"]
        assert spec["securityContext"]["seccompProfile"]["type"]=="RuntimeDefault"
        assert job["spec"]["backoffLimit"]==0 and spec["restartPolicy"]=="Never"
        mounts=app["volumeMounts"]
        assert all(not spec.get(n,False) for n in ("hostPID","hostNetwork","hostIPC"))
        assert not any("hostPath" in v for v in spec["volumes"])
        assert next(m for m in mounts if m["mountPath"]=="/credentials")["readOnly"]
        assert next(m for m in mounts if m["mountPath"]=="/source")["readOnly"]
        raw=ns("logs","pod/"+p["metadata"]["name"],"-c","worker","--timestamps")
        (run/(role+".log")).write_bytes(raw)
        milestones=[];processes=[]
        for line in raw.splitlines():
            at,_,data=line.partition(b" ")
            if not data.startswith(b"{"):continue
            row=json.loads(data)
            if row.get("event") in {"native-ready","native-running","native-finished"}:
                milestones.append(dict(at=at.decode(),**{k:row[k] for k in ("event","execution_id","namespace_pid","native_status","native_lifecycle_receipts_settled") if k in row}))
            if row.get("event")=="native-startup-diagnostics":
                processes=[{k:r[k] for k in ("executable","pid","ppid")} for r in row["diagnostic"]["processes"]]
        assert [m["event"] for m in milestones]==["native-ready","native-running","native-finished"]
        assert milestones[0]["native_status"]=="PAUSED" and milestones[-1]["native_status"]=="FINISHED"
        assert milestones[-1]["native_lifecycle_receipts_settled"]
        ids={r["execution_id"] for r in milestones};assert len(ids)==1;observed.update(ids)
        by_name={r["executable"]:r for r in processes}
        assert by_name["SPELL-Executor"]["ppid"]==by_name["SPELL-Context"]["pid"]
        assert by_name["SPELL-Context"]["ppid"]==by_name["SPELL-Listener"]["pid"]
        starts.append(datetime.fromisoformat(milestones[1]["at"]));ends.append(datetime.fromisoformat(milestones[2]["at"]))
        evidence["pods"][role]={"pod":p["metadata"]["name"],"pod_uid":p["metadata"]["uid"],"job_uid":job["metadata"]["uid"],
                                "node":node,"container_id":container["containerID"],"kubelet_image_id":container["imageID"],
                                "pod_image_ref":app["image"],"exit":0,"restarts":0,"log_sha256":hashlib.sha256(raw).hexdigest(),
                                "original_processes":processes,"events":milestones}
    assert observed==expected
    evidence["running_overlap_seconds"]=(min(ends)-max(starts)).total_seconds()
    assert evidence["running_overlap_seconds"]>0
    durable=json.loads(ns("exec","deployment/context","-c","context","--","python","-I","-c",CHECK_DB,"/state/context.sqlite3"))
    assert durable["integrity"]=="ok" and {r["id"] for r in durable["executions"]}==expected
    assert {r["execution_id"] for r in durable["results"] if r["native_status"]=="FINISHED"}==expected
    assert {r["execution_id"] for r in durable["holds"]}=={r["execution_id"] for r in durable["natives"]}==expected
    assert sum(w["spent"] for w in durable["workers"])==len(expected)
    assert [r[0] for r in durable["events"]]==list(range(1,len(durable["events"])+1))
    evidence["durable"]=durable
    evidence["asrun"]=audit_volumes(groups,deployment["oci_refs"]["core"])
    assert set(evidence["asrun"])==set(evidence["pods"]) and all(evidence["asrun"].values())
    claims=object_json("persistentvolumeclaims")["items"]
    evidence["claims"]={c["metadata"]["name"]:{"uid":c["metadata"]["uid"],"pv":c["spec"].get("volumeName"),"phase":c["status"]["phase"]}
                        for c in claims if c["status"]["phase"]=="Bound"}
    network=object_json("networkpolicies")["items"]
    evidence["network_policies"]=[p["metadata"]["name"] for p in network]
    evidence["oci_refs"]=deployment["oci_refs"]
    evidence["deployment_sha256"]=hashlib.sha256((path/"workloads.json").read_bytes()).hexdigest()
    evidence["passed"]=True
    (run/"durable.json").write_text(json.dumps(evidence,indent=2)+"\n")
    print(json.dumps({"jobs":len(workers),"native_overlap":evidence["running_overlap_seconds"],"original_audit_events":len(durable["events"]),
                      "durable_asrun":len(evidence["asrun"]),"audit_sha256":durable["audit_sha256"]}))


if __name__ == "__main__":main()
