"""Exercise Run and debugpy through the installed offline bundle's Qt widgets."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--usability', action='store_true')
    parser.add_argument('--examples', type=Path)
    args = parser.parse_args()
    evidence = args.output.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    import openbexi_ide.app as desktop
    import openbexi_runtime
    assert Path(desktop.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    assert Path(openbexi_runtime.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    project = evidence / 'user project'
    project.mkdir()
    source = project / 'ordinary_python.py'
    source.write_text("value = 21\ncheckpoint = value + 1\nanswer = checkpoint + 1\nprint('BUNDLED_PYTHON_' + str(answer))\n", encoding='utf-8')
    application = QApplication([])
    view = desktop.MainWindow(project, QSettings(str(evidence / 'preferences.ini'), QSettings.IniFormat))
    view.show()
    report = {'passed': False, 'version': importlib.metadata.version('openbexi-ide'),
              'python': sys.executable, 'prefix': sys.prefix, 'origin': desktop.__file__,
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'checks': [], 'scope': 'Actual installed Qt widgets offscreen; not noVNC/clean-machine evidence'}

    def wait(predicate, timeout=45):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            application.processEvents()
            QTest.qWait(10)
            time.sleep(0.005)
        debug = view.debug_controller
        assert predicate(), (view.console.toPlainText(), {'active': debug.running,
            'validating': getattr(debug, 'validating', None), 'paused': debug.paused,
            'adapter_state': str(debug.adapter.state()), 'adapter_pid': debug.adapter.processId(),
            'terminal_state': str(debug.terminal.state()), 'terminal_pid': debug.terminal.processId(),
            'pending': {key: value[0] for key, value in debug.pending.items()}})

    def request(command, arguments):
        result = []
        view.debug_controller.view_request(command, arguments, result.append)
        wait(lambda: bool(result))
        return result[0]

    try:
        assert view.interpreter == Path(sys.executable), (view.interpreter, sys.executable)
        view.open_file(source)
        view.run_action.trigger()
        wait(lambda: not view.run_controller.running)
        assert 'BUNDLED_PYTHON_23' in view.console.toPlainText()
        report['checks'].append('Default private CPython interpreter and ordinary Python Run')
        editor = view.current_editor()
        editor.toggle_breakpoint(2)
        frames = []
        view.debug_controller.stack_changed.connect(frames.append)
        view.debug_action.trigger()
        wait(lambda: view.debug_controller.paused and bool(frames))
        assert editor.execution_line == 2
        frame = frames[-1][0]
        scopes = request('scopes', {'frameId': frame['id']})['scopes']
        local = next(scope for scope in scopes if scope['name'] == 'Locals')
        reference = local['variablesReference']
        variables = request('variables', {'variablesReference': reference})['variables']
        assert any(v['name'] == 'value' and v['value'] == '21' for v in variables)
        edited = request('setVariable', {'variablesReference': reference, 'name': 'value', 'value': '40'})
        assert edited['value'] == '40'
        assert view.grab().save(str(evidence / 'python-debugger.png'))
        editor.toggle_breakpoint(2)
        view.into_action.trigger()
        wait(lambda: view.debug_controller.paused and editor.execution_line == 3)
        view.continue_action.trigger()
        wait(lambda: not view.debug_controller.running)
        assert 'BUNDLED_PYTHON_42' in view.console.toPlainText()
        report['checks'].append('debugpy breakpoint, stack, variables, edit, Step and Continue')
        if args.usability:
            helper = project / 'helpers.py'
            helper.write_text('def saved(): pass\n')
            main = project / 'completion.py'
            main.write_text('from helpers import calculate\ncalculate()\npri')
            helper_editor = view.open_file(helper)
            helper_editor.selectAll()
            helper_editor.insertPlainText('# unsaved\n\ndef calculate():\n    return 42\n')
            source_editor = view.open_file(main)
            source_editor.goto_location(3, 3)
            application.processEvents()
            QTest.keyClick(source_editor, Qt.Key_Space, Qt.ControlModifier)
            wait(lambda: source_editor.completer.popup().isVisible())
            QTest.keyClick(source_editor, Qt.Key_Return)
            assert source_editor.toPlainText().endswith('print')
            source_editor.goto_location(2, 4)
            QTest.keyClick(source_editor, Qt.Key_F12)
            wait(lambda: view.current_editor() is helper_editor)
            assert helper_editor.textCursor().blockNumber() == 2
            assert helper_editor.document().isModified() and helper.read_text() == 'def saved(): pass\n'
            helper_editor.setReadOnly(True)
            QTest.keyClick(helper_editor, Qt.Key_O, Qt.ControlModifier | Qt.ShiftModifier)
            wait(lambda: helper_editor.symbol_dialog is not None)
            dialog = helper_editor.symbol_dialog
            QTest.keyClicks(dialog.search, 'calculate helpers')
            assert dialog.results.count() == 1
            QTest.keyClick(dialog.search, Qt.Key_Return)
            assert view.grab().save(str(evidence / 'completion-navigation.png'))
            report['checks'].append('Installed Ctrl+Space insertion, F12 unsaved definition and read-only symbol navigation')
        if args.examples:
            example_root = args.examples.resolve()
            report['examples'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in example_root.glob('*.py')}
            result = subprocess.run([sys.executable, '-I', '-B', str(example_root / 'test_Python_in_deep.py'),
                                     '--stream', '3', '--delay', '0'], capture_output=True, text=True, timeout=60)
            (evidence / 'python-example.log').write_text(result.stdout + result.stderr, encoding='utf-8')
            assert result.returncode == 0 and '15 chapters passed' in result.stdout and result.stdout.count('  PASS') == 15
            graphic = example_root/'test_python_support/graphics_demo.py'
            dashboard = runpy.run_path(str(graphic if graphic.is_file() else example_root/'graphics_demo.py'))['Dashboard']()
            dashboard.show()
            application.processEvents()
            try:
                QTest.mouseClick(dashboard.play, Qt.LeftButton)
                assert not dashboard.timer.isActive()
                previous = dashboard.samples.ticks
                QTest.mouseClick(dashboard.add_button, Qt.LeftButton)
                assert dashboard.samples.ticks == previous + 1
                for invalid in ('bad', float('nan'), float('inf')):
                    dashboard.command({'action': 'add', 'value': invalid})
                assert dashboard.samples.ticks == previous + 1
                dashboard.command({'action': 'resume'})
                wait(lambda: dashboard.samples.ticks > previous + 1)
                assert dashboard.grab().save(str(evidence / 'graphics-example.png'))
                QTest.mouseClick(dashboard.close_button, Qt.LeftButton)
                assert not dashboard.isVisible() and not dashboard.timer.isActive()
            finally:
                dashboard.close()
            report['checks'].append('Private runtime deep Python 15 chapters and graphics animation/controls/close')
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        (evidence / 'console.txt').write_text(view.console.toPlainText(), encoding='utf-8')
        view.run_controller.stop()
        view.debug_controller.stop()
        wait(lambda: not view.is_busy())
        for index in range(view.tabs.count()):
            view.tabs.widget(index).document().setModified(False)
        view.close()
        application.processEvents()
        (evidence / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
