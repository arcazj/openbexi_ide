"""Pinned mTLS v0.8 desktop client. No credentials are written to source or state.

This is separate from the v0.7 session protocol. No automatic retry, controller
claim acceptance or capability/epoch repair occurs after an ambiguous response.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
from pathlib import Path
import re
import socket
import ssl
import threading
from urllib.parse import urlsplit

LIMIT = 65536
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


class SpellServerError(RuntimeError):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(f"SPELL server: {status} {code}")


def identifier(value):
    if not isinstance(value, str) or IDENTIFIER.fullmatch(value) is None:
        raise ValueError("Invalid server identifier")
    return value


def decode(raw):
    if len(raw) > LIMIT:
        raise SpellServerError(503, "response_too_large")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate field")
            result[key] = value
        return result

    def reject(_):
        raise ValueError("Non-finite JSON")

    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)
        pending = [(result, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > 16:
                raise ValueError("JSON nesting limit")
            if isinstance(item, (list, dict)):
                pending.extend(
                    (v, depth + 1)
                    for v in (item.values() if isinstance(item, dict) else item)
                )
        return result
    except (ValueError, UnicodeError, RecursionError) as error:
        raise SpellServerError(503, "invalid_response") from error


class SpellServerClient:
    """One configured endpoint and one certificate identity; thread-safe I/O.

    The server is authoritative. A client can control several executions with
    independent proofs; no session-wide ownership or automatic epoch restamp.
    """

    def __init__(self, *, url, fingerprint, ca, certificate, key):
        target = urlsplit(url)
        if (
            target.scheme != "https"
            or not target.hostname
            or target.username
            or target.password
            or target.path not in ("", "/")
            or target.query
            or target.fragment
        ):
            raise ValueError("Use an HTTPS gateway origin")
        if not isinstance(fingerprint, str) or not re.fullmatch(
            r"[0-9a-f]{64}", fingerprint
        ):
            raise ValueError("Use the gateway certificate SHA-256")
        self.host, self.port, self.fingerprint = (
            target.hostname,
            target.port or 443,
            fingerprint,
        )
        self.tls = ssl.create_default_context(cafile=str(ca))
        self.tls.minimum_version = ssl.TLSVersion.TLSv1_3
        self.tls.load_cert_chain(str(certificate), str(key))
        self._lock = threading.RLock()
        self._controllers = {}

    @classmethod
    def from_config(cls, path):
        path = Path(path).resolve()
        config = decode(path.read_bytes())
        if type(config) is not dict or set(config) != {
            "url",
            "fingerprint",
            "ca",
            "certificate",
            "key",
        }:
            raise ValueError("Invalid SPELL client configuration")
        for name in ("ca", "certificate", "key"):
            config[name] = str((path.parent / config[name]).resolve())
        return cls(**config)

    def request(self, method, path, body=None, *, key=None):
        if method not in ("GET", "POST") or not re.fullmatch(
            r"/v1/(?:health|contexts(?:/[A-Za-z0-9_.:-]+/(?:health|snapshot|blackboard|procedures|executions|authority))?)",
            path,
        ):
            raise ValueError("Unconfigured server route")
        raw = (
            None
            if body is None
            else json.dumps(body, allow_nan=False, separators=(",", ":")).encode()
        )
        if raw is not None and len(raw) > LIMIT:
            raise ValueError("Request exceeds its bound")
        headers = {} if raw is None else {"Content-Type": "application/json"}
        if key is not None:
            headers["Idempotency-Key"] = identifier(key)
        with self._lock:
            connection = http.client.HTTPSConnection(
                self.host, self.port, context=self.tls, timeout=2
            )
            watchdog = None
            try:
                connection.connect()
                wire = connection.sock

                def expire():
                    try:
                        wire.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

                watchdog = threading.Timer(5, expire)
                watchdog.daemon = True
                watchdog.start()
                peer = hashlib.sha256(wire.getpeercert(binary_form=True)).hexdigest()
                if peer != self.fingerprint:
                    raise SpellServerError(503, "gateway_identity_unavailable")
                connection.request(method, path, raw, headers)
                response = connection.getresponse()
                result = decode(response.read(LIMIT + 1))
                if response.status != 200:
                    # Never expose server-controlled errors, paths or secrets.
                    raise SpellServerError(response.status, "request_denied")
                if (
                    type(result) is not dict
                    or result.get("schema") != "openbexi.listener/1"
                ):
                    raise SpellServerError(503, "invalid_protocol")
                return result
            except (OSError, http.client.HTTPException) as error:
                raise SpellServerError(503, "gateway_unavailable") from error
            finally:
                if watchdog:
                    watchdog.cancel()
                connection.close()

    def contexts(self):
        return self.request("GET", "/v1/contexts")["contexts"]

    def read(self, context, resource):
        identifier(context)
        if resource not in (
            "health",
            "snapshot",
            "blackboard",
            "procedures",
            "executions",
        ):
            raise ValueError("Unknown resource")
        return self.request("GET", f"/v1/contexts/{context}/{resource}")["result"]

    def authority(self, context, method, payload, *, key):
        identifier(context)
        if method not in (
            "session.open",
            "session.close",
            "execution.reserve",
            "execution.rebind",
            "execution.claim",
            "execution.decide",
            "execution.cancel",
        ):
            raise ValueError("Unknown authority operation")
        return self.request(
            "POST",
            f"/v1/contexts/{context}/authority",
            {"method": method, "payload": payload},
            key=key,
        )["result"]

    def remember_controller(self, context, result):
        """Store only an explicitly delivered proof; never reconstruct one from a list."""
        if "capability" not in result:
            return False
        proof = {
            "execution_id": result["id"],
            "connection_id": result["connection_id"],
            "expected_epoch": result["epoch"],
            "connection_generation": result["connection_generation"],
            "capability": result["capability"],
        }
        with self._lock:
            self._controllers[(identifier(context), result["id"])] = proof
        return True

    def has_controller(self, context, execution):
        with self._lock:
            return (context, execution) in self._controllers

    def decide(self, context, execution, claim, decision, *, key):
        if decision not in ("accept", "reject"):
            raise ValueError("Explicit accept or reject required")
        with self._lock:
            proof = dict(self._controllers[(context, execution)])
            result = self.authority(
                context,
                "execution.decide",
                {**proof, "claim_id": claim, "decision": decision},
                key=key,
            )
            if result.get("state") in ("ACCEPTED", "BLOCKED"):
                self._controllers.pop((context, execution), None)
            return result

    def forget(self):
        with self._lock:
            self._controllers.clear()


def main():
    parser = argparse.ArgumentParser(
        description="Read the authenticated SPELL v0.8 server"
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--context")
    parser.add_argument(
        "--resource", choices=("health", "procedures", "executions"), default="health"
    )
    args = parser.parse_args()
    client = SpellServerClient.from_config(args.config)
    result = (
        client.read(args.context, args.resource) if args.context else client.contexts()
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
