"""Own the test desktop/services and stop only their processes on container exit."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import ssl
import subprocess
import sys
import tempfile
import time

ROOT = Path('/workspace')
children = []
stopping = False


def run(command, **options):
    return subprocess.run(command, check=True, **options)


def start(name, command):
    logs = ROOT / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / (name + '.log')).open('ab', buffering=0) as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    children.append((name, process))
    return process


def wait_until(predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        failed = [(name, p.returncode) for name, p in children if p.poll() is not None]
        if failed:
            raise RuntimeError(f'Test service exited: {failed}; inspect /workspace/logs')
        if predicate():
            return
        time.sleep(0.1)
    raise RuntimeError('Test desktop startup timed out; inspect /workspace/logs')


def initialize():
    os.umask(0o077)
    (ROOT / 'connections').mkdir(parents=True, exist_ok=True)
    (ROOT / 'dss').mkdir(exist_ok=True)
    for name in ('demo', 'durable'):
        project = ROOT / 'projects' / name
        if project.exists():
            continue
        project.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree('/opt/openbexi/examples', project)
        (project / '.gitignore').write_text('__pycache__/\n*.pyc\n.openbexi/\n')
        if name == 'demo':
            (project / 'dss_demo.py').write_text(
                'from spell.lang import Display, GetTM, BuildTC, Send\n'
                'Display("DSS development test")\nDisplay(str(GetTM("TM1")))\n'
                'Send(BuildTC("CMD1"))\nDisplay("Binary DSS command complete")\n')
        run(['git', 'init', '-q', str(project)])
        run(['git', '-C', str(project), 'add', '.'])
        run(['git', '-C', str(project), '-c', 'user.name=OpenBEXI Test Fixture',
             '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false',
             'commit', '-qm', 'Initial Docker test examples'])
    target_certs = ROOT / 'certificates'
    if not target_certs.exists():
        # A terminated first start must not leave a partially initialized CA.
        certs = Path(tempfile.mkdtemp(prefix='certificates-preparing-', dir=ROOT))
        def openssl(*args):
            run(['openssl', *args], cwd=certs, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'ca.key', '-out', 'ca.pem',
                '-days', '365', '-subj', '/CN=OpenBEXI Local Test CA',
                '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
        identities = {}
        for name in ('server', 'alice', 'monitor'):
            openssl('req', '-newkey', 'rsa:2048', '-nodes', '-keyout', name + '.key', '-out', name + '.csr',
                    '-subj', '/CN=' + name)
            extension = ('subjectAltName=DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\n'
                         if name == 'server' else 'extendedKeyUsage=clientAuth\n')
            (certs / 'extensions.cnf').write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n' + extension)
            openssl('x509', '-req', '-in', name + '.csr', '-CA', 'ca.pem', '-CAkey', 'ca.key', '-CAcreateserial',
                    '-out', name + '.pem', '-days', '365', '-extfile', 'extensions.cnf')
            if name != 'server':
                fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert((certs / (name + '.pem')).read_text())).hexdigest()
                identities[fingerprint] = {'name': name, 'role': 'monitor' if name == 'monitor' else 'developer'}
        (certs / 'identities.json').write_text(json.dumps({'schema': 1, 'identities': identities}, indent=2))
        certs.rename(target_certs)
    certs = target_certs
    for name in ('alice', 'monitor'):
        info = {'url': 'https://localhost:9011',
                'tls': {'ca': str(certs / 'ca.pem'), 'certificate': str(certs / (name + '.pem')),
                        'key': str(certs / (name + '.key'))}}
        (ROOT / 'connections' / ('durable-' + name + '.json')).write_text(json.dumps(info, indent=2))


def shutdown(*_args):
    global stopping
    stopping = True


def desktop():
    initialize()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        start('display', ['Xvfb', ':0', '-screen', '0', '1600x1000x24', '-nolisten', 'tcp', '-ac', '-s', '0'])
        wait_until(lambda: Path('/tmp/.X11-unix/X0').exists())
        start('window-manager', ['openbox', '--config-file', '/opt/test-lab/openbox.xml'])
        start('vnc', ['x11vnc', '-display', ':0', '-rfbport', '5900', '-localhost', '-nopw', '-forever', '-shared', '-noxdamage'])
        start('browser', ['/usr/bin/websockify', '--web=/usr/share/novnc', '0.0.0.0:6080', '127.0.0.1:5900'])
        start('dss', [sys.executable, '-I', '-m', 'dss.local', '--port', '8085', '--database', str(ROOT / 'dss/dss.sqlite')])
        start('shared-session', [sys.executable, '-I', '-m', 'openbexi_runtime.cli', 'serve',
                                '--project', str(ROOT / 'projects/demo'), '--port', '9010', '--max-parallel', '2',
                                '--info', str(ROOT / 'connections/shared-server.json'), '--dss-url', 'http://127.0.0.1:8085'])
        certs = ROOT / 'certificates'
        start('durable-session', [sys.executable, '-I', '-m', 'openbexi_runtime.cli', 'serve',
                                 '--project', str(ROOT / 'projects/durable'), '--port', '9011',
                                 '--state-directory', str(ROOT / 'durable-state'), '--info', str(ROOT / 'connections/durable-server.json'),
                                 '--tls-cert', str(certs / 'server.pem'), '--tls-key', str(certs / 'server.key'),
                                 '--client-ca', str(certs / 'ca.pem'), '--identities', str(certs / 'identities.json')])
        start('desktop', [sys.executable, '-I', '/opt/test-lab/desktop.py'])
        wait_until(lambda: subprocess.run([sys.executable, '-I', '/opt/test-lab/health.py'],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0)
        print('OpenBEXI test desktop ready: http://localhost:6080/vnc.html?autoconnect=1&resize=scale', flush=True)
        print('Use the desktop launch buttons for local/shared/monitor/durable IDEs and a terminal.', flush=True)
        while not stopping:
            wait_until(lambda: True)
            time.sleep(0.5)
    finally:
        for _name, process in reversed(children):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
        deadline = time.monotonic() + 12
        for _name, process in reversed(children):
            try:
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)


def tests():
    evidence = Path('/evidence') / (time.strftime('%Y%m%d-%H%M%S') + '-' + str(time.time_ns() % 1000000))
    evidence.mkdir(parents=True, exist_ok=False)
    environment = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}
    result = subprocess.run([sys.executable, '-m', 'pytest', 'tests', '-q', '-W', 'error',
                             '--junitxml=' + str(evidence / 'tests.xml')], cwd='/opt/openbexi', env=environment)
    reference = Path('/opt/openbexi/.qualification/desktop-runtime')
    if reference.is_dir():
        shutil.copytree(reference, evidence / 'python-reference')
    if result.returncode == 0:
        # The source suite uses offscreen Qt. Installed desktop acceptance also
        # exercises the actual X11 platform used by the browser desktop.
        with (evidence / 'display.log').open('wb') as log:
            display = subprocess.Popen(['Xvfb', ':0', '-screen', '0', '1600x1000x24',
                                        '-nolisten', 'tcp', '-ac'], stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 10
            while not Path('/tmp/.X11-unix/X0').exists():
                if display.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Qualification display failed to start')
                time.sleep(0.1)
            environment['QT_QPA_PLATFORM'] = 'xcb'
            for script in ('qualify_installed.py', 'qualify_desktop_installed.py'):
                result = subprocess.run([sys.executable, '-I', '/opt/openbexi/scripts/' + script,
                                         '--output', str(evidence)], env=environment)
                if result.returncode:
                    break
        finally:
            display.terminate()
            display.wait(timeout=5)
    print('Evidence retained in ' + str(evidence), flush=True)
    return result.returncode


if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) > 1 else 'desktop'
    if action == 'desktop':
        desktop()
    elif action == 'test':
        raise SystemExit(tests())
    else:
        raise SystemExit('Choose desktop or test')
