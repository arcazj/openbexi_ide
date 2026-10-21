"""Small HTTP client and per-project discovery for the local execution service."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from .launch import clean_environment, console_interpreter
from .procedure_service import workspace_directory, implementation_id


class Client:
    def __init__(self, url, token):
        self.url = url.rstrip('/'); self.token = token
        self.opener = build_opener(ProxyHandler({}))

    def request(self, path, data=None, timeout=45):
        request = Request(self.url + path,
            data=json.dumps(data, allow_nan=False).encode() if data is not None else None,
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                return json.load(response)
        except HTTPError as error:
            try:
                message = json.load(error)['error']
            except (ValueError, KeyError):
                message = str(error)
            finally:
                error.close()
            raise RuntimeError(message) from None

    @classmethod
    def connect(cls, endpoint, name='Desktop', role='operator'):
        config = json.loads(Path(endpoint).read_text(encoding='utf-8'))
        client = cls(config['url'], config[role])
        result = client.request('/api/connect', {'name': name}, timeout=3)
        client.token = result['client']
        return client


def ensure_service(project):
    directory = workspace_directory(project); directory.mkdir(parents=True, exist_ok=True)
    endpoint = directory / 'endpoint.json'
    # Serialise service discovery across desktop and JetBrains launchers.
    lock = open(directory / 'launch.lock', 'a+b')
    if lock.tell() == 0:
        lock.write(b'0'); lock.flush()
    lock.seek(0)
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        client = None
        try:
            client = Client.connect(endpoint, 'Service discovery')
            state = client.request('/api/state', timeout=2)
        except (OSError, RuntimeError, ValueError, KeyError):
            pass
        else:
            config = json.loads(endpoint.read_text(encoding='utf-8'))
            if config.get('implementation') == implementation_id():
                client.request('/api/disconnect', {}, timeout=2)
                return endpoint
            if any(run['active'] for run in state['runs']):
                client.request('/api/disconnect', {}, timeout=2)
                raise RuntimeError('A procedure-service update is pending. Stop its live procedures before starting the updated IDE.')
            client.request('/api/shutdown', {}, timeout=3)
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                try:
                    client.request('/api/state', timeout=.5)
                except Exception:
                    break
                time.sleep(.1)
            # The server releases its lifetime lock on process exit.
            time.sleep(.3)
        with open(directory / 'service.log', 'ab') as log:
            subprocess.Popen([str(console_interpreter(sys.executable)), '-I', '-B', '-u', '-X', 'utf8', '-m',
                'openbexi_runtime.procedure_service', '--project', str(Path(project).resolve()), '--directory', str(directory)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=clean_environment(),
                start_new_session=os.name != 'nt', creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                client = Client.connect(endpoint, 'Service discovery')
                client.request('/api/state', timeout=1)
                client.request('/api/disconnect', {}, timeout=1)
                return endpoint
            except (OSError, RuntimeError, ValueError, KeyError):
                time.sleep(.1)
        raise RuntimeError('Procedure service startup failed. See ' + str(directory / 'service.log'))
    finally:
        if os.name == 'nt':
            lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        lock.close()


if __name__ == '__main__':
    # A short-lived bootstrap prevents an IDE's process handler from owning
    # the long-lived service as a descendant of its DAP bridge.
    print(ensure_service(sys.argv[1]))
