"""Exercise a real RC1 upgrade, live native-backed Context checkpoint, fenced replacement and rollback."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.metadata
import json
from pathlib import Path
import runpy
import subprocess
import sys
import time
import uuid

from openbexi_runtime.spell_server_client import SpellServerClient, SpellServerError

fixture_tools=runpy.run_path(str(Path(__file__).with_name("compose_fixture.py")))
Fixture, docker, text = (fixture_tools[k] for k in ("Fixture","docker","text"))
RC, FINAL, NATIVE = (fixture_tools[k] for k in ("RC","FINAL","NATIVE"))
QUERY="""
import hashlib,json,sqlite3,sys
d=sqlite3.connect('file:/state/context.sqlite3?mode=ro',uri=True)
identity=dict(d.execute('SELECT name,value FROM meta WHERE name IN ("incarnation","context_id")'))
rows=d.execute('SELECT sequence,type,body FROM events ORDER BY sequence').fetchall()
limit=int(sys.argv[1])
digest=lambda data:hashlib.sha256(b''.join(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode()+b'\\n' for row in data)).hexdigest()
print(json.dumps(dict(identity,count=len(rows),last_sequence=rows[-1][0],audit_sha256=digest(rows),prefix_sha256=digest([r for r in rows if r[0]<=limit]),
    events=[[s,t] for s,t,b in rows],holds=d.execute('select procedure_id,execution_id from reservations order by procedure_id').fetchall(),
    executions=d.execute('select id,procedure_id,lifecycle,control_state,epoch,connection_generation from executions order by procedure_id').fetchall(),
    spent=d.execute('select slot,incarnation,spent from workers order by slot').fetchall(),
    integrity=d.execute('pragma integrity_check').fetchone()[0])))
"""
AUDIT="""
import hashlib,json,os,shutil,sys
from pathlib import Path
source=Path('/audit')
target=Path('/archive/worker-native-audit')
if sys.argv[1]=='save':target.mkdir(mode=0o700,exist_ok=False)
found={}
for f in sorted(source.rglob('*')):
    if f.is_symlink():raise ValueError('Unexpected audit link')
    if not f.is_file():continue
    name=f.relative_to(source)
    if sys.argv[1]=='save':
        dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True)
        with f.open('rb') as origin,dest.open('xb') as sink:
            shutil.copyfileobj(origin,sink);sink.flush();os.fsync(sink.fileno())
        data=dest.read_bytes()
    else:data=f.read_bytes()
    found[name.as_posix()]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
