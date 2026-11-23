"""Issue 100 distinct public native-start intents for one already-reserved logical procedure."""

from argparse import ArgumentParser
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time
import uuid

from openbexi_runtime.spell_server_client import SpellServerClient, SpellServerError


def key(): return str(uuid.uuid4())


def main():
    p=ArgumentParser()
    p.add_argument("--case",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    spec=json.loads((a.case/"case.json").read_text())
    owner=SpellServerClient.from_config(a.case/"alice/connection.json")
    reader=SpellServerClient.from_config(a.case/"observer/connection.json")
    report={"passed":False,"runtime":spec["worker_image"],"server":spec["server_image"],
            "fixture_sha256":hashlib.sha256((a.case/"case.json").read_bytes()).hexdigest(),"harness_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    def save(): (a.output/"result.json").write_text(json.dumps(report,indent=2)+"\n")
    session=None
    try:
        item=owner.read("A","procedures")["procedures"][0]
        assert item["source_sha256"]==spec["source_sha256"] and item["source_revision"]==spec["revision"]
        session=owner.authority("A","session.open",{},key=key())["connection_id"]
        binding={k:item[k] for k in ("procedure_id","source_revision","source_sha256","runtime_image","driver_binding")}
        receipt=owner.authority("A","execution.reserve",dict(binding,connection_id=session),key=key())
        assert owner.remember_controller("A",receipt)
        execution=receipt["id"]
        report.update(execution_id=execution,binding=binding)
        start=time.monotonic()
        barrier=threading.Barrier(100)
        def compete(i):
            barrier.wait(timeout=30)
            begin=time.monotonic()
            row={"index":i,"started_offset_seconds":round(begin-start,6)}
            try:
                result=owner.launch("A",execution,key=key())
                row.update(status=200,state=result["state"],execution_id=result["execution_id"],request_id=result["request_id"])
            except SpellServerError as e: row.update(status=e.status,code=e.code)
            except Exception as e: row.update(status=0,error=type(e).__name__)
            row["duration_seconds"]=round(time.monotonic()-begin,6)
            return row
        with ThreadPoolExecutor(100) as pool: rows=list(pool.map(compete,range(100)))
        report["requests"]=rows
        report["response_counts"]=dict(Counter(str(r["status"])+"/"+r.get("code",r.get("state","")) for r in rows))
        report["start_spread_seconds"]=round(max(r["started_offset_seconds"] for r in rows)-min(r["started_offset_seconds"] for r in rows),6)
        save()
        assert len([r for r in rows if r.get("state")=="ADMITTED" and r.get("execution_id")==execution])==1
        worker=spec["prefix"]+"-worker"
        def wait(event):
            deadline=time.monotonic()+80
            while time.monotonic()<deadline:
                data=subprocess.check_output(["docker","logs",worker],timeout=10)
                entries=[json.loads(line) for line in data.splitlines() if line.startswith(b"{")]
                matched=[row for row in entries if row.get("event")==event and row.get("execution_id")==execution]
                if matched:
                    assert len(matched)==1
                    return {k:matched[0][k] for k in ("event","execution_id","native_status","namespace_pid","native_lifecycle_receipts_settled") if k in matched[0]}
                time.sleep(0.25)
            raise TimeoutError(event)
        report["native_ready"]=wait("native-ready")
        assert report["native_ready"]["native_status"]=="PAUSED"
        owner.command("A",execution,"CMD_RUN",key=key())
        report["native_finished"]=wait("native-finished")
        assert report["native_finished"]["native_status"]=="FINISHED" and report["native_finished"]["native_lifecycle_receipts_settled"]
        visible=reader.read("A","executions")["executions"]
        assert len(visible)==1 and visible[0]["id"]==execution and visible[0]["native_root_result"]=="FINISHED"
        sql="""import sqlite3,json
d=sqlite3.connect('file:/state/context.sqlite3?mode=ro',uri=True)
print(json.dumps(dict(executions=d.execute('select count(*) from executions').fetchone()[0],spent=d.execute('select sum(spent) from workers').fetchone()[0],registered=d.execute('select count(*) from native_members').fetchone()[0],results=d.execute('select execution_id,native_status from assigned_native_results').fetchall(),events=d.execute('select type,count(*) from events group by type').fetchall())))
"""
        state=json.loads(subprocess.check_output(["docker","exec",spec["prefix"]+"-context","python","-I","-c",sql],text=True,timeout=10))
        report["durable"]=state
        assert state["executions"]==state["spent"]==state["registered"]==1 and state["results"]==[[execution,"FINISHED"]]
        report["passed"]=True
    except BaseException as error:
        report["error"]=repr(error);raise
    finally:
        if session:
            try:owner.authority("A","session.close",{"connection_id":session},key=key())
            except Exception as e:report["close_error"]=str(e)
        owner.forget(); reader.forget(); save()


if __name__=="__main__":main()
