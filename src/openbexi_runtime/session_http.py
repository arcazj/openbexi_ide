"""Authenticated loopback transport for shared local-development sessions."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .session import SessionError


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field')
        result[key] = value
    return result


class SessionServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, address, session, *, tls_context=None, identities=None, worker_only=False):
        if bool(tls_context) != bool(identities):
            raise ValueError('TLS requires explicit certificate identities')
        if address[0] not in {'127.0.0.1', 'localhost'} and not tls_context:
            raise ValueError('Shared Development sessions require a loopback address; use an authenticated tunnel for remote developers')
        if worker_only and tls_context:
            raise ValueError('Worker endpoint must be a separate loopback listener')
        if tls_context and session.store is None:
            raise ValueError('Remote identity requires a durable session directory')
        self.identities, self.worker_only = identities, worker_only
        self.session = session
        super().__init__(address, Handler)
        if tls_context:
            self.socket = tls_context.wrap_socket(self.socket, server_side=True, do_handshake_on_connect=False)
        else:
            session.worker_url = f'http://127.0.0.1:{self.server_port}'

    def service_actions(self):
        if self.identities:
            try:
                identities = self.identities.read()
            except (ValueError, OSError):
                identities = {}
            with self.session.lock:
                for member in list(self.session.clients.values()):
                    subject = member.get('subject')
                    if subject and identities.get(subject) != {'name': member['name'], 'role': member['role']}:
                        self.session.revoke_subject(subject)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError):
            # Worker cleanup and a disconnected monitor can close a socket
            # between accept and request parsing; this is an ordinary lifecycle.
            pass

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_args):
        pass

    def reply(self, status, body):
        raw = json.dumps(body, ensure_ascii=True, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(raw)

    def actor(self):
        principal = self.principal()
        header = self.headers.get('Authorization', '')
        if not header.startswith('Bearer '):
            raise SessionError('Bearer credential required', 401)
        actor = self.server.session.authenticate(header[7:])
        if principal is not None and (actor.get('subject') != principal['subject']
                                      or actor['role'] != principal['role'] or actor['name'] != principal['name']):
            raise SessionError('Connection certificate identity differs', 403)
        return actor

    def principal(self):
        if self.server.worker_only:
            raise SessionError('Worker endpoint does not accept client commands', 403)
        if self.server.identities is None:
            return None
        der = self.connection.getpeercert(binary_form=True)
        try:
            principal = self.server.identities.principal(der) if der else None
        except (ValueError, OSError):
            principal = None
        if principal is None:
            raise SessionError('Certificate identity is revoked or unregistered', 403)
        return principal

    def body(self):
        if self.headers.get('Origin') is not None:
            raise SessionError('Browser-origin mutations are not accepted', 403)
        lengths = self.headers.get_all('Content-Length', [])
        if self.headers.get('Transfer-Encoding') or len(lengths) != 1 or not lengths[0].isdigit():
            raise SessionError('One Content-Length is required', 400)
        length = int(lengths[0])
        if not 2 <= length <= 131072:
            raise SessionError('Request exceeds its bound', 413)
        if self.headers.get('Content-Type') != 'application/json':
            raise SessionError('application/json required', 415)
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise SessionError('Truncated request', 400)
        body = json.loads(raw, object_pairs_hook=_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite value')))
        if type(body) is not dict:
            raise SessionError('JSON object required', 400)
        return body

    def do_GET(self):
        try:
            self.principal()
            route = urlsplit(self.path)
            if route.path == '/healthz':
                available = not self.server.session.closed.is_set()
                self.reply(200 if available else 503,
                           {'status': 'ready' if available else 'fenced', 'session': self.server.session.id})
                return
            self.actor()
            if route.path != '/session':
                raise SessionError('Route not found', 404)
            fields = parse_qs(route.query, strict_parsing=True, max_num_fields=1)
            if set(fields) - {'after'} or any(len(v) != 1 for v in fields.values()):
                raise ValueError('Invalid cursor')
            self.reply(200, self.server.session.snapshot(int(fields.get('after', ['0'])[0])))
        except SessionError as error:
            self.reply(error.status, {'error': str(error)})
        except (ValueError, TypeError, KeyError):
            self.reply(400, {'error': 'Invalid request'})

    def do_POST(self):
        try:
            body, route, session = self.body(), urlsplit(self.path), self.server.session
            if route.query:
                raise SessionError('Query unsupported', 400)
            if route.path == '/connect':
                result = session.join(body.get('name', 'certificate'), body.get('invite'), principal=self.principal())
            elif route.path == '/worker/checkpoint':
                if self.server.identities is not None:
                    raise SessionError('Worker checkpoint requires the private loopback endpoint', 403)
                result = session.checkpoint(body)
            else:
                actor, epoch = self.actor(), body.get('epoch')
                if route.path == '/claim':
                    result = session.claim(actor)
                elif route.path == '/disconnect':
                    result = session.leave(actor)
                elif route.path == '/configure':
                    result = session.configure(actor, epoch, body['max_parallel'])
                elif route.path == '/renew':
                    result = session.renew(actor, epoch)
                elif route.path == '/release':
                    result = session.release(actor, epoch)
                elif route.path == '/handoff':
                    result = session.handoff(actor, epoch, body['target'])
                elif route.path == '/run':
                    result = session.submit(actor, epoch, body['script'], arguments=body.get('arguments', []),
                        language=body.get('language', 'python'), debug=body.get('debug', False),
                        stop_on_entry=body.get('stop_on_entry', True), breakpoints=body.get('breakpoints'))
                elif route.path == '/debug':
                    result = session.debug_request(actor, epoch, body['procedure'], body['command'],
                        body.get('arguments'), body.get('revision'))
                elif route.path == '/source':
                    result = session.debug_source(body['procedure'], body['path'])
                elif route.path in {'/pause', '/resume', '/stop'}:
                    result = session.change(actor, epoch, route.path[1:], body['procedure'])
                elif route.path == '/input':
                    result = session.input(actor, epoch, body['procedure'], body.get('text'))
                else:
                    raise SessionError('Route not found', 404)
            self.reply(200, result)
        except SessionError as error:
            self.reply(error.status, {'error': str(error)})
        except (ValueError, TypeError, KeyError, OSError) as error:
            self.reply(400, {'error': str(error)})