print(json.dumps(found))
"""


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--case",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    a=parser.parse_args(); f=Fixture(a.case); out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    case=json.loads((a.case/"case.json").read_text())
    report={"passed":False,"scope":"Task-only local Docker Compose upgrade and recovery; no migration, remote cluster, driver egress or live-command resumption.",
        "images":{"public_rc1":RC,"candidate":FINAL,"worker":NATIVE},"deployment":json.loads((a.case/"deployment.json").read_text()),
        "python":sys.executable,"ide":importlib.metadata.version("openbexi-ide"),"server_package":importlib.metadata.version("openbexi-spell-server"),"phases":[]}
    def record(name, details):
        report[name]=details; report["phases"].append(name)
        (out/"result.json").write_text(json.dumps(report,indent=2)+"\n")
        print(name,flush=True)
    def boot(gen,roles=("context-a","listener","gateway")):
        # Service startup is explicit. Context B and the independent DSS are outside this single-Context recovery case.
        for role in roles:
            f.compose(gen,"up","--detach","--no-deps","--no-build","--pull","never","--wait","--wait-timeout","32",role)
        return {role:{"container":f.container(gen,role),"image":text("inspect","--format","{{.Image}}",f.container(gen,role))} for role in roles}
    def shutdown(gen,roles):
        captures={}
        for role in roles:
            cid=f.container(gen,role)
            if not cid:continue
            if role=="qualification-worker":f.compose(gen,"kill","-s","SIGKILL",role)
            else:f.compose(gen,"stop","--timeout","6",role)
            state=json.loads(text("inspect","--format","{{json .State}}",cid))
            assert not state["Running"] and state["Pid"]==0
            captures[role]={"container":cid,"exit":state["ExitCode"],"pid":state["Pid"],"running":state["Running"]}
            if role=="qualification-worker":
                raw=docker("logs","--timestamps",cid).stdout
                (out/"old-worker.log").write_bytes(raw)
                captures[role]["original_worker_log_sha256"]=hashlib.sha256(raw).hexdigest()
            f.compose(gen,"rm","--force",role)
            assert not f.container(gen,role)
        return captures
    def client(subject):return SpellServerClient.from_config(a.case/subject/"connection.json")
    delivered_proofs={}
    def public(c):
        health=c.read("A","health")
        rows=c.read("A","executions")["executions"]
        return {"subject":health["subject"],"incarnation":health.get("incarnation"),"executions":[
            {k:r[k] for k in ("id","procedure_id","owner","lifecycle","control_state","epoch","connection_generation","native_root_result") if k in r} for r in rows]}
    def reserve(c,name,session):
        proc=next(r for r in c.read("A","procedures")["procedures"] if r["procedure_id"]==name)
        assert proc["source_sha256"]==case["source_sha256"][name]
        payload={k:proc[k] for k in ("procedure_id","source_revision","source_sha256","runtime_image","driver_binding")}
        actual=c.authority("A","execution.reserve",dict(payload,connection_id=session),key=str(uuid.uuid4()))
        assert c.remember_controller("A",actual)
        # Keep the actually delivered credential only in memory. The installed client can independently
        # erase it when its heartbeat discovers a restart; this test must also prove server-side exclusion.
        delivered_proofs[actual["id"]]={"execution_id":actual["id"],"connection_id":actual["connection_id"],
            "expected_epoch":actual["epoch"],"connection_generation":actual["connection_generation"],"capability":actual["capability"]}
        return actual["id"]
    def db(vol,sub,seq=0):
        res=f.helper(["-I","-c",QUERY,str(seq)],volumes=f.bind(vol,"/state",sub=sub,readonly=True))
        return json.loads(res.stdout)
    archive=f.bind("archive","/archive")
    tools=f.bind("fixture","/tools",sub="tools",readonly=True)
    initial=f.bind("original","/state",sub="current",readonly=True)
    target=f.bind("replacement","/replacement")
    auditvol=f.bind("fixture","/audit",sub="audit/worker-02",readonly=True)
    def checkpoint(mode, args, mounts, expect=True):
        op=f.helper(["-I","/tools/context_checkpoint.py",mode,*args],volumes=[*tools,*mounts],check=False)
        if expect and op.returncode:raise AssertionError(op.stderr.decode(errors="replace")[-950:])
        if not expect:
            assert op.returncode
            return {"exit":op.returncode,"observed":op.stderr.decode().splitlines()[-1]}
        return json.loads(op.stdout)
    def stale_command(c,e,*,disabled_route=False):
        try:
            c.request("POST","/v1/contexts/A/commands",dict(delivered_proofs[e],command="CMD_RUN",target_admission_id=None),key=str(uuid.uuid4()))
        except SpellServerError as error:
            assert error.status in ((403,404,409) if disabled_route else (403,409))
            assert error.code!="controller_proof_required"
            return {"http":error.status,"code":error.code,"route":"POST /v1/contexts/A/commands","credential":"unchanged prior server-issued controller proof"}
        raise AssertionError("Old controller retained native command authority")
    def unchanged(gen,expected,base_seq,base_sha,legacy,native):
        current=db("replacement","restored",base_seq)
        assert current["prefix_sha256"]==base_sha and current["integrity"]=="ok"
        observer=client("watch-01")
        try:
            panel=public(observer)
            assert panel["subject"]=="watch-01" and {r["id"] for r in panel["executions"]}=={legacy,native}
            assert all(r["lifecycle"]==r["control_state"]=="RECOVERY_REQUIRED" for r in panel["executions"])
            events=observer.events("A",limit=32)
            assert any(row.get("type")=="EXECUTION_RESERVED" and row.get("execution_id")==native for row in events["events"])
            assert current["incarnation"]!=expected and {x[1] for x in current["holds"]}=={legacy,native}
            assert sum(x[2] for x in current["spent"])==1
            return {"authority":current,"public":panel,"public_events":events["events"],"project":gen}
        finally:observer.forget()
    owner=client("alice"); watcher=client("watch-01")
    try:
        record("published_rc1_start",boot("rc0"))
        ss=owner.authority("A","session.open",{},key=str(uuid.uuid4()))["connection_id"]
        legacy=reserve(owner,"procedure-02",ss)
        base=db("original","current")
        assert any(x[1]==legacy for x in base["holds"])
        record("published_rc1_durable_reservation",{"public":public(watcher),"original_audit":base})
        record("original_release_processes_removed",shutdown("rc0",("gateway","listener","context-a")))
        record("upgrade_to_99686362",boot("live"))
        upgraded=db("original","current",base["last_sequence"])
        assert upgraded["prefix_sha256"]==base["audit_sha256"] and upgraded["incarnation"]!=base["incarnation"]
        assert public(watcher)["executions"][0]["lifecycle"]=="RECOVERY_REQUIRED"
        record("live_upgrade_preserves_rc1_audit_and_fences_controller",{"audit":upgraded,"old_controller":stale_command(owner,legacy)})
        owner=client("alice")
        connection=owner.authority("A","session.open",{},key=str(uuid.uuid4()))["connection_id"]
        native=reserve(owner,"procedure-01",connection)
        worker=boot("live",("qualification-worker",))["qualification-worker"]["container"]
        receipt=owner.launch("A",native,key=str(uuid.uuid4()));assert receipt["state"]=="ADMITTED"
        deadline=time.monotonic()+55
        while time.monotonic()<deadline:
            lines=text("logs",worker).splitlines()
            ready=next((r for ln in lines if ln.startswith("{") and (r:=json.loads(ln)).get("event")=="native-ready" and r["execution_id"]==native),None)
            if ready:break
            time.sleep(.3)
        else:raise TimeoutError("Native recovery subject did not reach ready")
        assert ready["native_status"]=="PAUSED"
        before=public(watcher); assert next(r for r in before["executions"] if r["id"]==native)["control_state"]=="OWNED"
        record("active_native_at_backup",{"execution_id":native,"native_status":ready["native_status"],"namespace_pid":ready["namespace_pid"],
               "public":before,"container":worker,"worker_image":NATIVE})
        active=checkpoint("capture",["--context","A","--state","/state","--archive","/archive/live"],[*archive,*initial])
        active_db=db("original","current",active["last_sequence"])
        assert active_db["prefix_sha256"]==active["audit_sha256"] and active["incarnation"]==active_db["incarnation"]
        record("online_backup",active)
        record("live_native_audit",json.loads(f.helper(["-I","-c",AUDIT,"read"],volumes=auditvol).stdout))
        # This host is the single allowed old execution and command-egress domain. Stop it before bringing up a replacement.
        record("old_execution_and_authority_removed",shutdown("live",("qualification-worker","gateway","listener","context-a")))
        cold=db("original","current",active["last_sequence"])
        assert cold["prefix_sha256"]==active["audit_sha256"]
        stored=json.loads(f.helper(["-I","-c",AUDIT,"save"],volumes=[*auditvol,*archive]).stdout)
        record("durable_original_native_audit",stored)
        assert stored and all(n in stored for n in report["live_native_audit"])
        chosen,dirname=active,"live"
        if cold["last_sequence"]!=active["last_sequence"]:
            chosen=checkpoint("capture",["--context","A","--state","/state","--archive","/archive/quiesced"],[*archive,*initial])
            dirname="quiesced"
        record("audit_cutover",{"original_checkpoint_events":active["audit_events"],"last_old_authority_events":cold["count"],
            "original_native_final_sequence":cold["last_sequence"],"restored_archive":dirname,"all_old_events_included":chosen["audit_sha256"]==cold["audit_sha256"]})
        assert report["audit_cutover"]["all_old_events_included"]
        rest=["--context","A","--archive","/archive/"+dirname,"--target","/replacement/restored"]
        invalid=checkpoint("restore",[*rest,"--manifest-sha256","0"*64],[*archive,*target],False)
        f.helper(["-I","-c","import shutil,sys;from pathlib import Path;src=Path(sys.argv[1]);dst=Path('/archive/damaged-copy');shutil.copytree(src,dst);f=(dst/'context.sqlite3').open('ab');f.write(b'qualification-corruption');f.close()", "/archive/"+dirname],volumes=archive)
        damaged=checkpoint("restore",["--context","A","--archive","/archive/damaged-copy","--target","/replacement/damaged",
            "--manifest-sha256",chosen["manifest_sha256"]],[*archive,*target],False)
        assert "checksum mismatch" in damaged["observed"]
        assert f.helper(["-I","-c","from pathlib import Path; assert not Path('/replacement/damaged').exists()"],volumes=target).returncode==0
        concurrent=["-I","/tools/context_checkpoint.py","restore","--context","A","--archive","/archive/"+dirname,
                    "--target","/replacement/contended","--manifest-sha256",chosen["manifest_sha256"]]
        with ThreadPoolExecutor(2) as pool:
            attempts=list(pool.map(lambda _:f.helper(concurrent,volumes=[*tools,*archive,*target],check=False),range(2)))
        assert sorted(r.returncode for r in attempts)==[0,1]
        winner=json.loads(next(r.stdout for r in attempts if not r.returncode))
        assert winner==chosen and db("replacement","contended",chosen["last_sequence"])["prefix_sha256"]==chosen["audit_sha256"]
        right=checkpoint("restore",[*rest,"--manifest-sha256",chosen["manifest_sha256"]],[*archive,*target]);assert right==chosen
        duplicate=checkpoint("restore",[*rest,"--manifest-sha256",chosen["manifest_sha256"]],[*archive,*target],False)
        record("verified_empty_volume_restore",{"original_receipt":chosen,"restored":right,"wrong_trusted_pin_rejected":invalid,
               "populated_destination_rejected":duplicate,"corrupt_database_rejected":damaged,"damaged_target_absent":True,
               "two_concurrent_restore_codes":sorted(r.returncode for r in attempts),"concurrent_winner_audit_verified":True})
        booted=boot("restored")
        first=unchanged("restored",active["incarnation"],chosen["last_sequence"],chosen["audit_sha256"],legacy,native)
        proof=stale_command(owner,native)
        fresh=client("alice")
        sess=fresh.authority("A","session.open",{},key=str(uuid.uuid4()))["connection_id"]
        try:reserve(fresh,"procedure-01",sess)
        except SpellServerError as error:assert error.status==409;hold={"http":error.status,"code":error.code}
        else:raise AssertionError("Old native execution hold was lost")
        fresh.authority("A","session.close",{"connection_id":sess},key=str(uuid.uuid4()));fresh.forget()
        check_private="""
