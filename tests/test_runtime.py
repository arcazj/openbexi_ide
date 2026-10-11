import json
import os
import re
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
from openbexi_runtime.dap import MessageReader, ProtocolError, encode_message
from openbexi_runtime.launch import LaunchSpec, interpreter_info
from openbexi_runtime.processes import process_alive, start_child


def capture(spec, input_text=None, timeout=20):
    child, owner = start_child(spec)
    try:
        stdout, stderr = child.communicate(input_text, timeout=timeout)
        return child.returncode, stdout, stderr
    finally:
        owner.close()
        if child.poll() is None: child.kill()
        child.communicate(timeout=5)


def test_isolated_flags_explicit_imports_args_unicode_stdin_and_no_domain_library(tmp_path, monkeypatch):
    poison = tmp_path / "poison"; poison.mkdir()
    (poison / "json.py").write_text("raise RuntimeError('environment leakage')")
    monkeypatch.setenv("PYTHONPATH", str(poison))
    monkeypatch.setenv("PYTHONHOME", str(poison))
    project = tmp_path / "my project"; project.mkdir()
    (project / "shared.py").write_text("VALUE = 42\n")
    nested = project / "scripts"; nested.mkdir()
    (nested / "neighbor.py").write_text("NAME = 'local'\n")
    script = nested / "café.py"
    script.write_text("import sys,json,os,builtins,importlib.util\nimport shared,neighbor\n"
        "data={'flags':[sys.flags.isolated,sys.flags.ignore_environment,sys.flags.no_user_site,sys.flags.safe_path],"
        "'args':sys.argv[1:],'shared':shared.VALUE,'neighbor':neighbor.NAME,'input':input(),"
        "'spell':any(n=='spell' or n.startswith('openbexi_spell') for n in sys.modules),'qt':any(n.startswith('PySide6') for n in sys.modules),"
        "'injected':hasattr(builtins,'Display'),'path_env':os.environ.get('PYTHONPATH')}\n"
        "print(json.dumps(data,ensure_ascii=False)); print('stderr: café 😀',file=sys.stderr)\n", encoding="utf-8")
    code, stdout, stderr = capture(LaunchSpec(project, script, arguments=("two words", "café", "--flag", "")), "こんにちは\n")
    assert code == 0, stderr
    data = json.loads(stdout)
    assert data["flags"] == [1, 1, 1, True]
    assert data["args"] == ["two words", "café", "--flag", ""]
    assert data["shared"] == 42 and data["neighbor"] == "local"
    assert data["input"] == "こんにちは"
    assert not data["spell"] and not data["qt"] and not data["injected"]
    assert data["path_env"] is None and "café 😀" in stderr


