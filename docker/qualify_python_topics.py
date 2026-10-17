"""Every individual Python topic entry point through the installed IDE Run."""
import json
from pathlib import Path
import shutil
import tempfile
import time
from PySide6.QtWidgets import QApplication
from openbexi_ide.controller import RunController
from openbexi_runtime.launch import LaunchSpec

app = QApplication([])
report = {'passed':False,'cases':[]}
with tempfile.TemporaryDirectory(prefix='python-learning-') as temporary:
    project = Path(temporary)/'project'
    shutil.copytree('/opt/openbexi/examples', project)
    directory = project/'test_python_support'
    for path in sorted(directory.glob('python_*.py')):
        if path.name == 'python_menu.py':
            continue
        controller = RunController()
        exits, errors, output = [], [], []
        controller.finished.connect(exits.append)
        controller.error.connect(errors.append)
        controller.output.connect(output.append)
        controller.start(LaunchSpec(project,path))
        deadline = time.monotonic()+60
        while not exits and not errors and time.monotonic()<deadline:
            app.processEvents(); time.sleep(.01)
        text = ''.join(output)
        passed = not errors and exits == [0] and 'All runtime checks passed:' in text
        report['cases'].append(dict(file=path.name,passed=passed,exits=exits,errors=errors,output=text))
        print(path.name, 'PASS' if passed else 'FAIL',flush=True)
        controller.stop()
        while controller.running:
            app.processEvents(); time.sleep(.01)
        Path('/evidence/python-topics.json').write_text(json.dumps(report,indent=2))
report['passed'] = len(report['cases']) == 39 and all(row['passed'] for row in report['cases'])
Path('/evidence/python-topics.json').write_text(json.dumps(report,indent=2))
raise SystemExit(0 if report['passed'] else 1)
