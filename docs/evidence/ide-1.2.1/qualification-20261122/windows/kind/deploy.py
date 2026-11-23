"""Deploy three certificate-bound services and ten single-use native Jobs to the dedicated namespace."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy


setup = runpy.run_path(str(Path(__file__).with_name("prepare.py")))
util, obj = setup["util"], setup["obj"]
LAB, NS, IMAGES, NODES = (util[k] for k in ("LAB", "NAMESPACE", "IMAGES", "NODES"))
ns, run = util["namespace"], util["run"]

INITIALIZE = """
import hashlib, os, sys, tarfile
from pathlib import Path
out = Path('/prepared')
(out / 'work').mkdir(mode=0o700)
if Path('/durable').exists():
    audit = Path('/durable/records')
    audit.mkdir(mode=0o700, exist_ok=True)
    audit.chmod(0o700)
    assert audit.stat().st_uid == os.getuid() and audit.stat().st_mode & 0o077 == 0
if len(sys.argv) > 1:
    archive = Path('/input/source.tar.gz')
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == sys.argv[1]
    source = out / 'source'
    source.mkdir(mode=0o750)
    with tarfile.open(archive) as files:
        for entry in files:
            path = source / entry.name
            assert path.resolve().is_relative_to(source) and entry.isfile()
            path.parent.mkdir(exist_ok=True, parents=True)
            with path.open('xb') as target:
                target.write(files.extractfile(entry).read())
            path.chmod(entry.mode & 0o755)
