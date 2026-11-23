"""Start the installed IDE on a local noVNC desktop with its public SPELL panel."""
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen


def health():
    with urlopen('http://127.0.0.1:6080/vnc.html', timeout=2) as response:
        if response.status != 200:
            raise RuntimeError('noVNC is unavailable')
    with socket.create_connection(('127.0.0.1', 5900), timeout=2) as connection:
        if not connection.recv(12).startswith(b'RFB '):
            raise RuntimeError('VNC is unavailable')
    windows = subprocess.check_output(['xwininfo', '-root', '-tree'], timeout=3)
    if b'OpenBEXI IDE' not in windows:
        raise RuntimeError('The installed OpenBEXI IDE window is unavailable')


def desktop():
    project = Path('/workspace/projects/demo')
    if not project.exists():
        project.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree('/opt/openbexi/examples', project)
    services = []
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    def start(command):
        process = subprocess.Popen(command, start_new_session=True)
        services.append(process)
        return process

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        display = start(['Xvfb', ':0', '-screen', '0', '1600x1000x24', '-nolisten', 'tcp', '-ac'])
        deadline = time.monotonic() + 15
        while not Path('/tmp/.X11-unix/X0').exists():
            if display.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('X11 display startup failed')
            time.sleep(0.1)
        start(['openbox'])
        start(['x11vnc', '-display', ':0', '-rfbport', '5900', '-localhost', '-nopw', '-forever', '-shared', '-noxdamage'])
        start(['/usr/bin/websockify', '--web=/usr/share/novnc', '0.0.0.0:6080', '127.0.0.1:5900'])
        gui = start([sys.executable, '-I', '-m', 'openbexi_ide.app', '--project', str(project)])
        while not stopping:
            if gui.poll() is not None:
                return gui.returncode
            if any(p.poll() is not None for p in services[:-1]):
                raise RuntimeError('A desktop service stopped')
            time.sleep(0.25)
        return 0
    finally:
        for p in reversed(services):
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
        for p in reversed(services):
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()


if __name__ == '__main__':
    if sys.argv[1:] == ['health'] or Path(__file__).name == 'health.py':
        health()
    elif sys.argv[1:] in ([], ['desktop']):
        raise SystemExit(desktop())
    else:
        raise SystemExit('Expected desktop or health')
