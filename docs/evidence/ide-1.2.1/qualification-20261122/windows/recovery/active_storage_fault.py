"""Exhaust a disposable running Context's actual state mount with a native root paused."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import time
import uuid
from openbexi_runtime.spell_server_client import SpellServerClient, SpellServerError

modules=runpy.run_path(str(Path(__file__).with_name("compose_fixture.py")))
Fixture,docker,text,FINAL=(modules[k] for k in ("Fixture","docker","text","FINAL"))
query=runpy.run_path(str(Path(__file__).with_name("qualify_recovery.py")))["QUERY"]


def main():
    p=argparse.ArgumentParser();p.add_argument("--case",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    args=p.parse_args(); f=Fixture(args.case); out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    meta=json.loads((args.case/"deployment.json").read_text());fixture=json.loads((args.case/"case.json").read_text())
    small=f.prefix+"-smallstate"
    holder=f.prefix+"-holder"
    record={"passed":False,"fixture":meta,"storage_limit_bytes":2097152,"phases":[]}
    def note(name,value):
        record[name]=value;record["phases"].append(name);(out/"result.json").write_text(json.dumps(record,indent=2)+"\n");print(name,flush=True)
    def start(gen,roles):
        for role in roles:f.compose(gen,"up","--detach","--no-deps","--no-build","--pull","never","--wait","--wait-timeout","30",role)
    def cid(gen,role):return f.container(gen,role)
    def stat():
        command="import json,os;s=os.statvfs('/state');print(json.dumps(dict(total=s.f_blocks*s.f_frsize,available=s.f_bavail*s.f_frsize)))"
        return json.loads(text("exec",holder,"python","-I","-c",command))
    def db(seq):
        return json.loads(text("exec",holder,"python","-I","-c",query,str(seq)))
    def client(name):return SpellServerClient.from_config(args.case/name/"connection.json")
    key=lambda:str(uuid.uuid4())
    owner=client("alice");watch=client("watch-01")
    roles=("gateway","listener","context-a")
    mounted=["--mount",f"type=volume,src={small},dst=/state"]
    archive=f.bind("archive","/archive"); tools=f.bind("fixture","/tools",sub="tools",readonly=True)
    def checkpoint(generation):
        return json.loads(f.helper(["-I","/tools/context_checkpoint.py","capture","--context","A","--state","/state","--archive","/archive/"+generation],
                                   volumes=[*tools,*archive,*mounted]).stdout)
    def denied(action,allowed):
        before=time.monotonic()
        try:action()
        except SpellServerError as e:
            if e.status not in allowed:raise
            return {"http":e.status,"code":e.code,"elapsed_seconds":round(time.monotonic()-before,5)}
        raise AssertionError("A failed state device unexpectedly accepted this operation")
    try:
        text("volume","create","--driver","local","--opt","type=tmpfs","--opt","device=tmpfs","--opt","o=size=2m,mode=0777",small)
        text("run","--detach","--name",holder,"--network","none","--read-only","--user","10003:10003","--cap-drop","ALL","--security-opt","no-new-privileges",
             *mounted,"--entrypoint","python",FINAL,"-I","-c","import time;time.sleep(600)")
        for gen,base in [("storage-live","live"),("storage-restored","restored")]:
            doc=json.loads((args.case/(base+".json")).read_text())
            doc["volumes"]["smallstate"]={"external":True,"name":small}
            for vol in doc["services"]["context-a"]["volumes"]:
                if vol["target"]=="/state":vol.update(source="smallstate");vol.pop("volume")
            (args.case/(gen+".json")).write_text(json.dumps(doc,indent=2))
        gen="storage-live";start(gen,("context-a","listener","gateway"))
        catalog={r["procedure_id"]:r for r in owner.read("A","procedures")["procedures"]}
        sess=owner.authority("A","session.open",{},key=key())["connection_id"]
        ids=[]
        for name in ("procedure-02","procedure-01"):
            r=catalog[name];assert r["source_sha256"]==fixture["source_sha256"][name]
            payload={k:r[k] for k in ("procedure_id","source_revision","source_sha256","runtime_image","driver_binding")}
            proof=owner.authority("A","execution.reserve",dict(payload,connection_id=sess),key=key())
            assert owner.remember_controller("A",proof);ids.append(proof["id"])
        native=ids[1]
        stale={"execution_id":native,"connection_id":proof["connection_id"],"expected_epoch":proof["epoch"],"connection_generation":proof["connection_generation"],
               "capability":proof["capability"],"command":"CMD_RUN","target_admission_id":None}
        start(gen,("qualification-worker",));worker=cid(gen,"qualification-worker")
        assert owner.launch("A",native,key=key())["state"]=="ADMITTED"
        deadline=time.monotonic()+55
        while time.monotonic()<deadline:
            entries=[json.loads(s) for s in text("logs",worker).splitlines() if s.startswith("{")]
            ready=next((e for e in entries if e.get("event")=="native-ready" and e["execution_id"]==native),None)
            if ready:break
            time.sleep(.25)
        else:raise TimeoutError("Expected native ready")
        assert ready["native_status"]=="PAUSED"
        before=db(0);assert stat()["total"]==record["storage_limit_bytes"]
        note("active",{"executions":ids,"native_paused":native,"native_pid":ready["namespace_pid"],"container":worker,"state_mount":stat(),"db":before,
                       "hot_checkpoint":checkpoint("before-enospc")})
        fill="""
