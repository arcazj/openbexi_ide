from pathlib import Path
import time

import pytest
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from openbexi_ide.app import MainWindow
from openbexi_ide.editor import FileConflictError
from openbexi_ide.fonts import configure_fonts
from openbexi_runtime.processes import process_alive


@pytest.fixture
def window(app, tmp_path):
    folder = tmp_path / "my project"; folder.mkdir()
    (folder / "hello.py").write_text("print('Hello from ordinary Python')\n", encoding="utf-8")
    settings = QSettings(str(tmp_path / "preferences.ini"), QSettings.IniFormat)
    view = MainWindow(folder, settings)
    view.show(); app.processEvents()
    yield view
    for index in range(view.tabs.count()):
        view.tabs.widget(index).document().setModified(False)
    view.run_controller.stop()
    wait_until(app, lambda: not view.run_controller.running)
    view.close(); app.processEvents()


def wait_until(app, predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        # Windows QTest.qWait holds the GIL; the real interpreter probe uses
        # Python workers which need to make progress during this Qt test loop.
        app.processEvents(); time.sleep(0.01)
    assert predicate(), "UI operation did not finish before its deadline"


def test_runtime_follows_file_and_hello_keeps_plain_python(window, app):
    # Metadata stands in for the plugin; hello uses the real Python worker.
    if window.backend_probe:
        window.backend_probe.cancel.set()
    window.backend_epoch += 1
    window.backend_choices = [{'id':'spell', 'label':'SPELL', 'sourceModules':['spell']}]
    window.populate_backends()
    spell = window.project/'procedure.py'
    spell.write_text("from spell.lang.functions import Display\nDisplay('ready')\n")
    window.open_file(spell)
    assert window.language.currentData() == 'spell'
    window.open_file(window.project/'hello.py')
    assert window.language.currentData() == 'python'
    window.run_action.trigger()
    wait_until(app, lambda: not window.run_controller.running)
    assert window.run_controller.spec.language == 'python'
    assert 'Hello from ordinary Python' in window.console.toPlainText()
    assert not (window.project/'.openbexi/runs').exists()
    window.open_file(spell)
    assert window.language.currentData() == 'spell'
    window.language.setCurrentIndex(window.language.findData('python'))
    window.open_file(window.project/'hello.py')
    window.open_file(spell)
    assert window.language.currentData() == 'python', 'Explicit choice must survive tab switches'
    window.populate_backends()
    assert window.language.currentData() == 'python', 'Plugin refresh must preserve the choice'


def test_mentions_of_spell_do_not_select_a_plugin(window):
    if window.backend_probe:
        window.backend_probe.cancel.set()
    window.backend_epoch += 1
    window.backend_choices = [{'id':'spell', 'label':'SPELL', 'sourceModules':['spell']}]
    window.populate_backends()
    script = window.project/'notes.py'
    script.write_text("# from spell import anything\nprint('import spell')\n")
    window.open_file(script)
    assert window.language.currentData() == 'python'


def test_open_edit_save_and_external_change_protection(window):
    editor = window.open_file(window.project / "hello.py")
    QTest.keyClick(editor, Qt.Key_End, Qt.ControlModifier)
    QTest.keyClicks(editor, "print('edited')")
    assert editor.document().isModified()
    assert window.save_current()
    assert "edited" in editor.path.read_text()
    editor.path.write_text("# another developer changed the file\n")
    editor.appendPlainText("# my unsaved change")
    with pytest.raises(FileConflictError):
        editor.save()
    assert editor.path.read_text() == "# another developer changed the file\n"


def test_unsaved_project_change_can_be_cancelled(window, monkeypatch, tmp_path):
    editor = window.open_file(window.project / "hello.py")
    editor.appendPlainText("# keep my work")
    replacement = tmp_path / "other"; replacement.mkdir()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Cancel)
    assert not window.open_project(replacement)
    assert window.current_editor() is editor


def test_run_normal_python_and_restart(window, app):
    window.open_file(window.project / "hello.py")
    for _ in range(2):
        window.run_action.trigger()
        wait_until(app, lambda: not window.run_controller.running)
        assert "Hello from ordinary Python" in window.console.toPlainText()
        assert "Finished · exit 0" in window.console.toPlainText()
        assert window.run_action.isEnabled()


def test_themes_breakpoint_gutter_find_and_render(window, app, tmp_path):
    editor = window.open_file(window.project / "hello.py")
    QTest.mouseClick(editor.gutter, Qt.LeftButton, pos=QPoint(10, 8))
    assert 1 in editor.breakpoints
    window.show_find(); window.find.setText("ordinary"); window.find_next()
    assert editor.textCursor().selectedText() == "ordinary"
    window.find.hide()
    output = Path(__file__).resolve().parents[1] / ".qualification" / "v0.2" / "desktop-ui"
    output.mkdir(parents=True, exist_ok=True)
    for theme in ("light", "dark"):
        if window.theme != theme: window.toggle_theme()
        app.processEvents(); QTest.qWait(80)
        assert window.grab().save(str(output / f"{theme}.png"))
        assert editor.colors == window.colors


