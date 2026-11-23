"""Create the checked public Compose topology with separate operator, active and restored volumes."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess

COMMIT = "99686362f93fa1bbbadd70e7b74d52ed3b5da469"
RC = "sha256:295638b950a09a0c8c2f8467162407b9adaabfd96d558a9f02c67b97a38644ed"
FINAL = "sha256:a897af70ab6edf5aa6c8d05681111231f6c6b715e5da2f060bab02f149a91bbd"
NATIVE = "sha256:b96d56321543bea4818529c0332aa8ced874751a2ab972f02a78213977c1e115"


def docker(*args, check=True):
    proc = subprocess.run(["docker", *map(str,args)], capture_output=True, timeout=120)
    if check and proc.returncode:
        raise RuntimeError(f"Docker {args[0]} failed: " + proc.stderr.decode(errors="replace")[-1200:])
    return proc


def text(*args):
    return docker(*args).stdout.decode().strip()


class Fixture:
    def __init__(self, out):
        self.out = out.resolve()
        meta = json.loads((self.out/"deployment.json").read_text())
        self.prefix, self.port = meta["prefix"], meta["port"]
        self.env = dict(os.environ, V08_DEPLOY_ROOT=self.out.as_posix(), V08_SERVICE_UID="10003", V08_GATEWAY_PORT=str(self.port))

    def volume(self, role):
        return self.prefix + "-" + role

    def bind(self, role, dst, *, sub=None, readonly=False):
        spec=f"type=volume,src={self.volume(role)},dst={dst}"
        if sub: spec+=",volume-subpath="+sub
        if readonly: spec+=",readonly"
        return ["--mount",spec]

    def helper(self, command, *, volumes=(), entry="python", check=True, image=FINAL, network="none"):
        return docker("run","--rm","--network",network,"--read-only","--user","10003:10003","--cap-drop","ALL","--security-opt",
                      "no-new-privileges","--entrypoint",entry,*volumes,image,*command,check=check)

    def compose(self, generation, *args, check=True):
        argv=["docker","compose","--project-name",self.prefix,"-f",str(self.out/"compose.yaml"),"-f",str(self.out/(generation+".json")),*args]
        r=subprocess.run(argv,env=self.env,capture_output=True,timeout=90)
        if check and r.returncode: raise RuntimeError("Compose "+str(args[:2])+": "+r.stderr.decode(errors="replace")[-1400:])
        return r

    def container(self,generation,role):
        return self.compose(generation,"ps","-a","-q",role).stdout.decode().strip()


def setup(a):
    if not re.fullmatch("obx-qual-recovery-[a-z0-9]+",a.name):
        raise ValueError("Use an isolated temporary Compose project")
    out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    owner=subprocess.check_output(["whoami"],text=True).strip()
    subprocess.run(["icacls",out,"/inheritance:r","/grant:r",owner+":(OI)(CI)F","*S-1-5-18:(OI)(CI)F"],check=True,stdout=subprocess.DEVNULL)
    for image in (RC,FINAL,NATIVE):assert text("image","inspect","--format","{{.Id}}",image)==image
    with socket.socket() as s:s.bind(("127.0.0.1",0));port=s.getsockname()[1]
    repo=a.spell_repo.resolve()
    raw=subprocess.check_output(["git","-C",repo,"show",COMMIT+":deploy/v0.8/compose.yaml"])
    (out/"compose.yaml").write_bytes(raw)
    checkpoints=repo/"deploy/v0.8/context_checkpoint.py"
    receipt={"prefix":a.name,"port":port,"spell_commit":COMMIT,"rc_image":RC,"target_image":FINAL,"native_image":NATIVE,
             "release_compose_sha256":hashlib.sha256(raw).hexdigest(),"operator_checkpoint_sha256":hashlib.sha256(checkpoints.read_bytes()).hexdigest()}
    (out/"deployment.json").write_text(json.dumps(receipt,indent=2))
    f=Fixture(out)
    roles=("fixture","original","replacement","archive")
    for role in roles: text("volume","create",f.volume(role))
    prep=a.name+"-issuer"
    text("create","--name",prep,"--network","none","--entrypoint","python","-e","WORKER_IMAGE="+NATIVE,"-e","PUBLIC_PORT="+str(port),
         *f.bind("fixture","/case"),*f.bind("original","/state-original"),*f.bind("replacement","/replacement"),*f.bind("archive","/archive"),FINAL,"-I","/recovery-setup.py")
    here=Path(__file__).resolve().parent
    for src,dst in ((here.parent/"api/provision.py","load-provision.py"),(here/"provision.py","recovery-setup.py"),(checkpoints,"context_checkpoint.py")):
        text("cp",src,prep+":/"+dst)
    try:
        text("start","-a",prep)
        assert text("inspect","--format","{{.State.ExitCode}}",prep)=="0"
        text("cp",prep+":/case/case.json",out/"case.json")
        for role in ("alice","watch-01"):
            text("cp",prep+":/case/clients/"+role,out/role)
    finally:text("rm",prep)

    def mount(source,dst,sub=None,ro=False):
        result={"type":"volume","source":source,"target":dst,"read_only":ro}
        if sub:result["volume"]={"subpath":sub}
        return result
    for gen in ("rc0","live","restored","rollback","forward"):
        rc=gen in ("rc0","rollback")
        remote_state=gen in ("restored","rollback","forward")
        cfg="restored" if gen=="forward" else gen
        nodes={}
        for name,role in (("context-a","context"),("listener","listener"),("gateway","gateway")):
            scopes={"context-a":["control","driver"],"listener":["control"],"gateway":["ingress","control"]}[name]
            node={"image":RC if rc else FINAL,
                  "networks":{scope:{"aliases":[role]} for scope in scopes},
                  "volumes":[mount("fixture","/run/private",f"{cfg}/{role}",True),mount("fixture","/credentials",f"{cfg}/{role}",True)],
                  "healthcheck":{"test":["CMD","python","-I","-c","import socket; socket.create_connection(('127.0.0.1',9443),2).close()"],
                                 "interval":"1s","timeout":"3s","retries":20}}
            if role=="context":
                node["volumes"].extend([mount("replacement" if remote_state else "original","/state","restored" if remote_state else "current"),mount("fixture","/git","git",True)])
            nodes[name]=node
        nodes["qualification-worker"]={"image":NATIVE,"networks":["driver"],"read_only":True,"init":True,"user":"10003:10003","restart":"no",
             "security_opt":["no-new-privileges:true"],"cap_drop":["ALL"],"pids_limit":256,"mem_limit":"1536m","memswap_limit":"1536m",
             "environment":{"OPENBEXI_V08_AUDIT_ROOT":"/audit"},"tmpfs":["/tmp:rw,nosuid,nodev,size=128m","/workspace:rw,nosuid,nodev,size=16m,mode=0700,uid=10003,gid=10003"],
             "volumes":[mount("fixture","/credentials",cfg+"/worker-02",True),mount("fixture","/source","snapshot",True),mount("fixture","/audit","audit/worker-02")]}
        networks={n:{"ipam":{"config":[{"subnet":f"198.19.{a.subnet}.{i*32}/27"}]}} for i,n in enumerate(("ingress","control","driver"))}
        (out/(gen+".json")).write_text(json.dumps({"services":nodes,"networks":networks,
            "volumes":{name:{"external":True,"name":f.volume(name)} for name in roles}},indent=2))
        f.compose(gen,"config","--quiet")
    receipt.update(ready=True,volume_names=[f.volume(r) for r in roles],case_sha256=hashlib.sha256((out/"case.json").read_bytes()).hexdigest())
    (out/"deployment.json").write_text(json.dumps(receipt,indent=2)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True);p.add_argument("--spell-repo",type=Path,required=True)
    p.add_argument("--name",required=True);p.add_argument("--subnet",type=int,choices=range(75,81),required=True)
    setup(p.parse_args())
