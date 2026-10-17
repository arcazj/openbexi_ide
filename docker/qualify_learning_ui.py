"""Installed CLI/runtime selection and real X11 IDE Run action with screenshots."""
import json
from pathlib import Path
import tempfile
import shutil
import time
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from openbexi_ide.app import MainWindow, main

app = QApplication([])
report = {'passed':False}
started = time.monotonic()
stage = 'select'
with tempfile.TemporaryDirectory(prefix='learning-ui-') as temporary:
    project = Path(temporary)/'project'
    shutil.copytree('/opt/openbexi/examples', project)
    def inspect():
        global stage
        try:
            assert time.monotonic()-started < 60, 'Installed IDE UI timed out'
            windows = [w for w in app.topLevelWidgets() if isinstance(w,MainWindow)]
            if not windows:
                return
            window = windows[0]
            if stage == 'select' and window.language.currentData() == 'spell':
                report['selected_runtime'] = window.language.currentData()
                assert window.run_action.isEnabled()
                window.run_action.trigger()
                stage = 'run'
            elif stage == 'run' and not window.is_busy():
                output = window.console.toPlainText()
                assert 'SPELL_COMMAND_TELEMETRY_PASS' in output, output
                report['console'] = output
                assert window.grab().save('/evidence/native-ide-run.png')
                report['passed'] = True
                timer.stop()
                window.close()
                app.quit()
        except Exception as error:
            report['error'] = str(error)
            timer.stop()
            app.quit()
    timer = QTimer()
    timer.timeout.connect(inspect)
    timer.start(50)
    main(['--project',str(project),'--file',str(project/'test_spell/command_wait_telemetry.py'),'--runtime','spell'])
Path('/evidence/learning-ui.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
raise SystemExit(0 if report['passed'] else 1)
