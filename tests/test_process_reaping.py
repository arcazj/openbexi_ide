"""Real Linux orphan adoption, exact wait ownership and process-tree settlement."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

import pytest
import openbexi_runtime.processes as processes

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux pidfd/subreaper ownership")

CHILD = (
    "import json,os,subprocess,sys,time; "
    "p=subprocess.Popen([sys.executable,'-I','-c','import time;time.sleep(60)'],"
    "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
    "print(json.dumps([os.getpid(),p.pid]),flush=True);time.sleep(60)"
)
ROOT = (
    "import json,os,subprocess,sys; "
    f"p=subprocess.Popen([sys.executable,'-I','-c',{CHILD!r}],stdout=subprocess.PIPE,text=True); "
    "print(json.dumps([os.getpid(),*json.loads(p.stdout.readline())]),flush=True); "
    "sys.stdin.readline();sys.exit(int(sys.argv[1]))"
)


def launch(code=0):
    process, owner = processes.start_owned_process(
        [sys.executable, "-I", "-c", ROOT, str(code)], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    pids = json.loads(process.stdout.readline())
    identities = [processes._linux_identity(pid) for pid in pids]
    assert all(record and record["session"] == process.pid for record in identities)
    return process, owner, identities


def settled(identities):
    # A zombie with the original start time fails this assertion too.
    for original in identities:
        current = processes._linux_identity(original["pid"])
        assert current is None or current["start_ticks"] != original["start_ticks"], (original, current)


def dispose(process, owner):
    owner.close()
    process.communicate(timeout=5)


def test_cancel_reaps_owned_descendants_and_preserves_unrelated_wait_status():
    process, owner, identities = launch()
    unrelated = subprocess.Popen([sys.executable, "-I", "-c", "raise SystemExit(37)"])
    try:
        deadline = time.monotonic() + 5
        while processes._linux_identity(unrelated.pid)["state"] != b"Z":
            assert time.monotonic() < deadline
            time.sleep(0.005)
        owner.close()
        assert owner.closed and process.wait(timeout=5) == -signal.SIGKILL
        settled(identities)
        assert os.waitpid(unrelated.pid, 0) == (unrelated.pid, 37 << 8)
        unrelated.returncode = 37
    finally:
        dispose(process, owner)
        unrelated.wait(timeout=5)


@pytest.mark.parametrize("code", [0, 19])
def test_normal_and_error_root_exit_adopt_and_reap_remaining_children(code):
    process, owner, identities = launch(code)
    try:
        process.stdin.write("finish\n")
        process.stdin.flush()
        assert process.wait(timeout=5) == code
        for original in identities[1:]:
            current = processes._linux_identity(original["pid"])
            assert current["start_ticks"] == original["start_ticks"]
        # Only the root's direct child is orphaned yet; the grandchild still
        # belongs to that live child until the owned session is terminated.
        assert processes._linux_identity(identities[1]["pid"])["ppid"] == os.getpid()
        assert processes._linux_identity(identities[2]["pid"])["ppid"] == identities[1]["pid"]
        owner.close()
        settled(identities)
        assert process.returncode == code
    finally:
        dispose(process, owner)


def test_concurrent_owned_roots_and_repeated_close_do_not_exchange_child_statuses():
    before = len(list(Path("/proc/self/fd").iterdir()))
    runs = [launch() for _ in range(3)]
    barrier = threading.Barrier(6)

    def close(owner):
        barrier.wait(timeout=5)
        owner.close()

    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(close, [owner for _, owner, _ in runs] * 2))
        for process, owner, identities in runs:
            assert owner.closed and process.wait(timeout=5) == -signal.SIGKILL
            settled(identities)
    finally:
        for process, owner, _ in runs:
            dispose(process, owner)
    assert len(list(Path("/proc/self/fd").iterdir())) == before


def test_changed_root_start_identity_is_rejected_before_signalling(monkeypatch):
    process, owner, identities = launch()
    original = processes._linux_identity

    def changed(pid):
        current = original(pid)
        if pid == process.pid and current:
            current = {**current, "start_ticks": current["start_ticks"] + 1}
        return current

    try:
        with monkeypatch.context() as patch:
            patch.setattr(processes, "_linux_identity", changed)
            with pytest.raises(OSError, match="root process identity changed"):
                owner.close()
        assert not owner.closed and process.poll() is None
        assert all(original(record["pid"])["state"] not in {b"T", b"t", b"Z", b"X"} for record in identities)
    finally:
        dispose(process, owner)
    settled(identities)


@pytest.mark.parametrize("code", [0, 19])
def test_public_cli_natural_and_error_exit_reap_owned_descendants(tmp_path, code):
    script = tmp_path / "cli_tree.py"
    script.write_text(
        "import json,os,pathlib,subprocess,sys\n"
        f"child=subprocess.Popen([sys.executable,'-I','-c',{CHILD!r}],stdout=subprocess.PIPE,text=True)\n"
        "pids=[os.getpid(),*json.loads(child.stdout.readline())]\n"
        "identities=[]\n"
        "for pid in pids:\n"
        " fd=os.pidfd_open(pid)\n"
        " info=dict(line.split(':',1) for line in pathlib.Path('/proc/self/fdinfo/'+str(fd)).read_text().splitlines())\n"
        " fields=(pathlib.Path('/proc')/info['Pid'].strip()/'stat').read_text().rsplit(')',1)[1].split()\n"
        " os.close(fd)\n"
        " identities.append(dict(pid=pid,start_ticks=int(fields[19])))\n"
        "print(json.dumps(identities),flush=True)\n"
        f"raise SystemExit({code})\n")
    result = subprocess.run([sys.executable, "-I", "-m", "openbexi_runtime.cli", "run", script.name,
                             "--project", str(tmp_path), "--python", sys.executable],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == code, result.stderr
    settled(json.loads(result.stdout))


def test_pidfd_prerequisite_failure_prevents_owned_launch(monkeypatch):
    launched = []

    def unavailable(_pid):
        raise PermissionError("pidfd ownership denied")

    monkeypatch.setattr(os, "pidfd_open", unavailable)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: launched.append(args))
    with pytest.raises(PermissionError, match="pidfd ownership denied"):
        processes.start_owned_process([sys.executable, "-c", "raise SystemExit(0)"])
    assert launched == []


def test_qprocess_cleanup_failure_preserves_owner_for_exact_retry(app, monkeypatch):
    from PySide6.QtCore import QProcess
    from openbexi_ide.controller import OwnedProcess
    process = OwnedProcess()
    errors = []
    process.ownership_error.connect(errors.append)
    process.start(sys.executable, ["-I", "-c", ROOT, "0"])
    assert process.waitForStarted(5000) and process.waitForReadyRead(5000)
    identities = [processes._linux_identity(pid) for pid in json.loads(bytes(process.readAllStandardOutput()))]
    owner = process.owner
    close = owner.close
    failed = False

    def fail_once():
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("injected cleanup observation failure")
        close()

    try:
        with monkeypatch.context() as patch:
            patch.setattr(owner, "close", fail_once)
            process.release_tree()
            assert process.owner is owner and not owner.closed
            assert errors == ["Process cleanup failed: injected cleanup observation failure"]
            process.release_tree()
            assert process.owner is None and owner.closed
        assert process.waitForFinished(5000)
        settled(identities)
    finally:
        close()
        if process.state() != QProcess.NotRunning:
            process.kill()
            process.waitForFinished(5000)
