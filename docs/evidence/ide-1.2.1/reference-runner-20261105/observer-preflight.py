"""Read-only proof that the trusted observer sees Docker-host PIDs and cgroups."""
import json
import os
from pathlib import Path
import subprocess
import sys

name = sys.argv[1]
info = json.loads(subprocess.check_output(["docker", "inspect", name]))[0]
pid = info["State"]["Pid"]
report = dict(container_id=info["Id"], host_pid=pid, observer_pid_namespace=os.readlink("/proc/self/ns/pid"), passed=False)
try:
    fd = os.pidfd_open(pid)
    try:
        report["pidfd_open"] = True
        report["target_pid_namespace"] = os.readlink(f"/proc/{pid}/ns/pid")
        actual = subprocess.check_output(["docker", "exec", name, "readlink", "/proc/self/ns/pid"], text=True).strip()
        if actual != report["target_pid_namespace"]:
            raise RuntimeError("Docker PID namespace does not match observed PID")
        group = Path(f"/proc/{pid}/cgroup").read_text().strip().split("0::", 1)[1].lstrip("/")
        report["cgroup"] = group
        if info["Id"] not in group:
            raise RuntimeError("Observed cgroup does not bind the Docker container")
        report["memory_max"] = (Path("/sys/fs/cgroup") / group / "memory.max").read_text().strip()
        check = subprocess.run(["sudo", "-n", "python3", "-c",
            "import json,os,sys;from pathlib import Path; p=Path('/proc')/sys.argv[1];print(json.dumps(dict(uid=os.getuid(),root_readable=(p/'root').is_dir(),status_readable=bool((p/'status').read_text()))))", str(pid)], capture_output=True, text=True)
        report["privileged_read_exit"] = check.returncode
        if check.returncode:
            raise RuntimeError("Noninteractive trusted observer read is unavailable")
        report["privileged_read"] = json.loads(check.stdout)
        report["passed"] = report["privileged_read"]["uid"] == 0 and report["privileged_read"]["root_readable"]
    finally:
        os.close(fd)
except Exception as error:
    report["error"] = type(error).__name__ + ": " + str(error)
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["passed"] else 1)
