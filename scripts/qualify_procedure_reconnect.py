"""Exercise simultaneous paused instances and reconnect through real Qt controls."""
import argparse
import json
from importlib.metadata import version
from pathlib import Path
import time
import traceback

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from openbexi_ide.app import MainWindow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    project = args.output / 'project'; project.mkdir()
    source = project / 'same.py'
    source.write_text("from spell.lang.functions import Notify, Display\nNotify('TEMP', '20', 'SUCCESS')\nDisplay('RECONNECTED_INSTANCE_COMPLETE')\n", encoding='utf-8')
    app = QApplication.instance() or QApplication([])
    report = dict(passed=False, version=version('openbexi-ide'), checks=[]); view = None
    def wait(predicate, seconds=90):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate(): return
            time.sleep(.02)
        raise AssertionError(view.console.toPlainText() if view else 'Timed out')
    def open_view():
        result = MainWindow(project, QSettings(str(project / 'preferences.ini'), QSettings.IniFormat))
        result.resize(1600, 1040); result.show(); result.open_file(source)
        wait(lambda: any(row.get('procedureWorkspace') for row in result.backend_choices), 20)
        return result
    try:
        view = open_view(); view.current_editor().breakpoints.add(3)
        workspace = view.procedure_workspace
        view.debug_action.trigger()
        wait(lambda: view.debug_controller.paused and workspace.active_run.service_id)
        first = workspace.active_run
        wait(lambda: workspace.can_start() and view.debug_action.isEnabled())
        view.debug_action.trigger(); second = workspace.active_run
        assert second is not first
        wait(lambda: second.status.upper() == 'PAUSED' and second.service_id)
        assert first.service_id != second.service_id and first.active and second.active
        workspace.history.setCurrentItem(workspace.history.topLevelItem(1))
        assert workspace.selected is first
        view.grab().save(str(args.output / 'two-paused-instances.png'))
        report['checks'].append('Two paused instances of the same procedure have independent IDs and history selection')
        view.close(); wait(lambda: not view.is_busy() and not view.isVisible())
        report['checks'].append('Closing the native view detaches instead of aborting the instances')
        view = open_view(); workspace = view.procedure_workspace
        wait(lambda: len(workspace.runs) == 2 and all(run.active for run in workspace.runs))
        restored = workspace.runs[0]
        workspace.history.setCurrentItem(workspace.history.topLevelItem(0))
        wait(lambda: workspace.claim.isEnabled())
        assert not workspace.control_buttons['continue'].isEnabled()
        workspace.claim.click()
        wait(lambda: workspace.control_buttons['continue'].isEnabled())
        workspace.control_buttons['continue'].click()
        wait(lambda: not restored.active)
        assert restored.status == 'FINISHED' and 'RECONNECTED_INSTANCE_COMPLETE' in restored.output
        assert restored.results[source][2]['status'] == 'SUCCESS'
        report['checks'].append('Reopened native view monitors, explicitly claims, and continues the original instance')
        workspace.history.setCurrentItem(workspace.history.topLevelItem(1))
        wait(lambda: workspace.claim.isEnabled()); workspace.claim.click()
        wait(lambda: workspace.control_buttons['abort'].isEnabled()); workspace.control_buttons['abort'].click()
        wait(lambda: not any(run.active for run in workspace.runs))
        assert workspace.selected.status == 'ABORTED'
        report['checks'].append('The second original instance remains independently abortable')
        view.grab().save(str(args.output / 'restored-history.png'))
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        if view: report['console'] = view.console.toPlainText()
    finally:
        if view: view.close(); app.processEvents()
        (args.output / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
