"""Runtime suggestions follow edited source without replacing explicit choices."""
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import openbexi_ide.app as desktop


@pytest.fixture
def runtime_window(app, tmp_path, monkeypatch):
    # These tests exercise the GUI's selection and launch handoff. Plugin
    # discovery and actual native execution are covered separately.
    monkeypatch.setattr(desktop.MainWindow, 'discover_backends', lambda self: None)
    settings = QSettings(str(tmp_path / 'preferences.ini'), QSettings.IniFormat)
    view = desktop.MainWindow(tmp_path, settings)
    view.backend_choices = [{'id': 'spell', 'label': 'SPELL', 'sourceModules': ['spell']}]
    view.populate_backends()
    (tmp_path / 'hello.py').write_text("print('hello')\n", encoding='utf-8')
    yield view
    for index in range(view.tabs.count()):
        view.tabs.widget(index).document().setModified(False)
    view.close()
    app.processEvents()


@pytest.mark.parametrize('action, controller_name', [
    ('run_script', 'run_controller'), ('debug_script', 'debug_controller'),
])
def test_launch_refreshes_edited_imports_and_preserves_override(
        runtime_window, monkeypatch, action, controller_name):
    view = runtime_window
    editor = view.open_file(view.project / 'hello.py')
    launched = []
    monkeypatch.setattr(getattr(view, controller_name), 'start',
                        lambda spec, *args: launched.append(spec.language))
    launch = getattr(view, action)
    assert view.language.currentData() == 'python'

    editor.setPlainText("from spell.lang.functions import Display\nDisplay('hello')\n")
    editor.document().setModified(True)
    launch()
    assert launched[-1] == 'spell'

    editor.setPlainText("print('ordinary Python again')\n")
    editor.document().setModified(True)
    launch()
    assert launched[-1] == 'python'

    # The user's explicit choice must take precedence over a later source edit.
    view.language.setCurrentIndex(view.language.findData('spell'))
    view.language.setCurrentIndex(view.language.findData('python'))
    editor.setPlainText("from spell.lang.functions import Display\nDisplay('hello')\n")
    editor.document().setModified(True)
    launch()
    assert launched[-1] == 'python'


def test_cli_runtime_with_file_reports_missing_backend(runtime_window, monkeypatch):
    view = runtime_window
    monkeypatch.setattr(desktop, 'MainWindow', lambda project: view)
    monkeypatch.setattr(QApplication, 'exec', lambda self: 0)
    assert desktop.main(['--project', str(view.project), '--file',
                         str(view.project / 'hello.py'), '--runtime', 'missing']) == 0
    assert view.statusBar().currentMessage() == 'Runtime is not installed: missing'
    assert view.current_editor().path == view.project / 'hello.py'


def test_cli_runtime_with_file_preserves_explicit_backend(runtime_window, monkeypatch):
    view = runtime_window
    monkeypatch.setattr(desktop, 'MainWindow', lambda project: view)
    monkeypatch.setattr(QApplication, 'exec', lambda self: 0)
    assert desktop.main(['--project', str(view.project), '--file',
                         str(view.project / 'hello.py'), '--runtime', 'spell']) == 0
    assert view.language.currentData() == 'spell'
    assert view.file_runtimes[view.project / 'hello.py'] == 'spell'
