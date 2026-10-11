"""Explicit certificate identities; roles are provisioned by the service owner."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import ssl


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate identity field')
        result[key] = value
    return result


class CertificateIdentities:
    def __init__(self, path):
        self.path = Path(path)
        self.read()

    def read(self):
        if self.path.stat().st_size > 65536:
            raise ValueError('Identity configuration exceeds its bound')
        data = json.loads(self.path.read_text(encoding='utf-8'), object_pairs_hook=unique_object)
        if type(data) is not dict or set(data) != {'schema', 'identities'} or data['schema'] != 1:
            raise ValueError('Invalid certificate identity configuration')
        identities = data['identities']
        if type(identities) is not dict or len(identities) > 256:
            raise ValueError('Invalid certificate identity inventory')
        for fingerprint, row in identities.items():
            if (re.fullmatch('[0-9a-f]{64}', fingerprint) is None or type(row) is not dict
                    or set(row) != {'name', 'role'} or row['role'] not in {'developer', 'monitor'}
                    or not isinstance(row['name'], str) or not 1 <= len(row['name']) <= 64
                    or not row['name'].strip() or any(ord(c) < 32 for c in row['name'])):
                raise ValueError('Invalid certificate identity or role')
        return identities

    def principal(self, der):
        fingerprint = hashlib.sha256(der).hexdigest()
        row = self.read().get(fingerprint)
        return None if row is None else {**row, 'subject': fingerprint}


def server_context(certificate, key, client_ca):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate, key)
    context.load_verify_locations(cafile=client_ca)
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def client_context(*, ca=None, certificate=None, key=None):
    if bool(certificate) != bool(key):
        raise ValueError('Client certificate and key must be supplied together')
    context = ssl.create_default_context(cafile=ca)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if certificate:
        context.load_cert_chain(certificate, key)
    return context