import json,sys
from openbexi_spell_server.contracts import Fault
from openbexi_spell_server.transport import Route,tls_context
c=json.load(open('/old/config.json'))['assigned']
tls=tls_context('/old/ca.pem','/old/tls.pem','/old/tls.key')
route=Route('https://context:9443',sys.argv[1],tls)
try:route.call({'schema':'openbexi.worker-assignment/1','context_id':'A'},path='/v1/worker/assignment',schema='openbexi.worker-assignment/1')
except Fault as error:
    assert error.status==403,(error.status,error.code)
    print(json.dumps(dict(http=error.status,code=error.code)))
else:raise AssertionError('Retired worker certificate still accepted')
"""
        stale=f.helper(["-I","-c",check_private,case["replacement_private_identities"]["context"]],volumes=f.bind("fixture","/old",sub="live/worker-02",readonly=True),network=f.prefix+"_driver")
        record("replacement_public_and_authority",{"containers":booted,**first,"old_controller_command":proof,"original_logical_hold":hold,
               "old_worker_private_request":json.loads(stale.stdout),"rotated":case["replacement_private_identities"],"previous_private_pins":case["old_private_identities"]})
        assert all(case["replacement_private_identities"][n]!=case["old_private_identities"][n] for n in case["old_private_identities"])
        before_rollback=db("replacement","restored")
        record("replacement_stopped_for_rollback",shutdown("restored",("gateway","listener","context-a")))
        rollback=boot("rollback")
        rolled=unchanged("rollback",first["authority"]["incarnation"],before_rollback["last_sequence"],before_rollback["audit_sha256"],legacy,native)
        record("published_rc1_rollback",{"containers":rollback,**rolled,"old_controller_command":stale_command(owner,native,disabled_route=True)})
        before_forward=db("replacement","restored")
        record("rollback_stopped_for_forward",shutdown("rollback",("gateway","listener","context-a")))
        upgraded_again=boot("forward")
        final=unchanged("forward",rolled["authority"]["incarnation"],before_forward["last_sequence"],before_forward["audit_sha256"],legacy,native)
        record("roll_forward_final",{"containers":upgraded_again,**final,"old_controller_command":stale_command(owner,native)})
        assert len({base["incarnation"],upgraded["incarnation"],first["authority"]["incarnation"],rolled["authority"]["incarnation"],final["authority"]["incarnation"]})==5
        record("successful_final_teardown",shutdown("forward",("gateway","listener","context-a")))
        f.compose("forward","down","--remove-orphans")
        report["passed"]=True
        record("volumes_retained",report["deployment"]["volume_names"])
    except BaseException as error:
        record("error",repr(error));raise
    finally:
        owner.forget();watcher.forget()


if __name__=="__main__":main()
