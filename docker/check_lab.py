"""Read-only checks of the running lab, including the browser's WebSocket bridge."""
import base64
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import runpy
import socket
import subprocess
from urllib.request import urlopen

runpy.run_path('/opt/test-lab/health.py')
assert 'OpenBEXI Test Desktop' in subprocess.check_output(['xwininfo', '-root', '-tree'], text=True)
with urlopen('http://127.0.0.1:6080/', timeout=5) as response:
    assert b'url=vnc.html?autoconnect=1&amp;resize=scale' in response.read(), 'Root must open the desktop'
assert os.getuid() == 10003
key = base64.b64encode(os.urandom(16)).decode('ascii')
with socket.create_connection(('127.0.0.1', 6080), timeout=5) as connection:
    connection.sendall((
        'GET /websockify HTTP/1.1\r\nHost: localhost:6080\r\n'
        'Upgrade: websocket\r\nConnection: Upgrade\r\n'
        'Sec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: binary\r\n'
        f'Sec-WebSocket-Key: {key}\r\n\r\n').encode('ascii'))
    response = b''
    while b'\r\n\r\n' not in response:
        chunk = connection.recv(4096)
        assert chunk, 'WebSocket upgrade closed'
        response += chunk
        assert len(response) < 16384
    headers, frame = response.split(b'\r\n\r\n', 1)
    expected = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode('ascii')).digest())
    assert headers.startswith(b'HTTP/1.1 101 ') and expected in headers, headers
    while len(frame) < 14:
        chunk = connection.recv(4096)
        assert chunk, 'VNC bridge closed'
        frame += chunk
    assert frame[:2] == b'\x82\x0c' and frame[2:14].startswith(b'RFB '), frame

result = {
    'passed': True, 'uid': os.getuid(),
    'versions': {name: version(name) for name in ('openbexi-ide', 'openbexi-spell-plugin', 'PySide6-Essentials', 'debugpy')},
    'checks': ['persistent desktop launcher running with an X11 window', 'root URL redirects to the desktop', 'noVNC HTTP assets', 'WebSocket upgrade and real VNC banner',
               'DSS health', 'shared session health', 'durable mutual TLS health'],
    'wheels': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in Path('/opt/wheels').glob('*.whl')},
}
print(json.dumps(result, indent=2))
