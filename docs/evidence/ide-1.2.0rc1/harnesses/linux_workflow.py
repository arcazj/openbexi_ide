import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path('/tmp/rc1-evidence')
report = {'version': importlib.metadata.version('openbexi-ide'), 'passed': False, 'checks': []}
display = subprocess.Popen(['Xvfb', ':91', '-screen', '0', '1600x1040x24', '-nolisten', 'tcp', '-ac'])
try:
    for _ in range(100):
        if Path('/tmp/.X11-unix/X91').exists():
            break
        assert display.poll() is None
        time.sleep(.05)
    assert Path('/tmp/.X11-unix/X91').exists()
    environment = dict(os.environ, DISPLAY=':91', QT_QPA_PLATFORM='xcb')
    for script, directory in (('qualify_procedure_workspace.py', 'native-workspace'),
                              ('distribution_desktop.py', 'python-workflow')):
        with (root / (directory + '.log')).open('wb') as log:
            subprocess.run([sys.executable, '-I', '-B', '/opt/rc1-checks/'+script, '--output', str(root / directory)],
                           env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=360, check=True)
        result = json.loads((root / directory / 'result.json').read_text())
        assert result['passed'], result
        report['checks'].append(directory)
    report['passed'] = True
finally:
    display.terminate()
    display.wait(timeout=10)
    (root / 'installed-docker-workflow.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)