def test_project_venv_without_gui_or_spell_dependencies_runs_plain_python(tmp_path):
    environment = tmp_path / ".venv"
    subprocess.run([sys.executable, "-I", "-m", "venv", "--without-pip", str(environment)], check=True, timeout=20,
                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    info = interpreter_info(python)
    assert info["version"][:2] == [3, 13]
    with pytest.raises(ValueError, match="debugpy 1.8.22"):
        interpreter_info(python, require_debugger=True)
    script = tmp_path / "plain.py"; script.write_text("print('clean environment')\n")
    code, stdout, stderr = capture(LaunchSpec(tmp_path, script, python))
    assert code == 0 and stdout.strip() == "clean environment", stderr


def test_check_cancelled_and_invalid_launch_do_not_start_user_code(tmp_path):
    cancelled = threading.Event(); cancelled.set()
    with pytest.raises(RuntimeError, match="cancelled"):
        interpreter_info(sys.executable, cancel=cancelled)
    with pytest.raises(ValueError, match="does not exist"):
        interpreter_info(tmp_path / "missing.exe")
    script = tmp_path / "main.py"; script.write_text("raise AssertionError('should never run')")
    nested = tmp_path / "nested"; nested.mkdir()
    with pytest.raises(ValueError, match="inside"):
        LaunchSpec(nested, script).validate()
    with pytest.raises(ValueError, match="NUL"):
        LaunchSpec(tmp_path, script, arguments=("bad\0argument",)).validate()


@pytest.mark.parametrize("source,code,message", [
    ("raise ValueError('visible failure')\n", 1, "ValueError: visible failure"),
    ("if True print('bad syntax')\n", 1, "SyntaxError"),
    ("raise SystemExit(7)\n", 7, ""),
])
def test_exceptions_syntax_errors_and_exit_codes(tmp_path, source, code, message):
    script = tmp_path / "error.py"; script.write_text(source)
    actual, stdout, stderr = capture(LaunchSpec(tmp_path, script))
    assert actual == code
    assert message in stderr


def test_owned_stop_reaps_child_and_grandchild_and_leaves_other_process_alone(tmp_path):
    script = tmp_path / "tree.py"
    child_code = "import subprocess,sys,time,os; g=subprocess.Popen([sys.executable,'-I','-c','import time;time.sleep(60)']); print(os.getpid(),g.pid,flush=True);time.sleep(60)"
    script.write_text("import subprocess,sys,time,os,json\n"
        f"child=subprocess.Popen([sys.executable,'-I','-u','-c',{child_code!r}],stdout=subprocess.PIPE,text=True)\n"
        "pids=[os.getpid(),*[int(p) for p in child.stdout.readline().split()]]\n"
        "print(json.dumps(pids),flush=True)\ntime.sleep(60)\n")
    unrelated = subprocess.Popen([sys.executable, "-I", "-c", "import time;time.sleep(60)"],
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    child, owner = start_child(LaunchSpec(tmp_path, script))
    try:
        pids = json.loads(child.stdout.readline())
        assert all(process_alive(pid) for pid in pids)
        owner.close(); child.communicate(timeout=5)
        deadline = time.monotonic() + 5
        while any(process_alive(pid) for pid in pids) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not any(process_alive(pid) for pid in pids)
        assert unrelated.poll() is None
    finally:
        owner.close()
        if child.poll() is None: child.kill()
        child.communicate(timeout=5)
        unrelated.kill(); unrelated.wait(timeout=5)


def test_normal_worker_exit_reaps_detached_user_child_on_windows(tmp_path):
    if os.name != "nt":
        pytest.skip("Windows worker Job ownership; POSIX cleanup is tested through parent ownership")
    script = tmp_path / "orphan.py"
    script.write_text("import subprocess,sys\n"
                      "child=subprocess.Popen([sys.executable,'-I','-c','import time;time.sleep(60)'])\n"
                      "print(child.pid,flush=True)\n")
    code, stdout, stderr = capture(LaunchSpec(tmp_path, script))
    assert code == 0, stderr
    assert not process_alive(int(stdout.strip()))


def test_complete_python_reference_suite(tmp_path):
    repository = Path(__file__).resolve().parents[1]
    script = repository / "examples" / "test_Python.py"
    code, stdout, stderr = capture(LaunchSpec(script.parent, script), timeout=60)
    assert code == 0, stderr + stdout[-3000:]
    assert "39 topic(s)" in stdout and "All runtime checks passed:" in stdout
    summary = re.search(r"(\d+) check\(s\), 39 topic\(s\), (\d+) optional capability", stdout)
    assert summary and sum(int(value) for value in summary.groups()) >= 261
    output = repository / ".qualification" / "desktop-runtime"
    output.mkdir(parents=True, exist_ok=True)
    (output / "python-reference.stdout.txt").write_text(stdout, encoding="utf-8")
    (output / "python-reference.stderr.txt").write_text(stderr, encoding="utf-8")


def test_plain_python_graphic_window_opens_and_closes():
    examples = Path(__file__).resolve().parents[1] / "examples"
    code, stdout, stderr = capture(LaunchSpec(examples, examples / "graphics_demo.py",
                                  arguments=("--close-after", "150")))
    assert code == 0, stderr
    assert "Statistics window opened" in stdout and "Statistics window closed" in stdout


def test_interactive_menu_runs_topic_and_starts_updates_closes_graphics():
    examples = Path(__file__).resolve().parents[1] / "examples"
    code, stdout, stderr = capture(LaunchSpec(examples, examples / "test_menu.py"),
                                  "3\ntypes\n4\n5\n72\n6\n0\n")
    assert code == 0, stderr
    assert "All runtime checks passed:" in stdout and "Qualification exit: 0" in stdout
    assert "Statistics window opened" in stdout and "Statistics window closed" in stdout


@pytest.mark.parametrize("chunk", [1, 2, 7, 128])
def test_dap_fragmented_unicode_and_multiple_messages(chunk):
    messages = [{"seq": 1, "type": "event", "event": "output", "body": {"output": "café 😀"}},
                {"seq": 2, "type": "response", "request_seq": 1, "command": "threads", "success": True}]
    encoded = b"".join(encode_message(message) for message in messages)
    reader = MessageReader(); decoded = []
    for offset in range(0, len(encoded), chunk):
        decoded.extend(reader.feed(encoded[offset:offset+chunk]))
    assert decoded == messages


@pytest.mark.parametrize("wire", [
    b"Content-Length: -1\r\n\r\n", b"Content-Length: 999999999\r\n\r\n",
    b"Content-Length: x\r\n\r\n", b"Content-Length: 1\r\nContent-Length: 2\r\n\r\n",
    b"Content-Length: 2\r\n\r\n[]", b"Content-Length: 1\r\n\r\nx", b"x" * 16385,
])
def test_dap_malformed_or_oversized_input_is_rejected(wire):
    with pytest.raises(ProtocolError):
        MessageReader().feed(wire)
