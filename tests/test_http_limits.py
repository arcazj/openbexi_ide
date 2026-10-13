"""Real slow sockets exhaust a bounded server, then return capacity."""
from http.server import BaseHTTPRequestHandler
import socket
import threading
import time

import pytest

from openbexi_runtime.bounded_http import BoundedHTTPServer


def test_slow_clients_are_bounded_and_disconnection_restores_capacity():
    entered = threading.Condition()
    count = 0

    class Handler(BaseHTTPRequestHandler):
        def handle(self):
            try:
                super().handle()
            except ConnectionError:
                pass

        def setup(self):
            nonlocal count
            super().setup()
            self.connection.settimeout(2)
            with entered:
                count += 1
                entered.notify_all()

        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'ok')

        def log_message(self, *_):
            pass

    server = BoundedHTTPServer(('127.0.0.1', 0), Handler, max_handlers=2)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sockets = []
    try:
        for _ in range(2):
            client = socket.create_connection(server.server_address, timeout=1)
            sockets.append(client)
            client.sendall(b'GET / HTTP/1.0\r\nX-Slow: ')
        with entered:
            assert entered.wait_for(lambda: count == 2, timeout=1)
        rejected = socket.create_connection(server.server_address, timeout=1)
        with rejected:
            try:
                assert rejected.recv(1) == b''
            except ConnectionError:
                pass
        assert count == 2
        for client in sockets:
            client.close()
        sockets.clear()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with socket.create_connection(server.server_address, timeout=1) as client:
                try:
                    client.sendall(b'GET / HTTP/1.0\r\n\r\n')
                    if b'200 OK' in client.recv(1024):
                        break
                except ConnectionError:
                    pass
            time.sleep(.01)
        else:
            pytest.fail('Disconnected clients did not return HTTP capacity')
        assert count >= 3
    finally:
        for client in sockets:
            client.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize('limit', [0, 257, -1, True, 1.5])
def test_invalid_handler_limits_fail_before_binding(limit):
    with pytest.raises(ValueError, match='handler limit'):
        BoundedHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler, max_handlers=limit)


def test_deep_json_is_rejected_and_real_session_remains_healthy(tmp_path):
    import http.client
    import json
    from urllib.parse import urlsplit
    from test_sessions import serving
    with serving(tmp_path) as (session, url):
        address = urlsplit(url)
        connection = http.client.HTTPConnection(address.hostname, address.port, timeout=5)
        try:
            body = '{"nested":' + '['*2000 + '0' + ']'*2000 + '}'
            connection.request('POST', '/connect', body, {'Content-Type':'application/json'})
            response = connection.getresponse()
            assert response.status == 400 and 'nesting' in json.loads(response.read())['error']
            connection.request('GET', '/healthz')
            response = connection.getresponse()
            assert response.status == 200 and json.loads(response.read())['status'] == 'ready'
        finally:
            connection.close()