import errno,json,os
from pathlib import Path
p=Path('/state/qualification-ballast')
try:
    with p.open('xb', buffering=0) as f:
        while True:f.write(b'Z'*4096)
except OSError as e:
    assert e.errno==errno.ENOSPC,e
print(json.dumps(dict(ballast=p.stat().st_size,available=os.statvfs('/state').f_bavail*os.statvfs('/state').f_frsize)))
"""
        full=json.loads(text("exec",holder,"python","-I","-c",fill));assert full["available"]==0
        note("state_exhausted",full)
        trial=denied(lambda:owner.authority("A","session.open",{},key=key()),{503})
        failed_read=denied(lambda:watch.read("A","executions"),{503})
        note("actual_public_io_failure",{"one_fresh_write":trial,"observer_read":failed_read})
        text("exec",holder,"python","-I","-c","from pathlib import Path;Path('/state/qualification-ballast').unlink()")
        freed=stat();assert freed["available"]>0
        note("space_freed_authority_stays_fail_closed",{"available":freed,"new_distinct_write":denied(lambda:owner.authority("A","session.open",{},key=key()),{503})})
        original_audit=db(before["last_sequence"])
        assert original_audit["integrity"]=="ok" and original_audit["prefix_sha256"]==before["audit_sha256"] and original_audit["holds"]==before["holds"]
        if text("inspect","--format","{{.State.Running}}",worker)=="true":f.compose(gen,"kill","-s","SIGKILL","qualification-worker")
        for role in ("qualification-worker",*roles):
            old=cid(gen,role)
            if role!="qualification-worker":f.compose(gen,"stop","--timeout","6",role)
            assert text("inspect","--format","{{.State.Pid}}",old)=="0"
            f.compose(gen,"rm","--force",role)
        gen="storage-restored";start(gen,("context-a","listener","gateway"))
        new=db(before["last_sequence"])
        rows=watch.read("A","executions")["executions"]
        assert new["incarnation"]!=before["incarnation"] and new["prefix_sha256"]==before["audit_sha256"]
        assert new["holds"]==before["holds"] and {r["id"] for r in rows}==set(ids) and all(r["lifecycle"]=="RECOVERY_REQUIRED" for r in rows)
        rejected=denied(lambda:owner.request("POST","/v1/contexts/A/commands",stale,key=key()),{403,409})
        note("recovered",{"public_rows":[{"id":r["id"],"lifecycle":r["lifecycle"],"control_state":r["control_state"]} for r in rows],
             "incarnation":new["incarnation"],"source_prefix_sha256":new["prefix_sha256"],"integrity":new["integrity"],
             "old_controller_sent_to_public_endpoint":rejected,"durable_checkpoint":checkpoint("recovered-from-enospc")})
        f.compose(gen,"down","--remove-orphans")
        text("stop","--time","2",holder);text("rm",holder);text("volume","rm",small)
        record["passed"]=True
        note("cleanup",{"temporary_state_filesystem_removed":True,"durable_snapshots_retained_in":f.volume("archive")})
    except BaseException as error:note("error",repr(error));raise
    finally:owner.forget();watch.forget()


if __name__=="__main__":main()