def test_new_project_and_file_outside_project_do_not_leak(window, tmp_path):
    outside = tmp_path / "outside.py"; outside.write_text("print('outside')")
    assert window.open_file(outside) is None
    assert "containing this file" in window.console.toPlainText()


def test_failed_script_reports_exit_and_stdin_is_interactive(window, app):
    script = window.project / "input.py"
    script.write_text("name=input('Name: '); print('Hello',name); raise ValueError('visible error')\n")
    window.open_file(script); window.run_script()
    wait_until(app, lambda: "Name:" in window.console.toPlainText())
    window.input.setText("visitor"); QTest.keyClick(window.input, Qt.Key_Return)
    wait_until(app, lambda: not window.run_controller.running)
    assert "Hello visitor" in window.console.toPlainText()
    assert "ValueError: visible error" in window.console.toPlainText()
    assert "Finished · exit 1" in window.console.toPlainText()


def test_stop_while_checking_interpreter_does_not_launch_late(window, app):
    window.open_file(window.project / "hello.py")
    window.run_script(); window.stop_script()
    assert not window.run_controller.running
    QTest.qWait(300); app.processEvents()
    assert "Hello from ordinary Python" not in window.console.toPlainText()
    window.run_script()
    wait_until(app, lambda: not window.run_controller.running)
    assert "Hello from ordinary Python" in window.console.toPlainText()


def test_real_debugger_widgets_show_frame_variables_and_can_stop(window, app):
    script = window.project / "inspect.py"
    script.write_text("number = 21\nanswer = number * 2\nprint(answer)\n")
    editor = window.open_file(script); editor.toggle_breakpoint(2)
    window.debug_action.trigger()
    wait_until(app, lambda: window.debug_controller.paused)
    wait_until(app, lambda: window.variables.topLevelItemCount() > 0
               and window.variables.topLevelItem(0).childCount() > 0
               and window.variables.topLevelItem(0).child(0).text(0) != "Loading…")
    assert editor.execution_line == 2
    assert window.stack_list.count() > 0
    assert window.continue_action.isEnabled() and window.into_action.isEnabled()
    window.expression.setText("number * 2"); QTest.keyClick(window.expression, Qt.Key_Return)
    wait_until(app, lambda: window.eval_result.text() == "42")
    output = Path(__file__).resolve().parents[1] / ".qualification" / "v0.2" / "desktop-ui"
    app.processEvents(); window.grab().save(str(output / "debugger.png"))
    window.stop_action.trigger()
    wait_until(app, lambda: not window.debug_controller.running)
    assert window.run_action.isEnabled() and not window.continue_action.isEnabled()


def test_large_unbroken_output_is_bounded_and_ui_remains_responsive(window, app):
    script = window.project / "large.py"
    script.write_text("print('x' * 1200000); print('TAIL-MARKER')\n")
    window.open_file(script); window.run_script()
    wait_until(app, lambda: not window.run_controller.running)
    assert "TAIL-MARKER" in window.console.toPlainText()
    assert window.console.document().characterCount() <= 500_000


def test_incremental_utf8_stream_is_not_corrupted(window, app):
    script = window.project / "unicode_stream.py"
    script.write_text("import os,time\nraw='café 😀'.encode('utf-8')\n"
                      "for byte in raw:\n    os.write(1,bytes([byte]))\n    time.sleep(0.01)\n", encoding="utf-8")
    window.open_file(script); window.run_script()
    wait_until(app, lambda: not window.run_controller.running)
    assert "café 😀" in window.console.toPlainText()
    assert "\ufffd" not in window.console.toPlainText()


def test_window_close_reaps_running_user_process_and_child(window, app):
    script = window.project / "close_tree.py"
    script.write_text("import os,subprocess,sys,time\n"
        "child=subprocess.Popen([sys.executable,'-I','-c','import time;time.sleep(60)'])\n"
        "print('PIDS',os.getpid(),child.pid,flush=True)\ntime.sleep(60)\n")
    window.open_file(script); window.run_script()
    wait_until(app, lambda: "PIDS" in window.console.toPlainText())
    pids = [int(part) for part in window.console.toPlainText().split("PIDS ")[1].splitlines()[0].split()]
    window.close()
    wait_until(app, lambda: not window.run_controller.running and not window.isVisible())
    assert not any(process_alive(pid) for pid in pids)
