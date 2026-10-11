"""Validated, isolated local-development launches, independent of the GUI."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def clean_environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items()
            if key.upper() not in {"PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP",
                                   "PYTHONINSPECT", "PYTHONBREAKPOINT"}}


def console_interpreter(executable: str | Path) -> Path:
    path = Path(executable).resolve()
    if path.name.lower() == "pythonw.exe":
        path = path.with_name("python.exe")
    return path


def interpreter_info(executable: str | Path, require_debugger=False, cancel=None, language='python') -> dict:
    interpreter = console_interpreter(executable)
    if not interpreter.is_file():
        raise ValueError(f"Python interpreter does not exist: {interpreter}")
    if cancel is not None and cancel.is_set():
        raise RuntimeError("Interpreter check cancelled")
    probe = subprocess.Popen(
        [str(interpreter), "-I", "-B", "-X", "utf8", str(Path(__file__).with_name('interpreter_probe.py'))],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
        env=clean_environment(), start_new_session=os.name != "nt",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    from .processes import ProcessTree
    owner = None
    try:
        owner = ProcessTree(probe.pid)
        deadline = time.monotonic() + 5
        while True:
            if cancel is not None and cancel.is_set():
                raise RuntimeError("Interpreter check cancelled")
            if time.monotonic() >= deadline:
                raise RuntimeError("Interpreter check timed out")
            try:
                stdout, stderr = probe.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                continue
    finally:
        if owner:
            owner.close()
        if probe.poll() is None:
            probe.kill()
        probe.communicate(timeout=5)
    if probe.returncode:
        raise ValueError(f"Interpreter check failed: {stderr.strip()}")
    try:
        info = json.loads(stdout)
    except (ValueError, TypeError) as exc:
        raise ValueError("Interpreter returned an invalid version report") from exc
    if info.get("implementation") != "CPython" or info.get("version", [])[:2] != [3, 13]:
        raise ValueError("Select CPython 3.13 for this workspace")
    if language != 'python':
        info['backend'] = next((item for item in info.get('backends', []) if item['id'] == language), None)
        if info['backend'] is None:
            raise ValueError(f"Install the {language} backend in the selected interpreter first")
    if language == 'python' and require_debugger and info.get("debugpy") != "1.8.22":
        raise ValueError("Debug needs debugpy 1.8.22 in the selected interpreter. "
                         "Install it with that interpreter's pip, then try again.")
    return info


@dataclass(frozen=True)
class LaunchSpec:
    project: Path
    script: Path
    interpreter: Path = Path(sys.executable)
    arguments: tuple[str, ...] = ()
    language: str = 'python'

    def validate(self) -> LaunchSpec:
        project, script = self.project.resolve(), self.script.resolve()
        interpreter = console_interpreter(self.interpreter)
        if not project.is_dir():
            raise ValueError("Open an existing project folder first")
        if not script.is_file() or script.suffix.lower() != ".py":
            raise ValueError("Select a Python (.py) file to run")
        if not script.is_relative_to(project):
            raise ValueError("The script must be inside the opened project")
        if any(not isinstance(arg, str) or "\0" in arg for arg in self.arguments):
            raise ValueError("Script arguments must be text without NUL characters")
        if not interpreter.is_file():
            raise ValueError("The selected Python interpreter is unavailable")
        if not isinstance(self.language, str) or not self.language:
            raise ValueError('Select a runtime backend')
        return LaunchSpec(project, script, interpreter, self.arguments, self.language)

    def worker_arguments(self) -> list[str]:
        spec = self.validate()
        return [str(Path(__file__).with_name("worker.py")), str(spec.project),
                str(spec.script), *spec.arguments]

    def command(self, backend=None) -> list[str]:
        spec = self.validate()
        if spec.language != 'python':
            if not backend or backend.get('api') != 1 or backend.get('id') != spec.language:
                raise ValueError('Validate the installed runtime backend before launch')
            return [str(spec.interpreter), '-I', '-B', '-u', '-X', 'utf8', '-m', backend['runner'],
                    '--project', str(spec.project), '--program', str(spec.script), '--', *spec.arguments]
        return [str(spec.interpreter), "-I", "-B", "-u", "-X", "utf8",
                *spec.worker_arguments()]
