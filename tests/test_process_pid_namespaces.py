"""PID mapping is bound to kernel handles, never numeric sibling matches."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
import openbexi_runtime.processes as processes

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux PID namespaces")


@pytest.mark.parametrize("contents,expected", [
    ("Pid:\t100\nNSpid:\t100\t7\n", 100),
    ("Pid:\t-1\nNSpid:\t-1\n", None),
    ("Pid:\t100\nNSpid:\t100\t8\n", "error"),
    ("Pid:\t100\nNSpid:\t101\t7\n", "error"),
    ("Pid:\t100\nNSpid:\t100\n", "error"),
    ("Pid:\t100\nNSpid:\tbad\n", "error"),
    ("Pid:\t0\nNSpid:\t0\t7\n", "error"),
    ("Pid:\t100\n", "error"),
])
def test_pidfd_mapping_checks_both_proc_and_caller_namespace(tmp_path, monkeypatch, contents, expected):
    (tmp_path / "9").write_text(contents)
    monkeypatch.setattr(processes, "Path", lambda _path: tmp_path)
    if expected == "error":
        with pytest.raises(OSError, match="pidfd namespace identity differs"):
            processes._linux_pidfd_process(7, 9, 1)
    else:
        assert processes._linux_pidfd_process(7, 9, 1) == expected


def test_real_owned_pid_maps_through_original_kernel_handle():
    child = subprocess.Popen([sys.executable, "-I", "-c", "import time;time.sleep(60)"], start_new_session=True)
    fd = os.pidfd_open(child.pid)
    try:
        info = dict(line.split(":", 1) for line in Path(f"/proc/self/fdinfo/{fd}").read_text().splitlines())
        proc_pid = int(info["Pid"])
        record = processes._linux_identity(child.pid)
        assert record["pid"] == child.pid and record["proc_pid"] == proc_pid
        assert record["session"] == child.pid and record["ppid"] == os.getpid()
        stat = Path(f"/proc/{proc_pid}/stat").read_bytes().rsplit(b")", 1)[1].split()
        assert record["start_ticks"] == int(stat[19])
    finally:
        os.close(fd)
        child.kill()
        child.wait(timeout=5)


def test_reaped_original_handle_cannot_authorize_recycled_proc_path(monkeypatch):
    child = subprocess.Popen([sys.executable, "-I", "-c", "import time;time.sleep(60)"], start_new_session=True)
    original = processes._linux_pidfd_process
    calls = []

    def reaped_after_observation(pid, fd, level):
        result = original(pid, fd, level)
        calls.append(result)
        return result if len(calls) == 1 else None

    try:
        monkeypatch.setattr(processes, "_linux_pidfd_process", reaped_after_observation)
        assert processes._linux_identity(child.pid) is None
        assert len(calls) == 2 and child.poll() is None
    finally:
        child.kill()
        child.wait(timeout=5)


def test_matching_inner_pid_in_sibling_namespace_is_not_owned(tmp_path, monkeypatch):
    for pid in (100, 200):
        entry = tmp_path / str(pid)
        entry.mkdir()
        (entry / "status").write_text(f"Pid:\t{pid}\nNSpid:\t{pid}\t7\nNSsid:\t{pid}\t7\n")
    identity = dict(pid=7, proc_pid=100, start_ticks=17, session=7, state=b"S", ppid=5)
    monkeypatch.setattr(processes, "Path", lambda _path: tmp_path)
    monkeypatch.setattr(processes, "_linux_namespace_level", lambda: 1)
    monkeypatch.setattr(processes, "_linux_identity", lambda _pid: identity)
    owner = processes.ProcessTree.__new__(processes.ProcessTree)
    owner.pid, owner._root_proc_pid, owner._root_start_ticks = 7, 100, 17
    assert owner._linux_session() == {(7, 17): identity}


def test_reused_inner_pid_with_same_ticks_and_different_proc_identity_is_rejected(monkeypatch):
    child, owner = processes.start_owned_process([sys.executable, "-I", "-c", "import time;time.sleep(60)"])
    original = processes._linux_identity

    def replaced(pid):
        record = original(pid)
        return {**record, "proc_pid": record["proc_pid"] + 1} if pid == child.pid and record else record

    try:
        with monkeypatch.context() as patch:
            patch.setattr(processes, "_linux_identity", replaced)
            with pytest.raises(OSError, match="root process identity changed"):
                owner.close()
        assert not owner.closed and child.poll() is None
        assert original(child.pid)["state"] not in {b"T", b"t", b"Z", b"X"}
    finally:
        owner.close()
        child.wait(timeout=5)


def test_descendant_namespace_mapping_uses_callers_level_not_innermost(tmp_path, monkeypatch):
    (tmp_path / "9").write_text("Pid:\t100\nNSpid:\t100\t7\t2\n")
    monkeypatch.setattr(processes, "Path", lambda _path: tmp_path)
    assert processes._linux_pidfd_process(7, 9, 1) == 100
    with pytest.raises(OSError, match="pidfd namespace identity differs"):
        processes._linux_pidfd_process(7, 9, 2)
