"""Cross-check the public Windows load receipt against ten original workers and the durable Context."""

from argparse import ArgumentParser
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import subprocess

QUERY = """
import json,sqlite3
db=sqlite3.connect('file:/state/context.sqlite3?mode=ro',uri=True)
db.row_factory=sqlite3.Row
def rows(sql):return [dict(r) for r in db.execute(sql)]
print(json.dumps(dict(
  integrity=[r[0] for r in db.execute('PRAGMA integrity_check')],
  executions=rows('SELECT id,procedure_id,owner,worker_slot,worker_incarnation,lifecycle,control_state FROM executions ORDER BY procedure_id'),
  spent=rows('SELECT slot,incarnation,spent FROM workers ORDER BY slot'),
  held=db.execute('SELECT COUNT(*) FROM reservations').fetchone()[0],
  native_members=rows('SELECT execution_id,target_id,instance_id,pid,executable_sha256,state FROM native_members ORDER BY execution_id'),
  results=rows('SELECT execution_id,native_status FROM assigned_native_results ORDER BY execution_id'),
  event_counts=rows('SELECT type,COUNT(*) AS count FROM events GROUP BY type ORDER BY type')
)))
"""


def main():
    p=ArgumentParser()
    p.add_argument("--case",type=Path,required=True)
    p.add_argument("--cleanup",action="store_true")
    a=p.parse_args()
    case_dir=a.case.resolve()
    deployment=json.loads((case_dir/"deployment.json").read_text())
    case=json.loads((case_dir/"case.json").read_text())
    evidence=json.loads((case_dir/"probe/result.json").read_text())
    prefix=deployment["prefix"]
    assert re.fullmatch("obx-qual-load-[a-z0-9]+",prefix)
    def docker(*args):
        return subprocess.check_output(["docker",*args],text=True,encoding="utf-8",timeout=60).strip()
    def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    def exists(kind,name):
        return subprocess.run(["docker",kind,"inspect",name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    live=exists("container",prefix+"-context")
    db=json.loads(docker("exec",prefix+"-context","python","-I","-c",QUERY) if live else
                  docker("run","--rm","--network","none","--read-only","--mount",
                         f"type=volume,src={deployment['volume']},dst=/state,volume-subpath=state,readonly",
                         "--entrypoint","python",deployment["server_image"],"-I","-c",QUERY))
    expected=set(evidence["ten_public_reservations"].values())
    assert db["integrity"]==["ok"] and len(expected)==10 and db["held"]==10
    assert {r["id"] for r in db["executions"]}==expected
    assert all(r["native_status"]=="FINISHED" for r in db["results"])
    assert {r["execution_id"] for r in db["results"]}==expected
    assert len({(r["worker_slot"],r["worker_incarnation"]) for r in db["executions"]})==10
    assert len(db["spent"])==10 and all(r["spent"]==1 for r in db["spent"])
    assert len(db["native_members"])==10 and {r["execution_id"] for r in db["native_members"]}==expected
    report={"passed":False,"db":db,"workers":{},"probe_sha256":sha(case_dir/"probe/result.json"),
            "deployment_sha256":sha(case_dir/"deployment.json"),"retained_volume":deployment["volume"]}
    starts,finishes=[],[]
    for w in case["workers"]:
        name=prefix+"-"+w
        logfile=case_dir/(w+".log")
        if exists("container",name):
            state=json.loads(docker("inspect","--format","{{json .State}}",name))
            assert state["Status"]=="exited" and state["ExitCode"]==0 and not state["OOMKilled"]
            lines=docker("logs","--timestamps",name)
            logfile.write_text(lines+"\n")
            process={"exit_code":state["ExitCode"],"oom_killed":state["OOMKilled"]}
        else:
            lines=logfile.read_text()
            process={"process_status":"Container removed after prior collector verified exited, code zero, and no OOM; raw terminal logs retained."}
        found=[]
        for line in lines.splitlines():
            timestamp,_,payload=line.partition(" ")
            if not payload.startswith("{"):continue
            row=json.loads(payload)
            if row.get("event") in {"native-ready","native-running","native-finished"}:
                found.append({"at":timestamp,**{k:row[k] for k in ("event","execution_id","native_status","namespace_pid","hold_retained",
                    "native_lifecycle_receipts_settled") if k in row}})
        assert [r["event"] for r in found]==["native-ready","native-running","native-finished"]
        assert len({r["execution_id"] for r in found})==1 and found[0]["execution_id"] in expected
        assert found[0]["native_status"]=="PAUSED" and found[2]["native_status"]=="FINISHED" and found[2]["native_lifecycle_receipts_settled"]
        starts.append(datetime.fromisoformat(found[1]["at"]))
        finishes.append(datetime.fromisoformat(found[2]["at"]))
        report["workers"][w]={"container":deployment["containers"][w].split()[0],**process,"log_sha256":sha(logfile),"events":found}
    report["all_ten_native_running_overlap_seconds"]=(min(finishes)-max(starts)).total_seconds()
    assert report["all_ten_native_running_overlap_seconds"]>0
    report["passed"]=evidence["passed"]
    (case_dir/"durable.json").write_text(json.dumps(report,indent=2)+"\n")
    if a.cleanup:
        names=[prefix+"-"+role for role in ("gateway","listener","context",*case["workers"])]
        # Only the exact container IDs created in this fixture are eligible for cleanup.
        remaining=[name for name in names if exists("container",name)]
        for name in remaining:
            role=name.removeprefix(prefix+"-")
            assert docker("inspect","--format","{{.Id}}",name)==deployment["containers"][role].split()[0]
        if remaining:
            docker("stop","--time","3",*remaining)
            docker("rm",*remaining)
        assert deployment["networks"]==[prefix+"-"+role for role in ("edge","service","private")]
        for network in deployment["networks"]:
            if exists("network",network):docker("network","rm",network)
        clients=(case_dir/"clients").resolve()
        assert clients.parent==case_dir and clients.name=="clients"
        if clients.exists():
            for item in clients.rglob("*"):
                assert item.resolve().is_relative_to(clients)
                item.chmod(stat.S_IWRITE|stat.S_IREAD)
            shutil.rmtree(clients)
        report["cleanup"]={"removed_containers":len(names),"removed_networks":len(deployment["networks"]),
            "host_client_credentials_removed":not clients.exists(),"retained_db_and_audit_volume":deployment["volume"]}
    (case_dir/"durable.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"passed":report["passed"],"overlap_seconds":report["all_ten_native_running_overlap_seconds"]}))


if __name__=="__main__":main()
