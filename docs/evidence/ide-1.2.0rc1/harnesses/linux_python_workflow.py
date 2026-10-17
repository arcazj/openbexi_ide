import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path('/tmp/rc1-evidence')
display = subprocess.Popen(['Xvfb', ':92', '-screen', '0', '1600x1040x24', '-nolisten', 'tcp', '-ac'])
try:
    for _ in range(100):
        if Path('/tmp/.X11-unix/X92').exists():
            break
        assert display.poll() is None
        time.sleep(.05)
    assert Path('/tmp/.X11-unix/X92').exists()
    with (root/'python-workflow-canonical.log').open('wb') as log:
        result = subprocess.run([sys.executable, '-I', '-B', '/opt/rc1-checks/distribution_desktop.py',
                                 '--output', str(root/'python-workflow-canonical')],
                                env=dict(os.environ, DISPLAY=':92', QT_QPA_PLATFORM='xcb'),
                                stdout=log, stderr=subprocess.STDOUT, timeout=300)
    print((root/'python-workflow-canonical/result.json').read_text(), flush=True)
    raise SystemExit(result.returncode)
finally:
    display.terminate()
    display.wait(timeout=10)
