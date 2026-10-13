"""Bound request threads before accepting work from slow or excess clients."""
from http.server import ThreadingHTTPServer
import threading


class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 16

    def __init__(self, *args, max_handlers=32, **kwargs):
        if type(max_handlers) is not int or not 1 <= max_handlers <= 256:
            raise ValueError('HTTP handler limit must be an integer from 1 to 256')
        self.max_handlers = max_handlers
        self._handler_slots = threading.BoundedSemaphore(max_handlers)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._handler_slots.acquire(blocking=False):
            # Closing works for both plain sockets and TLS sockets which have
            # not performed their handshake. Do not create another handler.
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._handler_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._handler_slots.release()
