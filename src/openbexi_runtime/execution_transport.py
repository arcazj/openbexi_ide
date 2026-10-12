"""Private stdio control channel inside an isolated Execution container.

User stdout/stderr (including native writes) are forwarded from separate OS pipes.
Neither controller credentials nor a host network endpoint enter the container.
"""
from __future__ import annotations

import json
import atexit
import os
import queue
import sys
import threading
import time

infrastructure = set()


def start():
    wire_in = os.fdopen(os.dup(0), 'rb', buffering=0)
    wire_out = os.fdopen(os.dup(1), 'wb', buffering=0)
    config = json.loads(wire_in.readline(262144))
    write_lock, report_lock = threading.Lock(), threading.Lock()
    replies = queue.Queue(maxsize=1)
    inputs = queue.Queue(maxsize=8)
    last_response = [time.monotonic()]

    def emit(value):
        raw = (json.dumps(value, ensure_ascii=True, allow_nan=False) + '\n').encode()
        with write_lock:
            wire_out.write(raw)

    def spawn(function, name='execution-control'):
        ready = threading.Event()
        def run():
            infrastructure.add(threading.get_ident())
            ready.set()
            try:
                function()
            except BaseException:
                os._exit(75)
            finally:
                infrastructure.discard(threading.get_ident())
        threading.Thread(target=run, daemon=True, name=name).start()
        ready.wait()

    def forward(read_fd, name):
        import codecs
        decoder = codecs.getincrementaldecoder('utf-8')('replace')
        while raw := os.read(read_fd, 4096):
            emit({'type': 'output', 'stream': name, 'text': decoder.decode(raw)})
        tail = decoder.decode(b'', final=True)
        if tail:
            emit({'type': 'output', 'stream': name, 'text': tail})
        os.close(read_fd)

    for fd, name in ((1, 'stdout'), (2, 'stderr')):
        reader, writer = os.pipe()
        os.dup2(writer, fd)
        os.close(writer)
        spawn(lambda reader=reader, name=name: forward(reader, name), 'execution-output-' + name)
    user_input, input_writer = os.pipe()
    os.dup2(user_input, 0)
    os.close(user_input)

    def write_inputs():
        while True:
            text = inputs.get()
            if text is None:
                os.close(input_writer)
                return
            raw = text.encode('utf-8')
            while raw:
                raw = raw[os.write(input_writer, raw):]

    def receive():
        while True:
            raw = wire_in.readline(262144)
            if not raw or not raw.endswith(b'\n'):
                os._exit(75)
            value = json.loads(raw)
            last_response[0] = time.monotonic()
            if value['type'] == 'reply':
                replies.put_nowait(value['action'])
            elif value['type'] == 'input':
                inputs.put_nowait(value['text'])
            elif value['type'] != 'heartbeat':
                os._exit(75)

    def watchdog():
        while True:
            time.sleep(0.2)
            if time.monotonic() - last_response[0] > 4:
                os._exit(75)

    spawn(write_inputs)
    spawn(receive)
    spawn(watchdog)

    def report(body):
        with report_lock:
            emit({'type': 'checkpoint', 'body': body})
            try:
                return replies.get(timeout=4)
            except queue.Empty:
                os._exit(75)

    return config, report


def main():
    config, report = start()
    os.environ['OPENBEXI_SESSION_WORKER'] = json.dumps(config)
    from openbexi_runtime import session_worker
    code = 0

    def finish():
        # Registered before the procedure, so its own atexit handlers run first.
        # Native extensions may also have buffered C stdout/stderr.
        import ctypes
        ctypes.CDLL(None).fflush(None)
        sys.stdout.flush()
        sys.stderr.flush()
        os.close(1)
        os.close(2)
        pumps = [t for t in threading.enumerate() if t.name.startswith('execution-output-')]
        for thread in pumps:
            thread.join(timeout=3)
        os._exit(75 if any(t.is_alive() for t in pumps) else code)

    atexit.register(finish)
    try:
        session_worker.main(pipe_report=report, infrastructure=infrastructure)
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1 if error.code else 0
        if error.code is not None and not isinstance(error.code, int):
            print(error.code, file=sys.stderr)
    except BaseException:
        import traceback
        traceback.print_exc()
        code = 1
    raise SystemExit(code)


if __name__ == '__main__':
    main()
