"""Qualification commands scoped to the one disposable Windows-hosted KinD cluster."""

import json
import os
from pathlib import Path
import subprocess


LAB = Path("F:/openbexi-builds/qualification-20261122/native-kind")
CONTEXT = "kind-obxqual2211"
CASE_NAME = os.environ.get("OPENBEXI_KIND_CASE", "ten")
NAMESPACE = {"ten":"obx-native-qualification","concurrent":"obx-native-concurrent",
             "admission":"obx-native-admission","cohort2":"obx-native-cohort2",
             "fence":"obx-native-fence","final47":"obx-native-final47","final47one":"obx-native-final47one",
             "node47":"obx-native-node47", "node47b":"obx-native-node47b"}[CASE_NAME]
CASE = LAB / CASE_NAME
NODES = ("obxqual2211-worker", "obxqual2211-worker2")
IMAGES = {
    "gateway": ("openbexi-qualification-gateway:655f5b5a2de3", "sha256:fdd6bf0f754c414d846b7199b1bddeaf4cea5d70a899ba7878a3de4bc6e80ac8"),
    "core": ("openbexi-qualification-core:655f5b5a2de3", "sha256:1426fbd0b032ebe86f128474f27ac20e2b12200a3c544a7467c5b8f05e98100d"),
    "worker": ("obx-compat-deps:655", "sha256:a545c9617133bfc8034f385ef0ffb71c5eb2cfc9a74fd078838ee33bdf6753d4"),
}
PROVISIONER = "sha256:6324fa788e5b2a28e3f89e8e499a13b711c2d7b3232db10ea6302ddb08e84e16"
FINAL_47 = CASE_NAME in {"final47","final47one","node47","node47b"}
if FINAL_47:
    bindings = json.loads((LAB/"release47-images.json").read_text())
    assert bindings["commit"] == "47e0cb376dac1e49e1f6745318c0eb3e43b2ec4d"
    assert set(bindings["images"]) == set(IMAGES)
    IMAGES = {role:(binding["local_tag"],binding["config_digest"]) for role,binding in bindings["images"].items()}


def run(command, *, data=None, timeout=90, check=True):
    return subprocess.run(list(map(str, command)), input=data, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout, check=check)


def scoped(*args):
    return ["kubectl", "--kubeconfig", str(LAB / "kubeconfig"), "--context", CONTEXT, *args]


def kubectl(*args, data=None, timeout=90):
    response = run(scoped(*args), data=data, timeout=timeout, check=False)
    if response.returncode:
        # No object body or Secret values are passed to stdout or stderr.
        raise RuntimeError("kubectl " + str(args[:2]) + " failed: " + response.stderr.decode(errors="replace")[-500:])
    return response.stdout


def namespace(*args, **options):
    return kubectl("--namespace", NAMESPACE, *args, **options)


def validate_cluster():
    expected = json.loads((LAB / "cluster-result.json").read_text())["nodes"]
    nodes = json.loads(kubectl("get", "nodes", "-o", "json"))["items"]
    actual = {n["metadata"]["name"]: n["metadata"]["uid"] for n in nodes}
    assert actual == {n["name"]: n["uid"] for n in expected}
    assert set(actual) == {*NODES, "obxqual2211-control-plane"}
    return actual


def load_images():
    uids = validate_cluster()
    for node in NODES:
        inspect = json.loads(run(["docker", "inspect", node]).stdout)[0]
        assert inspect["Config"]["Labels"]["io.x-k8s.kind.cluster"] == "obxqual2211"
    for tag, image_id in IMAGES.values():
        assert json.loads(run(["docker","image","inspect",tag]).stdout)[0]["Id"] == image_id
    env = dict(os.environ, KUBECONFIG=str(LAB/"kubeconfig"))
    args = [str(LAB/"kind.exe"), "load", "docker-image", "--name", "obxqual2211", "--nodes", ",".join(NODES)]
    action = subprocess.run([*args, *(tag for tag, ident in IMAGES.values())],env=env,timeout=540,
                            stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    stem = "image-import-47e" if FINAL_47 else "image-import"
    (LAB/(stem+".log")).write_bytes(action.stdout)
    if action.returncode:
        raise RuntimeError("KinD image import failed: " + action.stdout.decode(errors="replace")[-1500:])
    records = {}
    for node in NODES:
        records[node] = {}
        for role,(tag,ident) in IMAGES.items():
            image = json.loads(run(["docker","exec",node,"crictl","inspecti",tag]).stdout)["status"]
            assert image["id"] == ident and tag in " ".join(image["repoTags"])
            records[node][role] = {k:image[k] for k in ("id","repoTags","repoDigests","size")}
    (LAB/(stem+".json")).write_text(json.dumps({"cluster":CONTEXT,"nodes":uids,"images":records},indent=2)+"\n")
    print("Verified three frozen images on each worker node")


if __name__ == "__main__":
    load_images()
