"""Issue independent identities without a network and apply restricted, per-role inputs."""

import base64
import hashlib
import io
import json
from pathlib import Path
import runpy
import socket
import subprocess
import tarfile


util = runpy.run_path(str(Path(__file__).with_name("cluster.py")))
LAB, NS, IMAGES = (util[k] for k in ("LAB", "NAMESPACE", "IMAGES"))
kube, ns, run = (util[k] for k in ("kubectl", "namespace", "run"))
VOL = "obx-kind-2211-native-issuer-b" if util["CASE_NAME"] == "ten" else "obx-kind-2211-issuer-" + util["CASE_NAME"]
ISSUER = VOL + "-issuer"


def obj(kind, name, spec=None, **values):
    doc = {"apiVersion": "v1", "kind": kind, "metadata": {"name": name, "namespace": NS}, **values}
    if spec is not None:
        doc["spec"] = spec
    return doc


def create(doc):
    command = kube if doc["kind"] == "Namespace" else ns
    command("create", "-f", "-", data=json.dumps(doc).encode())


def archive(path):
    stream = run(["docker", "cp", ISSUER + ":/case/" + path + "/.", "-"]).stdout
    return tarfile.open(fileobj=io.BytesIO(stream), mode="r:")


def sample_source(kind):
    with archive(kind) as files:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as sample:
            for ent in files:
                if not ent.isfile():
                    continue
                member = ent.name.removeprefix("./")
                if member.startswith("/") or ".." in Path(member).parts:
                    raise ValueError("Unsafe qualification source filename")
                if kind == "snapshot" and not member.endswith(".py"):
                    raise ValueError("Unexpected file in native immutable snapshot")
                ent.name = member
                sample.addfile(ent, files.extractfile(ent))
        return buf.getvalue()


def main():
    util["validate_cluster"]()
    out = util["CASE"]
    out.mkdir(exist_ok=True)
    if (out/"deployment.json").exists():
        raise FileExistsError("Completed inputs already exist")
    user = subprocess.check_output(["whoami"], text=True).strip()
    run(["icacls", out, "/inheritance:r", "/grant:r", user + ":(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"])
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    nsdoc = {"apiVersion":"v1","kind":"Namespace","metadata":{"name":NS,"labels":{
        "pod-security.kubernetes.io/enforce":"restricted","pod-security.kubernetes.io/enforce-version":"v1.32",
        "openbexi-scope":"disposable-native-qualification"}}}
    previous = kube("get","namespace",NS,"--ignore-not-found","-o","json")
    if previous:
        assert json.loads(previous)["metadata"]["labels"].items() >= nsdoc["metadata"]["labels"].items()
    else:
        create(nsdoc)
    deny = obj("NetworkPolicy", "default-deny", {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]})
    deny["apiVersion"] = "networking.k8s.io/v1"
    for setup in [deny,obj("ServiceAccount", "no-api", automountServiceAccountToken=False)]:
        ns("apply","--server-side","--field-manager=obx-native-qualification","-f","-",data=json.dumps(setup).encode())
    image = util["PROVISIONER"]
    assert json.loads(run(["docker","image","inspect", image]).stdout)[0]["Id"] == image
    provision = Path(__file__).parent.parent / "api/provision.py"
    interrupted = run(["docker","inspect",ISSUER],check=False)
    if interrupted.returncode == 0:
        prior = json.loads(interrupted.stdout)[0]
        assert prior["State"]["Status"] == "created" and prior["HostConfig"]["NetworkMode"] == "none"
        assert any(m.get("Name") == VOL and m["Destination"] == "/case" for m in prior["Mounts"])
        run(["docker","rm",ISSUER])
    run(["docker","volume","create",VOL])
    run(["docker","create","--name",ISSUER,"--network","none","--read-only","--user","0:0","--cap-drop","ALL",
         "--cap-add","CHOWN","--cap-add","FOWNER","--cap-add","DAC_OVERRIDE",
         "--security-opt","no-new-privileges","--tmpfs","/tmp:rw,nodev,nosuid,size=48m",
         "--mount","type=volume,src="+VOL+",dst=/case","--entrypoint","python","-e","PUBLIC_PORT="+str(port),"-e",
         "WORKER_IMAGE="+IMAGES["worker"][1],image,"-I","-c",provision.read_text(encoding="utf-8")])
    run(["docker","start","-a",ISSUER],timeout=180)
    assert run(["docker","inspect","--format","{{.State.ExitCode}}",ISSUER]).stdout.strip() == b"0"
    run(["docker","cp",ISSUER+":/case/case.json",out/"case.json"])
    run(["docker","cp",ISSUER+":/case/clients",out/"clients"])
    case = json.loads((out/"case.json").read_text())
    for role in ["context","listener","gateway", *case["workers"]]:
        with archive(role) as records:
            values = {Path(m.name).name:base64.b64encode(records.extractfile(m).read()).decode()
                      for m in records if m.isfile()}
        assert set(values) == {"ca.pem","tls.pem","tls.key","config.json"}
        create(obj("Secret","identity-"+role,type="Opaque",immutable=True,data=values))
    source_hashes = {}
    for category in ("git","snapshot"):
        compressed = sample_source(category)
        source_hashes[category] = hashlib.sha256(compressed).hexdigest()
        create(obj("ConfigMap","source-"+category,immutable=True,binaryData={
            "source.tar.gz":base64.b64encode(compressed).decode()}))
    run(["docker","rm",ISSUER])
    result = {"namespace":NS,"port":port,"ready":False,"prefix":NS,"issuer_image":image,"issuer_network":"none",
              "source_archives_sha256":source_hashes,"worker_image":IMAGES["worker"][1],"server_image":IMAGES["gateway"][1],
              "core":IMAGES["core"][1],"provider":"kubernetes","provisioner_sha256":hashlib.sha256(provision.read_bytes()).hexdigest()}
    (out/"deployment.json").write_text(json.dumps(result,indent=2)+"\n")
    print("Created 13 immutable per-role Secrets, independent public client identities and two source-only ConfigMaps")


if __name__=="__main__":
    main()
