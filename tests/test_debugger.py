from pathlib import Path
from importlib.metadata import distribution
import json
import shutil
import subprocess
import sys
import time

import pytest
from PySide6.QtTest import QTest
from openbexi_ide.debugger import DebugController
from openbexi_runtime.launch import LaunchSpec
from openbexi_runtime.processes import process_alive


def wait_until(app, condition, timeout=30):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        app.processEvents(); QTest.qWait(10)
    assert condition(), "Debugger did not reach the expected state"


@pytest.mark.parametrize('use_venv', [False, True])
def test_real_debugpy_breakpoint_variables_steps_and_console(app, tmp_path, use_venv):
    interpreter = Path(sys.executable)
    if use_venv:
        environment = tmp_path / 'runtime'
        subprocess.run([sys.executable, '-I', '-m', 'venv', '--without-pip',
                        str(environment)], check=True, timeout=20)
        interpreter = environment / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
        site = Path(subprocess.check_output([str(interpreter), '-I', '-c',
                    "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True).strip())
        # Reuse the already installed, locked debugger without network access.
        dependency = distribution('debugpy')
        for name in ('debugpy', 'debugpy-1.8.22.dist-info'):
            shutil.copytree(dependency.locate_file(name), site / name)
    script = tmp_path / "debug me.py"
    script.write_text("def add(value):\n    shifted = value + 1\n    return shifted\n"
                      "number = 7\nresult = add(number)\nprint('Result', result)\n"
                      "label = input('Name: ')\nprint('Hello', label)\n", encoding="utf-8")
    debugger = DebugController()
    stacks, stops, output, errors, verified, exits = [], [], [], [], [], []
    debugger.stack_changed.connect(stacks.append); debugger.stopped.connect(stops.append)
    debugger.output.connect(output.append); debugger.error.connect(errors.append)
    debugger.breakpoints_verified.connect(verified.append); debugger.finished.connect(exits.append)
    try:
        debugger.start(LaunchSpec(tmp_path, script, interpreter), {script: [5]})
        wait_until(app, lambda: bool(stacks) or bool(errors))
        assert not errors, errors
        assert verified and verified[0]["breakpoints"][0]["verified"]
        assert stacks[-1][0]["line"] == 5
        frame_id = stacks[-1][0]["id"]
        scopes, variables, evaluated = [], [], []
        debugger.view_request("scopes", {"frameId": frame_id}, scopes.append)
        wait_until(app, lambda: bool(scopes))
        local = next(scope for scope in scopes[0]["scopes"] if scope["name"] == "Locals")
        debugger.view_request("variables", {"variablesReference": local["variablesReference"]}, variables.append)
        debugger.view_request("evaluate", {"frameId": frame_id, "expression": "number + 1", "context": "watch"}, evaluated.append)
        wait_until(app, lambda: bool(variables) and bool(evaluated))
        assert any(var["name"] == "number" and var["value"] == "7" for var in variables[0]["variables"])
        assert evaluated[0]["result"] == "8"
        # debugpy returns to the caller's call-site line on stepOut.
        for command, line in [("stepIn", 2), ("stepOut", 5), ("next", 6), ("next", 7)]:
            previous = len(stacks)
            debugger.control(command)
            wait_until(app, lambda: len(stacks) > previous or bool(errors))
            assert not errors, errors
            assert stacks[-1][0]["line"] == line
        debugger.control("continue")
        wait_until(app, lambda: "Name:" in "".join(output))
        debugger.send_input("visitor")
        wait_until(app, lambda: bool(exits))
        assert exits == [0], errors
        assert "Result 8" in "".join(output) and "Hello visitor" in "".join(output)
        assert not debugger.running
    finally:
        debugger.stop(); wait_until(app, lambda: not debugger.running)


def test_pause_stop_and_repeated_sessions_reap_debugger_tree(app, tmp_path):
    script = tmp_path / "loop.py"
    script.write_text("import time,os\nprint('READY',os.getpid(),flush=True)\nwhile True:\n    time.sleep(0.01)\n")
    debugger = DebugController()
    output, errors = [], []
    debugger.output.connect(output.append); debugger.error.connect(errors.append)
    try:
        for _ in range(2):
            output.clear(); errors.clear()
            debugger.start(LaunchSpec(tmp_path, script))
            wait_until(app, lambda: "READY" in "".join(output) or bool(errors))
            assert not errors, errors
            script_pid = int("".join(output).split("READY ")[1].split()[0])
            pids = [script_pid, int(debugger.adapter.processId()), int(debugger.terminal.processId())]
            debugger.control("pause")
            wait_until(app, lambda: debugger.paused)
            debugger.stop(); wait_until(app, lambda: not debugger.running)
            assert not any(process_alive(pid) for pid in pids)
    finally:
        debugger.stop(); wait_until(app, lambda: not debugger.running)


def test_real_thread_and_async_breakpoints(app, tmp_path):
    script = tmp_path / "thread_async_demo.py"
    source = ("import threading,asyncio\n"
              "def worker():\n    thread_value = 17\n    print('thread',thread_value)\n"
              "thread = threading.Thread(target=worker,name='calculation')\n"
              "thread.start()\nthread.join()\n"
              "async def task():\n    async_value = 9\n    await asyncio.sleep(0.01)\n"
              "    print('async',async_value)\nasyncio.run(task())\n")
    script.write_text(source)
    debugger = DebugController()
    stacks, threads, errors, output, exits, stops, verified = [], [], [], [], [], [], []
    debugger.stack_changed.connect(stacks.append); debugger.threads_changed.connect(threads.append)
    debugger.error.connect(errors.append); debugger.output.connect(output.append); debugger.finished.connect(exits.append)
    debugger.stopped.connect(stops.append); debugger.breakpoints_verified.connect(verified.append)
    try:
        debugger.start(LaunchSpec(tmp_path, script), {script: [3, 9]})
        wait_until(app, lambda: bool(stacks) and bool(threads) or bool(errors))
        assert not errors, errors
        assert stacks[-1][0]["line"] == 3
        assert any(t["id"] == debugger.thread_id and t["name"] == "calculation" for t in threads[-1])
        previous = len(stacks)
        debugger.control("continue")
        wait_until(app, lambda: len(stacks) > previous or bool(errors))
        assert not errors, errors
        assert stacks[-1][0]["line"] == 9, json.dumps({"stops": stops, "verified": verified,
                                                      "stack": stacks[-1], "output": "".join(output), "errors": errors})
        debugger.control("continue")
        wait_until(app, lambda: bool(exits))
        assert exits == [0]
        assert "thread 17" in "".join(output) and "async 9" in "".join(output)
    finally:
        debugger.stop(); wait_until(app, lambda: not debugger.running)


def test_uncaught_exception_is_inspectable_and_exit_code_preserved(app, tmp_path):
    script = tmp_path / "exception.py"; script.write_text("value = 42\nraise ValueError('inspect this error')\n")
    debugger = DebugController(); stopped, output, exits = [], [], []
    debugger.stopped.connect(stopped.append); debugger.output.connect(output.append); debugger.finished.connect(exits.append)
    try:
        debugger.start(LaunchSpec(tmp_path, script))
        wait_until(app, lambda: bool(stopped))
        assert stopped[-1]["reason"] == "exception"
        debugger.control("continue")
        wait_until(app, lambda: bool(exits))
        assert exits == [1]
        assert "ValueError: inspect this error" in "".join(output)
    finally:
        debugger.stop(); wait_until(app, lambda: not debugger.running)
