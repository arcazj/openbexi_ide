"""Mutual TLS over real sockets; no mocked certificate or role acceptance."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import threading

import pytest

from openbexi_runtime.cli import request
from openbexi_runtime.session import Session
from openbexi_runtime.session_http import SessionServer
from openbexi_runtime.session_identity import CertificateIdentities, server_context
from test_durable_sessions import project
from test_sessions import wait_for


@pytest.fixture(scope='module')
def certificates(tmp_path_factory):
    root = tmp_path_factory.mktemp('tls-certificates')
    executable = shutil.which('openssl')
    if executable is None and os.name == 'nt':
        candidate = Path('C:/Program Files/Git/usr/bin/openssl.exe')
        if candidate.is_file():
            executable = str(candidate)
    if executable is None:
        pytest.fail('TLS acceptance requires OpenSSL to generate temporary test certificates')
    def run(*args):
        result = subprocess.run([executable, *args], cwd=root, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr.decode(errors='replace')
    run('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'ca.key', '-out', 'ca.pem',
        '-days', '2', '-subj', '/CN=OpenBEXI Test CA', '-addext', 'basicConstraints=critical,CA:TRUE',
        '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
    for name in ('server', 'alice', 'bob', 'monitor', 'unregistered'):
        run('req', '-newkey', 'rsa:2048', '-nodes', '-keyout', name + '.key', '-out', name + '.csr',
            '-subj', '/CN=' + name)
        extensions = ('subjectAltName=DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\n'
                      if name == 'server' else 'extendedKeyUsage=clientAuth\n')
        (root / 'extensions.cnf').write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n' + extensions)
        run('x509', '-req', '-in', name + '.csr', '-CA', 'ca.pem', '-CAkey', 'ca.key', '-CAcreateserial',
            '-out', name + '.pem', '-days', '2', '-extfile', 'extensions.cnf')
    return root


def fingerprint(root, name):
    der = ssl.PEM_cert_to_DER_cert((root / (name + '.pem')).read_text())
    return hashlib.sha256(der).hexdigest()


def tls(root, name):
    return {'ca': str(root / 'ca.pem'), 'certificate': str(root / (name + '.pem')), 'key': str(root / (name + '.key'))}


@contextmanager
def secure_service(project, state, root):
    path = state.parent / 'identities.json'
    rows = {fingerprint(root, name): {'name': name, 'role': 'monitor' if name == 'monitor' else 'developer'}
            for name in ('alice', 'bob', 'monitor')}
    path.write_text(json.dumps({'schema': 1, 'identities': rows}))
    session = Session(project, state_directory=state)
    worker = SessionServer(('127.0.0.1', 0), session, worker_only=True)
    server = SessionServer(('127.0.0.1', 0), session, identities=CertificateIdentities(path),
                           tls_context=server_context(root / 'server.pem', root / 'server.key', root / 'ca.pem'))
    threads = [threading.Thread(target=s.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True) for s in (worker, server)]
    for thread in threads:
        thread.start()
    try:
        yield session, f'https://localhost:{server.server_port}', path, rows
    finally:
        session.close()
        for item in (worker, server):
            item.shutdown()
            item.server_close()
        for thread in threads:
            thread.join(timeout=5)


def test_real_tls_identity_binding_monitor_revocation_and_worker_boundary(project, tmp_path, certificates):
    with secure_service(project, tmp_path / 'authority', certificates) as (session, url, path, rows):
        credentials = tls(certificates, 'alice')
        # A self-chosen display name and invitation cannot select remote authority.
        alice = request(url, '/connect', {'name': 'administrator', 'invite': session.monitor_invite}, tls=credentials)
        member = session.authenticate(alice['token'])
        assert member['name'] == 'alice' and member['role'] == 'developer'
        epoch = request(url, '/claim', {}, alice['token'], tls=credentials)['epoch']
        monitor = request(url, '/connect', {}, tls=tls(certificates, 'monitor'))
        assert request(url, '/session', token=monitor['token'], tls=tls(certificates, 'monitor'))['controller']['name'] == 'alice'
        with pytest.raises(ValueError, match='read-only'):
            request(url, '/claim', {}, monitor['token'], tls=tls(certificates, 'monitor'))
        with pytest.raises(ValueError, match='identity differs'):
            request(url, '/session', token=alice['token'], tls=tls(certificates, 'bob'))
        with pytest.raises(ValueError, match='revoked or unregistered'):
            request(url, '/connect', {}, tls=tls(certificates, 'unregistered'))
        with pytest.raises((OSError, ValueError)):
            request(url, '/connect', {}, tls={'ca': str(certificates / 'ca.pem')})
        with pytest.raises((OSError, ValueError)):
            request(url, '/connect', {})  # Untrusted server CA and no client identity.
        with pytest.raises(ValueError, match='private loopback'):
            request(url, '/worker/checkpoint', {}, tls=credentials)
        with pytest.raises(ValueError, match='Worker endpoint'):
            request(session.worker_url, '/connect', {'name': 'local bypass', 'invite': session.developer_invite})
        with pytest.raises(ValueError, match='Worker endpoint'):
            request(session.worker_url, '/session', token=alice['token'])
        identifier = request(url, '/run', {'epoch': epoch, 'script': 'wait.py'}, alice['token'], tls=credentials)['id']
        wait_for(lambda: session.procedures[identifier].status == 'RUNNING')
        del rows[fingerprint(certificates, 'alice')]
        path.write_text(json.dumps({'schema': 1, 'identities': rows}))
        # Idle certificate revocation also fences control; no next request is required.
        wait_for(lambda: session.controller is None and session.procedures[identifier].status == 'PAUSED')
        assert alice['token'] not in session.clients
        with pytest.raises(ValueError, match='revoked'):
            request(url, '/claim', {}, alice['token'], tls=credentials)


def test_cli_connect_and_status_use_saved_certificate_paths(project, tmp_path, certificates):
    import sys
    root = Path(__file__).resolve().parents[1]
    with secure_service(project, tmp_path / 'authority', certificates) as (_session, url, _path, _rows):
        connection = tmp_path / 'client.json'
        command = [sys.executable, '-I', str(root / 'run_cli.py'), '--connection', str(connection)]
        result = subprocess.run([*command, 'connect', '--url', url, '--user', 'untrusted label',
                                 '--tls-ca', str(certificates / 'ca.pem'), '--tls-cert', str(certificates / 'alice.pem'),
                                 '--tls-key', str(certificates / 'alice.key')], capture_output=True, timeout=20)
        assert result.returncode == 0, result.stderr
        result = subprocess.run([*command, 'status'], capture_output=True, timeout=20)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['clients'][0]['name'] == 'alice'


def test_qt_client_certificate_join_and_disconnect(app, project, tmp_path, certificates):
    import time
    from openbexi_ide.session_client import SessionClient
    with secure_service(project, tmp_path / 'authority', certificates) as (session, url, _path, _rows):
        info = tmp_path / 'connection.json'
        info.write_text(json.dumps({'url': url, 'tls': tls(certificates, 'monitor')}))
        client = SessionClient()
        errors = []
        client.error.connect(errors.append)
        assert client.join(user='Monitor', invite_file=info, role='monitor')
        deadline = time.monotonic() + 10
        while not client.healthy and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert client.healthy, errors
        assert not client.can_control and not client.can_claim
        client.disconnect()
        while client.active and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert not client.active and not session.clients
        client._thread.join(timeout=5)
