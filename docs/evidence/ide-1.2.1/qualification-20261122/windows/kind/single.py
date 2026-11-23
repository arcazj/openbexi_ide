"""Send distinct installed-client Start native intents to one public reservation in Kubernetes."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import argparse
import json
from pathlib import Path
import runpy
import threading
import time
import uuid
from openbexi_runtime.spell_server_client import SpellServerClient, SpellServerError


util=runpy.run_path(str(Path(__file__).with_name("cluster.py")))
key=lambda:str(uuid.uuid4())

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--starts",type=int,choices=(1,100),default=100)
    args=parser.parse_args()
    util["validate_cluster"]()
    case=util["CASE"];out=case/"single";out.mkdir(exist_ok=False)
    receipt={"passed":False,"phases":[]}
    def note(name,data):
        receipt[name]=data;receipt["phases"].append(name)
        (out/"result.json").write_text(json.dumps(receipt,indent=2)+"\n")
        print(name,flush=True)
    def observe(event,execution):
        deadline=time.monotonic()+50
        while time.monotonic()<deadline:
            raw = util["namespace"]("logs","job/worker-01","-c","worker","--timestamps")
            (out/"worker.log").write_bytes(raw)
            for line in raw.splitlines():
                _,_,payload=line.partition(b" ")
                if not payload.startswith(b"{"):continue
                row=json.loads(payload)
                if row.get("event")=="native-worker-failed":raise RuntimeError(str(row.get("causes",[])))
                if row.get("event")==event and row.get("execution_id")==execution:
                    return {k:row[k] for k in ("execution_id","native_status","namespace_pid","native_lifecycle_receipts_settled") if k in row}
            time.sleep(.2)
        raise TimeoutError(event)
    owner=SpellServerClient.from_config(case/"clients/alice/connection.json")
    watcher=SpellServerClient.from_config(case/"clients/watch-01/connection.json")
    conn=None
    try:
        data=owner.read("A","procedures")["procedures"]
        item=next(r for r in data if r["procedure_id"]=="procedure-01")
        conn=owner.authority("A","session.open",{},key=key())["connection_id"]
        binding={k:item[k] for k in ("procedure_id","source_revision","source_sha256","runtime_image","driver_binding")}
        proof=owner.authority("A","execution.reserve",dict(binding,connection_id=conn),key=key())
        execution=proof["id"];assert owner.remember_controller("A",proof)
        note("reservation",{"execution_id":execution,"source_sha256":item["source_sha256"]})
        seen=threading.Barrier(args.starts);start=time.monotonic()
        def contender(index):
            seen.wait(timeout=30);begin=time.monotonic()
            r={"index":index,"offset_seconds":round(begin-start,6)}
            try:r.update(http=200,**owner.launch("A",execution,key=key()))
            except SpellServerError as e:r.update(http=e.status,code=e.code)
            except Exception as e:r.update(http=0,error=type(e).__name__)
            r["seconds"]=round(time.monotonic()-begin,6)
            return r
        with ThreadPoolExecutor(args.starts) as pool: attempts=list(pool.map(contender,range(args.starts)))
        note("intents",attempts)
        note("counts",dict(Counter(str(r["http"])+"/"+r.get("state",r.get("code","")) for r in attempts)))
        assert sum(r.get("state")=="ADMITTED" for r in attempts)==1
        ready=observe("native-ready",execution);assert ready["native_status"]=="PAUSED";note("native_ready",ready)
        owner.command("A",execution,"CMD_RUN",key=key())
        terminal=observe("native-finished",execution)
        assert terminal["native_status"]=="FINISHED" and terminal["native_lifecycle_receipts_settled"]
        note("native_finished",terminal)
        rows=watcher.read("A","executions")["executions"]
        assert [(r["id"],r["native_root_result"]) for r in rows]==[(execution,"FINISHED")]
        receipt["passed"]=True;note("observed_result",{"id":execution,"native_root_result":"FINISHED"})
    except BaseException as e:note("error",repr(e));raise
    finally:
        if conn:
            try: owner.authority("A","session.close",{"connection_id":conn},key=key())
            except SpellServerError: pass
        owner.forget();watcher.forget()


if __name__=="__main__":main()
