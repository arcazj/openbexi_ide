"""Start an isolated API qualification stack with ten non-reusable full-native workers."""

import argparse
import concurrent.futures
import hashlib
import json
import re
import socket
import subprocess
import time
from pathlib import Path

SERVER = "sha256:6189fc60d20bcfd14ae40f10010fcd2cc0c79a9ac70da3118c05c8e2c5dd6583"
WORKER = "sha256:de617ca4c3e0d2550bd639c201182f3f36ee21de6d7fd232e17fead8a47e47f3"


def docker(*args):
    return subprocess.check_output(["docker", *map(str, args)], text=True, timeout=90).strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--subnet", type=int, required=True, choices=range(71, 81))
    a = p.parse_args()
    if not re.fullmatch("obx-qual-load-[a-z0-9]+", a.name):
        raise ValueError("Use an isolated load qualification prefix")
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    owner = subprocess.check_output(["whoami"], text=True).strip()
    subprocess.run(["icacls", out, "/inheritance:r", "/grant:r", owner + ":(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"], check=True, stdout=subprocess.DEVNULL)
    for image in (SERVER, WORKER):
        assert docker("image", "inspect", "--format", "{{.Id}}", image) == image
    prefix = a.name
    volume = prefix + "-case"
    networks = [prefix + "-" + n for n in ("edge", "service", "private")]
    command = dict(prefix=prefix, volume=volume, networks=networks, server_image=SERVER, worker_image=WORKER,
                   worker_limit_mib=1536, worker_swap_limit_mib=1536, subject_deadlines_seconds=[2, 3, 1.5])
    (out / "deployment.json").write_text(json.dumps(command, indent=2))
    docker("volume", "create", volume)
    for index, n in enumerate(networks):
        docker("network", "create", "--subnet", f"198.19.{a.subnet}.{index*32}/27", *([] if index == 0 else ["--internal"]), n)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
    prep = prefix + "-setup"
    docker("create", "--name", prep, "--network", "none", "--entrypoint", "python", "-e", "WORKER_IMAGE=" + WORKER, "-e",
           "PUBLIC_PORT=" + str(port), "--mount", f"type=volume,src={volume},dst=/case", SERVER, "-I", "/setup.py")
    docker("cp", Path(__file__).with_name("provision.py"), prep + ":/setup.py")
    docker("start", "-a", prep)
    docker("cp", prep + ":/case/case.json", out / "case.json")
    docker("cp", prep + ":/case/clients", out / "clients")
    docker("rm", prep)
    case = json.loads((out / "case.json").read_text())

    def mount(src, dst, readonly=True):
        return ["--mount", f"type=volume,src={volume},dst={dst},volume-subpath={src}" + (",readonly" if readonly else "")]

    def start(role):
        worker = role in case["workers"]
        name = prefix + "-" + role
        net = networks[2] if worker else networks[1 if role == "context" else 0]
        common = ["create", "--name", name, "--network", net, "--network-alias", role, "--init", "--read-only",
                  "--user", "10003:10003", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "256", *mount(role, "/credentials")]
        if worker:
            extra = ["--memory", "1536m", "--memory-swap", "1536m", "--cpus", "2", "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m",
                     "--tmpfs", "/workspace:rw,nosuid,nodev,size=16m,mode=0700,uid=10003,gid=10003",
                     "--env", "OPENBEXI_V08_AUDIT_ROOT=/audit", *mount("audit/" + role, "/audit", False), *mount("snapshot", "/source"), WORKER]
        else:
            extra = ["--tmpfs", "/tmp:rw,nosuid,nodev,size=8m"]
            if role == "context":
                extra += [*mount("git", "/git"), *mount("state", "/state", False)]
            elif role == "gateway":
                extra += ["--publish", f"127.0.0.1:{port}:9443"]
            extra += [SERVER, role, "--config", "/credentials/config.json"]
        docker(*common, *extra)
        if role == "context": docker("network", "connect", "--alias", role, networks[2], name)
        if role == "listener": docker("network", "connect", "--alias", role, networks[1], name)
        docker("start", name)
        for _ in range(80):
            if docker("inspect", "--format", "{{.State.Status}}", name) != "running":
                raise RuntimeError(role + " stopped during startup")
            if worker or '"port": 9443' in docker("logs", name):
                return role
            time.sleep(0.15)
        raise TimeoutError("Unready service " + role)

    for role in ("context", "listener", "gateway"):
        start(role)
    with concurrent.futures.ThreadPoolExecutor(5) as pool:
        assert sorted(pool.map(start, case["workers"])) == case["workers"]
    command["ready"] = True
    command["fixture_sha256"] = hashlib.sha256((out / "case.json").read_bytes()).hexdigest()
    command["containers"] = {s: docker("inspect", "--format", "{{.Id}} {{.Image}}", prefix + "-" + s)
                             for s in ["context", "listener", "gateway", *case["workers"]]}
    (out / "deployment.json").write_text(json.dumps(command, indent=2) + "\n")


if __name__ == "__main__":
    main()
