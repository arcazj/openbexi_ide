import hashlib
import sys
import threading
import time

import pytest
from PySide6.QtCore import QSettings, QTimer

from openbexi_ide.app import MainWindow
from openbexi_ide import controller
from openbexi_runtime.launch import console_interpreter, interpreter_info


def preference_key(project):
    return 'interpreter/' + hashlib.sha256(str(project.resolve()).encode()).hexdigest()


def wait_until(app, predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert predicate(), 'Interpreter selection did not finish before its deadline'


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    # Selection is tested independently of the initial background plugin scan.
    monkeypatch.setattr(MainWindow, 'discover_backends', lambda self: None)
    settings = QSettings(str(tmp_path / 'preferences.ini'), QSettings.IniFormat)
    view = MainWindow(tmp_path, settings)
    view.show()
    yield view
    view.close()
    app.processEvents()


@pytest.mark.parametrize('name', ['pip', 'pip3', 'pip3.13', 'pip.exe',
                                 'pip3.13.exe', 'PIP.EXE', 'pip3-script.py'])
def test_pip_launchers_fail_before_starting_process(tmp_path, monkeypatch, name):
    launcher = tmp_path / name
    launcher.touch()
    python = tmp_path / 'python3.13'
    python.touch()

    def must_not_start(*args, **kwargs):
        pytest.fail('Package installers must never be probed as Python')

    monkeypatch.setattr('openbexi_runtime.processes.start_owned_process', must_not_start)
    with pytest.raises(ValueError, match='select a Python executable') as error:
        interpreter_info(launcher)
    assert str(python) in str(error.value)


def test_selecting_pip_preserves_valid_interpreter_and_preference(window, monkeypatch):
    launcher = window.project / 'pip3.13'
    launcher.touch()
    previous = window.interpreter
    key = preference_key(window.project)
    window.settings.setValue(key, str(previous))
    monkeypatch.setattr('openbexi_ide.app.QFileDialog.getOpenFileName',
                        lambda *args: (str(launcher), ''))
    window.choose_interpreter()
    assert window.interpreter == previous
    assert window.settings.value(key) == str(previous)
    assert window.pending_interpreter is None
    assert 'select a Python executable' in window.console.toPlainText()


def test_saved_pip_launcher_falls_back_to_automatic_python(app, tmp_path, monkeypatch):
    monkeypatch.setattr(MainWindow, 'discover_backends', lambda self: None)
    launcher = tmp_path / 'pip3.13'
    launcher.touch()
    settings = QSettings(str(tmp_path / 'preferences.ini'), QSettings.IniFormat)
    key = preference_key(tmp_path)
    settings.setValue(key, str(launcher))
    view = MainWindow(tmp_path, settings)
    try:
        assert view.interpreter == console_interpreter(sys.executable)
        assert settings.value(key) == str(view.interpreter)
        assert 'select a Python executable' in view.console.toPlainText()
    finally:
        view.close()
        app.processEvents()


def test_python_selection_is_validated_before_persisting(window, app, monkeypatch):
    key = preference_key(window.project)
    monkeypatch.setattr('openbexi_ide.app.QFileDialog.getOpenFileName',
                        lambda *args: (sys.executable, ''))
    window.choose_interpreter()
    assert window.pending_interpreter is not None
    assert not window.settings.contains(key)
    wait_until(app, lambda: window.pending_interpreter is None)
    assert window.settings.value(key) == str(console_interpreter(sys.executable))
    assert window.interpreter_button.text().startswith('Python 3.13.')


def test_failed_probe_keeps_selection_and_event_loop_responsive(window, app, monkeypatch):
    previous = window.interpreter
    key = preference_key(window.project)
    window.settings.setValue(key, str(previous))
    entered, release = threading.Event(), threading.Event()
    candidate = window.project / 'other-program.exe'
    candidate.touch()

    def slow_invalid_probe(*args, **kwargs):
        entered.set()
        assert release.wait(10), 'Test did not release interpreter probe'
        raise ValueError('This executable is not CPython 3.13')

    monkeypatch.setattr(controller, 'interpreter_info', slow_invalid_probe)
    monkeypatch.setattr('openbexi_ide.app.QFileDialog.getOpenFileName',
                        lambda *args: (str(candidate), ''))
    try:
        window.choose_interpreter()
        wait_until(app, entered.is_set)
        ticks = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        wait_until(app, lambda: bool(ticks))
        assert window.interpreter == previous
        assert window.settings.value(key) == str(previous)
    finally:
        release.set()
    wait_until(app, lambda: window.pending_interpreter is None)
    assert window.interpreter == previous
    assert window.settings.value(key) == str(previous)
    assert 'Select a Python executable' in window.console.toPlainText()


def test_project_change_cancels_pending_selection(window, app, monkeypatch):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original = window.project
    key = preference_key(original)

    def slow_valid_probe(*args, **kwargs):
        entered.set()
        assert release.wait(10), 'Test did not release interpreter probe'
        finished.set()
        return {'version': [3, 13, 15], 'executable': sys.executable, 'backends': []}

    monkeypatch.setattr(controller, 'interpreter_info', slow_valid_probe)
    monkeypatch.setattr('openbexi_ide.app.QFileDialog.getOpenFileName',
                        lambda *args: (sys.executable, ''))
    try:
        window.choose_interpreter()
        wait_until(app, entered.is_set)
        pending = window.interpreter_probe
        other = original / 'other-project'
        other.mkdir()
        assert window.open_project(other)
        assert pending.cancel.is_set()
    finally:
        release.set()
    wait_until(app, finished.is_set)
    app.processEvents()
    assert not window.settings.contains(key)
    assert not window.settings.contains(preference_key(other))
