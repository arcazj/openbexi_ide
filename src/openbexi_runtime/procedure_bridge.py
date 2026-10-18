"""DAP client connection to a server-owned procedure, for Qt and JetBrains."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib.parse import urlencode

from .dap import MessageReader, encode_message
from .launch import console_interpreter
from .procedure_client import Client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--endpoint', type=Path)
    parser.add_argument('--interpreter', default=sys.executable)
    parser.add_argument('--image')
    args = parser.parse_args()
    endpoint = args.endpoint
    if endpoint is None:
        bootstrap = subprocess.run([str(console_interpreter(sys.executable)), '-I', '-m',
            'openbexi_runtime.procedure_client', str(args.project)], capture_output=True, text=True, encoding='utf-8', timeout=20)
        if bootstrap.returncode:
            raise RuntimeError(bootstrap.stderr.strip())
        endpoint = Path(bootstrap.stdout.strip())
    client = Client.connect(endpoint, 'IDE')
    run_id = None; sequence = 0; output_lock = threading.Lock(); stop = threading.Event()

    def heartbeat():
        while not stop.wait(5):
            try:
                client.request('/api/heartbeat', timeout=3)
            except Exception:
                pass  # Event polling reports connectivity to the host.
    threading.Thread(target=heartbeat, daemon=True).start()

    def emit(message):
        nonlocal sequence
        with output_lock:
            sequence += 1; message = dict(message, seq=sequence)
            sys.stdout.buffer.write(encode_message(message)); sys.stdout.buffer.flush()

    def events():
        cursor = 0; terminal = None; revision = -1
        while not stop.is_set():
            try:
                entries = client.request('/api/events?' + urlencode(dict(id=run_id, after=cursor)))
                for entry in entries:
                    cursor = entry['sequence']; event = entry['event']
                    if event.get('kind') != 'dap':
                        continue
                    message = event['message']
                    if message.get('event') == 'terminated':
                        terminal = message
                    else:
                        emit(message)
                if len(entries) < 500:
                    state = client.request('/api/state')
                    run = next(item for item in state['runs'] if item['id'] == run_id)
                    if state['revision'] != revision:
                        revision = state['revision']
                        emit(dict(type='event', event='openbexi/workspace', body=dict(run,
                            revision=state['revision'], service_instance=state['instance'])))
                    if not run['active']:
                        if not terminal:
                            emit(dict(type='event', event='exited', body={'exitCode': run['exit_code'] if run['exit_code'] is not None else 1}))
                        emit(terminal or dict(type='event', event='terminated', body={}))
                        return
                    stop.wait(.25)
            except Exception as error:
                emit(dict(type='event', event='output', body=dict(category='stderr', output='Procedure connection lost: ' + str(error) + '\n')))
                emit(dict(type='event', event='terminated', body={})); return

    reader = MessageReader(); event_thread = None
    try:
        while data := sys.stdin.buffer.read1(65536):
            for request in reader.feed(data):
                command = request.get('command'); values = request.get('arguments') or {}
                response = dict(type='response', request_seq=request['seq'], command=command, success=True, body={})
                try:
                    if command == 'initialize':
                        response['body'] = dict(supportsConfigurationDoneRequest=True, supportsSetVariable=True)
                    elif command == 'launch':
                        program = Path(values['program']).resolve()
                        result = client.request('/api/run', dict(script=program.relative_to(args.project.resolve()).as_posix(),
                            interpreter=args.interpreter, image=args.image, args=values.get('args', []), noDebug=values.get('noDebug', False),
                            stopOnEntry=values.get('stopOnEntry', False), configure=False), timeout=120)
                        run_id = result['id']
                        emit(dict(type='event', event='openbexi/service', body=dict(endpoint=str(endpoint), id=run_id)))
                        event_thread = threading.Thread(target=events, daemon=True); event_thread.start()
                    elif command in {'openbexi/claim', 'openbexi/release'} and run_id:
                        response['body'] = client.request('/api/control', dict(id=run_id, release=command == 'openbexi/release'))
                    elif run_id:
                        response['body'] = client.request('/api/command', dict(id=run_id, command=command, arguments=values))
                        if command == 'disconnect':
                            deadline = time.monotonic() + 45
                            while time.monotonic() < deadline:
                                state = client.request('/api/state')
                                if not next(item for item in state['runs'] if item['id'] == run_id)['active']:
                                    break
                                time.sleep(.1)
                            else:
                                raise RuntimeError('Native shutdown is still pending; the execution slot remains reserved')
                    elif command != 'disconnect':
                        raise RuntimeError('Launch a procedure first')
                except Exception as error:
                    response.update(success=False, message=str(error))
                emit(response)
                if command == 'disconnect':
                    return 0
    finally:
        # EOF detaches this connection. The server's lease requests a pause;
        # a killed client cannot silently authorize background execution.
        stop.set()
        if event_thread:
            event_thread.join(timeout=2)
        try:
            client.request('/api/disconnect', {}, timeout=3)
        except Exception:
            pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
