"""The browser procedure service preserves the existing remote identity policy."""
import json
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from openbexi_runtime.procedure_service import ProcedureService, ProcedureServer
from openbexi_runtime.session_identity import CertificateIdentities, server_context, client_context
from test_session_tls import certificates, fingerprint


def test_remote_bind_requires_authenticated_tls(tmp_path):
    service = ProcedureService(tmp_path, tmp_path / 'state')
    try:
        with pytest.raises(ValueError, match='mutual TLS'):
            ProcedureServer(('0.0.0.0', 0), service)
    finally:
        service.records.close()


def test_real_browser_service_tls_roles_identity_binding_and_revocation(tmp_path, certificates):
    identities = tmp_path / 'identities.json'
    rows = {fingerprint(certificates, name): {'name': name, 'role': role}
            for name, role in (('alice', 'developer'), ('monitor', 'monitor'))}
    identities.write_text(json.dumps({'schema': 1, 'identities': rows}))
    service = ProcedureService(tmp_path, tmp_path / 'state')
    server = ProcedureServer(('127.0.0.1', 0), service, identities=CertificateIdentities(identities),
        tls_context=server_context(certificates / 'server.pem', certificates / 'server.key', certificates / 'ca.pem'))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    def request(name, path, token, data=None):
        context = client_context(ca=certificates / 'ca.pem', certificate=certificates / (name + '.pem'), key=certificates / (name + '.key'))
        query = Request('https://' + server.authority + path, data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
        with urlopen(query, context=context, timeout=5) as response:
            return json.load(response)
    try:
        alice = request('alice', '/api/connect', service.operator_key, {'name': 'Spoofed name'})
        monitor = request('monitor', '/api/connect', service.operator_key, {'name': 'Administrator'})
        assert alice['role'] == 'operator' and monitor['role'] == 'monitor'
        assert service.clients[alice['client']]['name'] == 'alice'
        with pytest.raises(HTTPError) as denied:
            request('monitor', '/api/state', alice['client'])
        assert denied.value.code == 403
        with pytest.raises(HTTPError) as denied:
            request('monitor', '/api/run', monitor['client'], {'script': 'never.py'})
        assert denied.value.code == 403
        rows.pop(fingerprint(certificates, 'alice')); identities.write_text(json.dumps({'schema': 1, 'identities': rows}))
        with pytest.raises(HTTPError) as denied:
            request('alice', '/api/state', alice['client'])
        assert denied.value.code == 403
    finally:
        server.shutdown(); server.server_close(); thread.join(); service.records.close()
