from pathlib import Path
import json
import socket
from urllib.request import urlopen
from openbexi_runtime.cli import request

for url in ('http://127.0.0.1:6080/vnc.html', 'http://127.0.0.1:8085/healthz', 'http://127.0.0.1:9010/healthz'):
    with urlopen(url, timeout=2) as response:
        assert response.status == 200
info = json.loads(Path('/workspace/connections/durable-alice.json').read_text())
assert request(info['url'], '/healthz', tls=info['tls'])['status'] == 'ready'
with socket.create_connection(('127.0.0.1', 5900), timeout=2) as vnc:
    assert vnc.recv(12).startswith(b'RFB ')
