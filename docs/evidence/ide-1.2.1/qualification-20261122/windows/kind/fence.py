"""Remove one actual active Kubernetes authority and worker before serving the original PVC again."""

import hashlib
import json
from pathlib import Path
import runpy
import time
import uuid
from openbexi_runtime.spell_server_client import SpellServerClient, SpellServerError

helpers=runpy.run_path(str(Path(__file__).with_name("collect.py")))
u, db_query=helpers["u"], helpers["CHECK_DB"]
key=lambda:str(uuid.uuid4())

def main():
    assert u["CASE_NAME"] in {"fence", "final47one"}
    u["validate_cluster"]()
    ns=u["namespace"]
    folder=u["CASE"];out=folder/"probe";out.mkdir(exist_ok=False)
    report={"passed":False,"phases":[]}
    def note(name,data):
        report[name]=data;report["phases"].append(name)
        (out/"result.json").write_text(json.dumps(report,indent=2)+"\n");print(name,flush=True)
    def pod(role):
        return json.loads(ns("get","pods","-l","role="+role,"-o","json"))["items"][0]
    def identity(p):
        c=p["status"]["containerStatuses"][0]
        return {"name":p["metadata"]["name"],"uid":p["metadata"]["uid"],"node":p["spec"]["nodeName"],
                "container_id":c["containerID"].split("://")[-1],"image":c["imageID"]}
    def state(limit=None):
        command=["exec","deployment/context","-c","context","--","python","-I","-c",db_query,"/state/context.sqlite3"]
        if limit is not None:command.append(str(limit))
        return json.loads(ns(*command))
    def denied(action,expected):
        try:action()
        except SpellServerError as err:
            assert err.status in expected,(err.status,err.code)
            return {"http":err.status,"code":err.code}
        raise AssertionError("Operation unexpectedly reached an active authority")
    def exited(old):
        container=u["run"](["docker","exec",old["node"],"crictl","inspect",old["container_id"]],check=False)
        if container.returncode:
            assert b"not found" in container.stderr.lower()
            return {"state":"removed","container_id":old["container_id"]}
        status=json.loads(container.stdout)["status"]
        assert status["labels"]["io.kubernetes.pod.uid"]==old["uid"] and status["state"]=="CONTAINER_EXITED"
        return {"state":status["state"],"exit":status["exitCode"],"finished_at":status["finishedAt"],"container_id":old["container_id"]}
    owner=SpellServerClient.from_config(folder/"clients/alice/connection.json")
    reader=SpellServerClient.from_config(folder/"clients/watch-01/connection.json")
    conn=None
    try:
        item=next(r for r in owner.read("A","procedures")["procedures"] if r["procedure_id"]=="procedure-01")
        conn=owner.authority("A","session.open",{},key=key())["connection_id"]
        data={k:item[k] for k in ("procedure_id","source_revision","source_sha256","runtime_image","driver_binding")}
        issued=owner.authority("A","execution.reserve",dict(data,connection_id=conn),key=key())
        execution=issued["id"];assert owner.remember_controller("A",issued)
        stale={"execution_id":execution,"connection_id":issued["connection_id"],"connection_generation":issued["connection_generation"],
               "expected_epoch":issued["epoch"],"capability":issued["capability"],"command":"CMD_RUN","target_admission_id":None}
        result=owner.launch("A",execution,key=key());assert result["state"]=="ADMITTED"
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            logs=ns("logs","job/worker-01","-c","worker")
            ready=next((r for line in logs.splitlines() if line.startswith(b"{") and (r:=json.loads(line)).get("event")=="native-ready" and r["execution_id"]==execution),None)
            if ready:break
            time.sleep(.3)
        else:raise TimeoutError("Native root never paused")
        assert ready["native_status"]=="PAUSED"
        (out/"active-native.log").write_bytes(logs)
        old_worker,old_service=identity(pod("worker")),identity(pod("context"))
        old=state()
        pvc=json.loads(ns("get","pvc","context-state","-o","json"))
        note("active",{"execution":execution,"native_status":"PAUSED","native_pid":ready["namespace_pid"],"old_worker":old_worker,
                       "old_context":old_service,"old_db":old,"pvc_uid":pvc["metadata"]["uid"],"pv":pvc["spec"]["volumeName"]})
        ns("scale","deployment/context","--replicas=0")
        ns("wait","pod/"+old_service["name"],"--for=delete","--timeout=50s")
        loss=denied(lambda:reader.read("A","executions"),{502,503,504})
        note("authority_loss",{"public_observer":loss,"old_context_exit":exited(old_service)})
        # The prior native process cannot retain a DSS channel when the replacement starts.
        ns("patch","job","worker-01","--type=merge","-p",'{"spec":{"suspend":true}}')
        old_pod=ns("get","pod",old_worker["name"],"--ignore-not-found","-o","json")
        if old_pod and json.loads(old_pod)["status"]["phase"] not in {"Failed","Succeeded"}:
            ns("wait","pod/"+old_worker["name"],"--for=delete","--timeout=50s")
        note("fenced_worker",exited(old_worker))
        ns("scale","deployment/context","--replicas=1")
        ns("rollout","status","deployment/context","--timeout=90s",timeout=95)
        new_pod=identity(pod("context"));assert new_pod["uid"]!=old_service["uid"]
        new=state(len(old["events"]))
        assert new["integrity"]=="ok" and new["prefix_sha256"]==old["audit_sha256"] and new["incarnation"]!=old["incarnation"]
        assert new["holds"]==old["holds"] and new["workers"]==old["workers"] and sum(r["spent"] for r in new["workers"])==1
        rows=reader.read("A","executions")["executions"];assert len(rows)==1
        row=rows[0];assert row["id"]==execution and row["lifecycle"]==row["control_state"]=="RECOVERY_REQUIRED" and not row["native_root_result"]
        stale_reply=denied(lambda:owner.request("POST","/v1/contexts/A/commands",stale,key=key()),{403,409})
        newpvc=json.loads(ns("get","pvc","context-state","-o","json"))
        assert newpvc["metadata"]["uid"]==pvc["metadata"]["uid"] and newpvc["spec"]["volumeName"]==pvc["spec"]["volumeName"]
        remaining=json.loads(ns("get","pods","-l","role=worker","-o","json"))["items"]
        assert all(p["status"]["phase"] in {"Failed","Succeeded"} for p in remaining)
        report["passed"]=True
        note("replacement",{"context":new_pod,"pvc_uid":newpvc["metadata"]["uid"],"pv":newpvc["spec"]["volumeName"],
             "new_db":new,"old_controller_actual_http":stale_reply,"public_observer":{"id":row["id"],"lifecycle":row["lifecycle"],
             "control_state":row["control_state"],"native_root_result":row["native_root_result"]},"running_worker_pods":0})
    except BaseException as err:note("error",repr(err));raise
    finally:owner.forget();reader.forget()


if __name__=="__main__":main()
