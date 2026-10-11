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

    def __init__(self, address, session):
        if address[0] not in {'127.0.0.1', 'localhost', '::1'}:
            raise ValueError('v0.1 sessions require a loopback address; use an authenticated tunnel for remote developers')
        self.session = session
        super().__init__(address, Handler)
        session.worker_url = f'http://127.0.0.1:{self.server_port}'


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError, TimeoutError):
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
        header = self.headers.get('Authorization', '')
        if not header.startswith('Bearer '):
            raise SessionError('Bearer credential required', 401)
        return self.server.session.authenticate(header[7:])

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
            route = urlsplit(self.path)
            if route.path == '/healthz':
                self.reply(200, {'status': 'ready', 'session': self.server.session.id})
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
                result = session.join(body['name'], body['invite'])
            elif route.path == '/worker/checkpoint':
                result = session.checkpoint(body)
            else:
                actor, epoch = self.actor(), body.get('epoch')
                if route.path == '/claim':
                    result = session.claim(actor)
                elif route.path == '/renew':
                    result = session.renew(actor, epoch)
                elif route.path == '/release':
                    result = session.release(actor, epoch)
                elif route.path == '/run':
                    result = session.submit(actor, epoch, body['script'], arguments=body.get('arguments', []), language=body.get('language', 'python'))
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
