"""Compare the shipped renderer with all ten recorded Jobs and the API-server's immutable specifications."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spell-repo", type=Path, required=True)
    parser.add_argument("--case", choices=("cohort2", "final47"), default="cohort2")
    args = parser.parse_args()
    os.environ["OPENBEXI_KIND_CASE"] = args.case
    cluster = runpy.run_path(str(Path(__file__).with_name("cluster.py")))
    cluster["validate_cluster"]()
    case = cluster["CASE"]
    recorded = json.loads((case / "workloads.json").read_text())
    deployment = json.loads((case / "deployment.json").read_text())
    template = args.spell_repo / "deploy/v0.8/render_native_job.py"
    render = runpy.run_path(str(template))["worker_job"]
    observed = {}
    for original in (doc for doc in recorded if doc["kind"] == "Job"):
        worker = original["metadata"]["name"]
        node = original["spec"]["template"]["spec"]["nodeSelector"]["kubernetes.io/hostname"]
        actual = render(cluster["NAMESPACE"], worker, deployment["oci_refs"]["worker"], deployment["oci_refs"]["core"],
                        deployment["source_archives_sha256"]["snapshot"], node)
        assert actual == original, worker
        api = cluster["namespace"]
        live = json.loads(api("get", "job/" + worker, "-o", "json"))
        dryrun = json.loads(api("apply", "--dry-run=server", "--server-side", "--field-manager=obx-native-qualification",
                                "-f", "-", "-o", "json", data=json.dumps(actual).encode()))
        assert live["metadata"]["uid"] == dryrun["metadata"]["uid"] and live["spec"] == dryrun["spec"]
        observed[worker] = {"uid":live["metadata"]["uid"], "node":node}
    assert len(observed) == 10
    result = {"passed":True,"renderer_sha256":hashlib.sha256(template.read_bytes()).hexdigest(),
              "original_workloads_sha256":hashlib.sha256((case/"workloads.json").read_bytes()).hexdigest(),
              "rendered_match_original":True, "server_dry_run_matches_immutable_live_spec":True, "jobs":observed}
    (case/"template.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"verified":len(observed),"renderer_sha256":result["renderer_sha256"]}))


if __name__=="__main__":main()
