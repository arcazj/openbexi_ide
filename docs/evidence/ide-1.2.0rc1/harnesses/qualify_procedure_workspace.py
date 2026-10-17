"""Exercise the installed/native procedure workspace through actual Qt controls."""
import argparse
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from openbexi_ide.app import MainWindow
from openbexi_ide.fonts import configure_fonts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    configure_fonts(app)
    report = {'passed': False, 'cases': [], 'platform': sys.platform, 'requested_image': os.environ.get('OPENBEXI_SPELL_IMAGE', 'backend default')}
    view = None
    def wait(predicate, timeout=90):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            app.processEvents(); time.sleep(.01)
        assert predicate(), view.console.toPlainText() if view else 'Workspace timed out'
    try:
        with nullcontext(args.output.resolve() / 'project') as directory:
            project = Path(directory)
            project.mkdir(exist_ok=True)
            script = project / 'procedure.py'
            source = '''from spell.lang.functions import Notify, Prompt, Display, StartProc
from spell.lang.constants import YES_NO, ALPHA, NUM, LIST
Notify('Voltage', '28.0', 'SUCCESS')
assert Prompt('Ready to execute?', Type=YES_NO, HandleError=False) is True
assert Prompt('Operator name', Type=ALPHA, HandleError=False) == 'Ada'
assert Prompt('Setpoint', Type=NUM, HandleError=False) == -2.5
assert Prompt('Choose station', ['A: North', 'B: South'], Type=LIST|ALPHA, HandleError=False) == 'South'
assert StartProc('child', HandleError=False)
Display('PROCEDURE_WORKSPACE_PASS')
'''
            script.write_text(source, encoding='utf-8')
            (project / 'child.py').write_text("from spell.lang.functions import Prompt, Display\nfrom spell.lang.constants import YES_NO\nassert Prompt('Child decision', Type=YES_NO, HandleError=False) is False\nDisplay('CHILD_WORKSPACE_PASS')\n", encoding='utf-8')
            report['source_sha256'] = hashlib.sha256(script.read_bytes()).hexdigest()
            view = MainWindow(project, QSettings(str(project / 'preferences.ini'), QSettings.IniFormat))
            view.resize(1600, 1040); view.show(); view.open_file(script)
            wait(lambda: any(row.get('procedureWorkspace') for row in view.backend_choices), 20)
            for mode in ('Run', 'Debug'):
                points = view.current_editor().breakpoints
                if mode == 'Debug':
                    points.add(3)
                (view.run_action if mode == 'Run' else view.debug_action).trigger()
                workspace = view.procedure_workspace
                run = workspace.active_run
                assert run and run.mode == mode
                if mode == 'Debug':
                    wait(lambda: view.debug_controller.paused or not view.is_busy())
                    assert view.debug_controller.paused, view.console.toPlainText()
                    view.debug_controller.control('continue')
                seen = []
                for expected, answer in (('Ready to execute?', '0'), ('Operator name', 'Ada'), ('Setpoint', '-2.5'), ('Choose station', '1'), ('Child decision', '1')):
                    wait(lambda: (run.prompt is not None and run.prompt['promptId'] not in seen) or not view.is_busy())
                    assert run.prompt and run.prompt['text'] == expected, (run.prompt, view.console.toPlainText())
                    seen.append(run.prompt['promptId'])
                    wait(lambda: workspace.commit.isEnabled())
                    workspace.refresh(); app.processEvents()
                    if expected == 'Ready to execute?':
                        assert run.current.get(script) == 4, run.current
                        assert run.results[script][3]['status'] == 'SUCCESS', run.results
                        assert '28.0' in run.results[script][3]['value']
                        assert run.sources[script] == source
                        assert workspace.model.data(workspace.model.index(3, 0), Qt.BackgroundRole) is not None
                        assert view.grab().save(str(args.output / (mode.lower() + '-prompt.png')))
                        view.toggle_theme(); workspace.refresh(); app.processEvents()
                        assert view.grab().save(str(args.output / (mode.lower() + '-prompt-dark.png')))
                        view.toggle_theme(); workspace.refresh(); app.processEvents()
                    if workspace.choices:
                        button = next(button for button in workspace.choices.buttons() if button.property('wire_value') == answer)
                        QTest.mouseClick(button, Qt.LeftButton, pos=QPoint(8, button.height() // 2))
                        QTest.mouseClick(workspace.reset, Qt.LeftButton)
                        assert workspace.choices.checkedButton() is None
                        QTest.mouseClick(button, Qt.LeftButton, pos=QPoint(8, button.height() // 2))
                    else:
                        workspace.answer_field.setText(answer)
                    QTest.mouseClick(workspace.commit, Qt.LeftButton)
                    assert run.answering or run.prompt is None
                wait(lambda: not view.is_busy())
                assert run.status == 'Finished (0)', (run.status, view.console.toPlainText())
                assert 'PROCEDURE_WORKSPACE_PASS' in run.output and 'CHILD_WORKSPACE_PASS' in run.output
                assert project / 'child.py' in run.sources
                assert not workspace.prompt_panel.isVisible()
                assert view.grab().save(str(args.output / (mode.lower() + '-results.png')))
                report['cases'].append(dict(mode=mode, passed=True, prompts=len(seen), sources=len(run.sources), results=len(run.results.get(script, {})), output=run.output))
            assert len(workspace.runs) == 2
            workspace.history.setCurrentItem(workspace.history.topLevelItem(1))
            assert workspace.selected.mode == 'Run' and workspace.model.lines == source.splitlines()
            # Stop a third run while its prompt is open, then prove the next run owns a fresh prompt.
            view.run_action.trigger(); run = workspace.active_run
            wait(lambda: run.prompt is not None or not view.is_busy())
            assert run.prompt
            QTest.mouseClick(workspace.abort, Qt.LeftButton)
            wait(lambda: not view.is_busy())
            assert run.status == 'Aborted'
            view.run_action.trigger(); fresh = workspace.active_run
            wait(lambda: fresh.prompt is not None or not view.is_busy())
            assert fresh is not run and fresh.prompt
            view.stop_script(); wait(lambda: not view.is_busy())
            report['stop_rerun'] = True
            # Ordinary Python still uses its fast worker after native execution.
            hello = project / 'hello.py'; hello.write_text("print('PLAIN_PYTHON_PASS')\n")
            view.open_file(hello); view.run_action.trigger()
            assert view.run_controller.running and not view.debug_controller.running
            wait(lambda: not view.is_busy())
            assert 'PLAIN_PYTHON_PASS' in view.console.toPlainText()
            report['ordinary_python'] = True
            report['history'] = len(workspace.runs)
            report['runtime_images'] = sorted({json.loads(path.read_text())['image']
                for path in project.glob('.openbexi/runs/*/manifest.json')})
            report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        if view:
            report['console'] = view.console.toPlainText()
            view.grab().save(str(args.output / 'failure.png'))
    finally:
        if view:
            view.stop_script(); wait(lambda: not view.is_busy())
            view.close(); app.processEvents()
        (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key not in {'cases', 'console'}}), flush=True)
    return not report['passed']


if __name__ == '__main__':
    raise SystemExit(main())