"""


def digests():
    refs = {}
    for node in NODES:
        def ctr(*args):
            return run(["docker", "exec", node, "ctr", "-n", "k8s.io", *args]).stdout
        rows = [line.split() for line in ctr("images", "ls").decode().splitlines()]
        for role, (tag, config) in IMAGES.items():
            local = "docker.io/library/" + tag
            root = next(row[2] for row in rows if row[0] == local)
            assert json.loads(ctr("content","get",root))["config"]["digest"] == config
            ref = local.rsplit(":",1)[0] + "@" + root
            if not any(row[0] == ref for row in rows):
                ctr("images","tag",local,ref)
            by_digest = json.loads(run(["docker", "exec", node, "crictl", "inspecti", ref]).stdout)["status"]
            assert by_digest["id"] == config
            if role in refs:
                assert refs[role] == ref
            refs[role] = ref
    return refs


def policy(name, selected, direction, peers, ports):
    item = obj("NetworkPolicy", name, {
        "podSelector":{"matchLabels":{"role":selected}},
        "policyTypes":[direction],
        direction.lower(): [{"from" if direction=="Ingress" else "to":peers, "ports":ports}],
    })
    item["apiVersion"]="networking.k8s.io/v1"
    return item


def resources(deployment, case, refs, shipped):
    roles = ("gateway","listener","context")
    workers = case["workers"]
    docs = []
    endpoint = [{"protocol":"TCP","port":9443}]
    dns = [{"namespaceSelector":{"matchLabels":{"kubernetes.io/metadata.name":"kube-system"}},
            "podSelector":{"matchLabels":{"k8s-app":"kube-dns"}}}]
    for role in ("gateway","listener","worker"):
        docs.append(policy("dns-"+role, role, "Egress", dns, [{"protocol":ip,"port":53} for ip in ("TCP","UDP")]))
    for source, target in (("gateway","listener"),("listener","context"),("worker","context")):
        docs.append(policy(source+"-to-"+target,source,"Egress",[{"podSelector":{"matchLabels":{"role":target}}}],endpoint))
        docs.append(policy(target+"-from-"+source,target,"Ingress",[{"podSelector":{"matchLabels":{"role":source}}}],endpoint))
    for name in ("context-state",*["audit-"+w for w in workers]):
        docs.append(obj("PersistentVolumeClaim", name, {"accessModes":["ReadWriteOnce"],"resources":{"requests":{"storage":"128Mi"}}}))
    for role in roles:
        service={"type":"ClusterIP","selector":{"app":role},"ports":[{"name":"tls","port":9443,"targetPort":9443}]}
        if role=="gateway" and util["CASE_NAME"]!="ten":
            service.update(type="NodePort",externalTrafficPolicy="Local")
        docs.append(obj("Service",role,service))
    security = {"allowPrivilegeEscalation":False,"readOnlyRootFilesystem":True,"capabilities":{"drop":["ALL"]}}
    def mount(name, target, *, sub=None, ro=False):
        value = {"name":name,"mountPath":target,"readOnly":ro}
        if sub:
            value["subPath"]=sub
        return value
    for index, name in enumerate([*roles,*workers]):
        worker = name in workers
        if worker and util["CASE_NAME"] not in {"concurrent","ten"}:
            docs.append(shipped(NS, name, refs["worker"], refs["core"],
                                deployment["source_archives_sha256"]["snapshot"], NODES[(index-len(roles))%2]))
            continue
        role = "worker" if worker else name
        uid = 10003 if worker else 65532
        labels = {"role":role,"app":name,"openbexi-native":"qualification"}
        volumes = [{"name":"creds","secret":{"secretName":"identity-"+name,"defaultMode":0o440}},
                   {"name":"tmp","emptyDir":{"medium":"Memory","sizeLimit":"128Mi" if worker else "8Mi"}}]
        mounts = [mount("creds","/credentials",ro=True),mount("tmp","/tmp")]
        cimage = refs["worker" if worker else ("gateway" if role=="gateway" else "core")]
        app = {"name":role,"image":cimage,"imagePullPolicy":"Never","securityContext":security,
               "resources":{"requests":{"cpu":"100m","memory":"128Mi"},"limits":{"cpu":"2","memory":"1536Mi" if worker else "512Mi"}},
               "volumeMounts":mounts}
        if not worker and util["CASE_NAME"]!="ten":
            app["resources"]["limits"]["cpu"]="4"
        pod = {"serviceAccountName":"no-api","automountServiceAccountToken":False,"enableServiceLinks":False,
               "securityContext":{"runAsNonRoot":True,"runAsUser":uid,"runAsGroup":uid,"fsGroup":uid,
                                  "fsGroupChangePolicy":"OnRootMismatch","seccompProfile":{"type":"RuntimeDefault"}},
               "nodeSelector":{"kubernetes.io/hostname":NODES[(index - len(roles))%2] if worker else NODES[0]},
               "containers":[app],"volumes":volumes,"terminationGracePeriodSeconds":8}
        if worker or role=="context":
            source = "snapshot" if worker else "git"
            volumes.extend([{"name":"input","configMap":{"name":"source-"+source}},
                            {"name":"prepared","emptyDir":{"sizeLimit":"32Mi"}}])
            init = {"name":"source","image":refs["core"],"imagePullPolicy":"Never","securityContext":security,
                    "command":["python","-I","-c",INITIALIZE,deployment["source_archives_sha256"][source]],
                    "volumeMounts":[mount("input","/input",ro=True),mount("prepared","/prepared")],
                    "resources":{"requests":{"cpu":"40m","memory":"32Mi"},"limits":{"cpu":"300m","memory":"128Mi"}}}
            pod["initContainers"]=[init]
            mounts.append(mount("prepared","/source" if worker else "/git",sub="source",ro=True))
            pvc = "audit-"+name if worker else "context-state"
            volumes.append({"name":"persistent","persistentVolumeClaim":{"claimName":pvc}})
            mounts.append(mount("persistent","/audit" if worker else "/state"))
        if worker:
            mounts.append(mount("prepared","/workspace",sub="work"))
            app["env"]=[{"name":"OPENBEXI_V08_AUDIT_ROOT","value":"/audit"}]
            pod["restartPolicy"]="Never"
            item = obj("Job",name,{"backoffLimit":0,"template":{"metadata":{"labels":labels},"spec":pod}})
            item["apiVersion"]="batch/v1"
        else:
            app.update(args=[role,"--config","/credentials/config.json"],ports=[{"name":"tls","containerPort":9443}],
                       readinessProbe={"tcpSocket":{"port":9443},"periodSeconds":2,"timeoutSeconds":2})
            item = obj("Deployment",name,{"replicas":1,"strategy":{"type":"Recreate"},"selector":{"matchLabels":{"app":name}},
                                        "template":{"metadata":{"labels":labels},"spec":pod}})
            item["apiVersion"]="apps/v1"
        docs.append(item)
    return docs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers",action="store_true",help="Start the ten separate Jobs after the services are healthy")
    parser.add_argument("--only",choices=[f"worker-{i:02}" for i in range(1,11)])
    parser.add_argument("--spell-repo",type=Path,default=Path(__file__).resolve().parents[7]/"openbexi_spell_plugin")
    args = parser.parse_args()
    util["validate_cluster"]()
    folder = util["CASE"]
    deployment = json.loads((folder/"deployment.json").read_text())
    case = json.loads((folder/"case.json").read_text())
    refs = digests()
    template=args.spell_repo/"deploy/v0.8/render_native_job.py"
    docs = resources(deployment,case,refs,runpy.run_path(str(template))["worker_job"])
    (folder/"workloads.json").write_text(json.dumps(docs,indent=2)+"\n")
    for item in docs:
        if (item["kind"] == "Job") != args.workers:
            continue
        if args.only and item["kind"]=="Job" and item["metadata"]["name"]!=args.only:
            continue
        ns("apply","--server-side","--field-manager=obx-native-qualification","-f","-",data=json.dumps(item).encode())
    if not args.workers:
        for role in ("context","listener","gateway"):
            ns("rollout","status","deployment/"+role,"--timeout=120s",timeout=130)
    else:
        for worker in ([args.only] if args.only else case["workers"]):
            ns("wait","pod","-l","app="+worker,"--for=condition=Ready","--timeout=90s",timeout=100)
        deployment["ready"]=True
    deployment["oci_refs"]=refs
    deployment["manifests_sha256"]=hashlib.sha256((folder/"workloads.json").read_bytes()).hexdigest()
    (folder/"deployment.json").write_text(json.dumps(deployment,indent=2)+"\n")
    print("Ready:", "native Jobs" if args.workers else "three services")


if __name__ == "__main__":
    main()
