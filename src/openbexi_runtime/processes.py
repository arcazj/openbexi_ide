"""Ownership of a development process tree; this is not an OS security sandbox."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import signal
import subprocess


if os.name == "nt":
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    class BasicLimits(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                    ("flags", wintypes.DWORD), ("min_working", ctypes.c_size_t),
                    ("max_working", ctypes.c_size_t), ("active_limit", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                    ("scheduling", wintypes.DWORD)]

    class IOCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in
                    ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("basic", BasicLimits), ("io", IOCounters),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]

    class ThreadEntry(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD),
                    ('thread', wintypes.DWORD), ('process', wintypes.DWORD),
                    ('base_priority', wintypes.LONG), ('delta_priority', wintypes.LONG),
                    ('flags', wintypes.DWORD)]

    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for function in (kernel.Thread32First, kernel.Thread32Next):
        function.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
        function.restype = wintypes.BOOL
    kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenThread.restype = wintypes.HANDLE
    kernel.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel.ResumeThread.restype = wintypes.DWORD


class ProcessTree:
    """Keep an owned Windows Job handle or an isolated POSIX process group."""

    def __init__(self, pid: int):
        if pid <= 0 or pid == os.getpid():
            raise ValueError("A separate child process is required")
        self.pid = pid
        self.job = None
        self.closed = False
        if os.name == "nt":
            self._create_windows_job(pid)
        elif os.getpgid(pid) != pid:
            raise RuntimeError("The child must have its own process group")

    def _create_windows_job(self, pid):
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            limits = ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            process = kernel.OpenProcess(0x0100 | 0x0001 | 0x1000, False, pid)
            if not process:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if not kernel.AssignProcessToJobObject(job, process):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                kernel.CloseHandle(process)
        except BaseException:
            kernel.CloseHandle(job)
            raise
        self.job = job

    def close(self):
        if self.closed:
            return
        self.closed = True
        if os.name == "nt":
            if self.job and not kernel.CloseHandle(self.job):
                raise ctypes.WinError(ctypes.get_last_error())
            self.job = None
        else:
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def active_count(self):
        """Count owned processes; unknown ownership prevents early token reuse."""
        if self.closed:
            return 0
        if os.name == "nt":
            class Accounting(ctypes.Structure):
                _fields_ = [("user", ctypes.c_int64), ("kernel", ctypes.c_int64),
                            ("period_user", ctypes.c_int64), ("period_kernel", ctypes.c_int64),
                            ("faults", wintypes.DWORD), ("total", wintypes.DWORD),
                            ("active", wintypes.DWORD), ("terminated", wintypes.DWORD)]
            query = kernel.QueryInformationJobObject
            query.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
            query.restype = wintypes.BOOL
            report = Accounting()
            if not self.job or not query(self.job, 1, ctypes.byref(report), ctypes.sizeof(report), None):
                return None
            return report.active
        identifiers = self.process_ids()
        return None if identifiers is None else len(identifiers)

    def process_ids(self):
        """Return actual owned process identities, or None when unobservable."""
        if self.closed:
            return set()
        if os.name == 'nt':
            class IdList(ctypes.Structure):
                _fields_ = [('assigned', wintypes.DWORD), ('count', wintypes.DWORD),
                            ('identifiers', ctypes.c_size_t * 512)]
            report = IdList()
            query = kernel.QueryInformationJobObject
            query.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
            query.restype = wintypes.BOOL
            if not self.job or not query(self.job, 3, ctypes.byref(report), ctypes.sizeof(report), None):
                return None
            return set(report.identifiers[:report.count])
        proc = __import__('pathlib').Path('/proc')
        if not proc.is_dir():
            return None
        identifiers = set()
        for entry in proc.iterdir():
            if entry.name.isdigit():
                try:
                    if os.getpgid(int(entry.name)) == self.pid:
                        # An exited child can remain a zombie until its paused
                        # Python parent reaps it. It cannot execute or hold a slot.
                        state = (entry / 'stat').read_bytes().rsplit(b')', 1)[1].split()[0]
                        if state not in {b'Z', b'X'}:
                            identifiers.add(int(entry.name))
                except (ProcessLookupError, FileNotFoundError):
                    continue
                except (PermissionError, IndexError):
                    return None
        return identifiers


_worker_job = None


def _resume_created_process(pid):
    """Resume the initial Windows thread after the suspended child owns its job.

    Popen closes the primary thread handle, so recover it using the documented
    Tool Help thread inventory. No user code can spawn a child before ResumeThread.
    """
    # Bind one stable ctypes structure/signature at module initialization. A
    # per-call class races with other launches changing the shared DLL argtypes.
    snapshot = kernel.CreateToolhelp32Snapshot
    first, next_thread = kernel.Thread32First, kernel.Thread32Next
    open_thread = kernel.OpenThread
    resume = kernel.ResumeThread
    handle = snapshot(0x00000004, 0)  # TH32CS_SNAPTHREAD
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = ThreadEntry()
        entry.size = ctypes.sizeof(entry)
        found = first(handle, ctypes.byref(entry))
        while found:
            if entry.process == pid:
                thread = open_thread(0x0002, False, entry.thread)  # THREAD_SUSPEND_RESUME
                if not thread:
                    raise ctypes.WinError(ctypes.get_last_error())
                try:
                    if resume(thread) == 0xFFFFFFFF:
                        raise ctypes.WinError(ctypes.get_last_error())
                    return
                finally:
                    kernel.CloseHandle(thread)
            found = next_thread(handle, ctypes.byref(entry))
        raise RuntimeError('Suspended process primary thread is unavailable')
    finally:
        kernel.CloseHandle(handle)


def start_owned_process(command, **options):
    """Establish process-tree ownership before a Windows launcher can spawn."""
    if os.name == 'nt':
        options['creationflags'] = options.get('creationflags', 0) | 0x00000004  # CREATE_SUSPENDED
    else:
        options['start_new_session'] = True
    process = subprocess.Popen(command, **options)
    owner = None
    try:
        owner = ProcessTree(process.pid)
        if os.name == 'nt':
            _resume_created_process(process.pid)
        return process, owner
    except BaseException:
        if owner:
            owner.close()
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
        raise


def own_worker_tree():
    """Before running user code, make worker death also end its descendants.

    On Windows keep the handle until the OS closes it during process exit. Closing
    it in Python's atexit would kill the worker itself before its real exit status.
    """
    global _worker_job
    if os.name == "nt":
        owner = ProcessTree.__new__(ProcessTree)
        owner.pid, owner.job, owner.closed = os.getpid(), None, False
        owner._create_windows_job(owner.pid)
        _worker_job = owner
    # debugpy already creates a debuggee process group within its launcher's
    # session. setsid() is forbidden for that group leader; retain its group so
    # debugpy can terminate the debuggee and its children together.
    elif os.getpgrp() != os.getpid():
        os.setsid()


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        handle = kernel.OpenProcess(0x00100000 | 0x1000, False, pid)
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def start_child(spec):
    """Neutral subprocess API, also used by the independent runtime checks."""
    from .launch import clean_environment
    spec = spec.validate()
    child = subprocess.Popen(spec.command(), cwd=spec.project, env=clean_environment(),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", start_new_session=os.name != "nt",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        owner = ProcessTree(child.pid)
    except BaseException:
        child.kill(); child.wait(timeout=5)
        raise
    return child, owner
