"""Measure installed UI Run after switching between native SPELL and Python."""
import json
from importlib.metadata import version
from pathlib import Path
import shutil
import tempfile
import time

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from openbexi_ide.app import MainWindow

app = QApplication([])


def wait(predicate, timeout=15):
    deadline = time.perf_counter()+timeout
    while not predicate() and time.perf_counter()<deadline:
        app.processEvents()
        time.sleep(.001)
    assert predicate(), 'Installed UI deadline exceeded'


report = {'passed':False, 'ide_version':version('openbexi-ide'), 'cases':[]}
with tempfile.TemporaryDirectory(prefix='hello-runtime-') as temporary:
    project = Path(temporary)/'project'
    shutil.copytree('/opt/openbexi/examples', project)
    window = MainWindow(project, QSettings(str(Path(temporary)/'settings.ini'), QSettings.IniFormat))
    window.show()
    try:
        wait(lambda: any(row['id']=='spell' for row in window.backend_choices))
        for name in ('spell_menu.py','command_wait_telemetry.py','spell_native_prompt.py'):
            window.open_file(project/'test_spell'/name)
            assert window.language.currentData()=='spell'
            window.open_file(project/'hello.py')
            assert window.language.currentData()=='python'
            started = time.perf_counter()
            window.run_action.trigger()
            wait(lambda: not window.run_controller.running)
            elapsed = time.perf_counter()-started
            console = window.console.toPlainText()
            assert 'Hello, Python!' in console and 'exit 0' in console, console
            assert window.run_controller.spec.language=='python'
            assert not (project/'.openbexi/runs').exists()
            assert elapsed<1, f'Hello exceeded the one-second local Run gate: {elapsed}'
            report['cases'].append({'from':name,'runtime':'python','completed_seconds':elapsed})
            window.open_file(project/'test_spell'/name)
            assert window.language.currentData()=='spell'
        window.language.setCurrentIndex(window.language.findData('python'))
        window.open_file(project/'hello.py')
        window.open_file(project/'test_spell/spell_native_prompt.py')
        assert window.language.currentData()=='python'
        report['manual_override_preserved'] = True
        report['passed'] = True
    finally:
        window.close()
        app.processEvents()
        Path('/evidence/hello-runtime.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report),flush=True)
