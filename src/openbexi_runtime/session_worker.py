"""Isolated cooperative worker. Stack inspection never evaluates user expressions."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import threading
import time
from urllib.request import Request, urlopen


def main(*, pipe_report=None, infrastructure=()):
    if not sys.flags.isolated:
        raise RuntimeError('Session workers require -I')
    project, script = (Path(p).resolve() for p in sys.argv[1:3])
    if not project.is_dir() or not script.is_file() or not script.is_relative_to(project):
        raise RuntimeError('Invalid session project/script boundary')
    config = json.loads(os.environ.pop('OPENBEXI_SESSION_WORKER'))
    if hashlib.sha256(script.read_bytes()).hexdigest() != config['source_hash']:
        raise RuntimeError('Procedure changed after submission; submit the new version explicitly')
    runtime_root = str(Path(__file__).resolve().parents[1])
    sys.path.insert(0, runtime_root)
    from openbexi_runtime.processes import own_worker_tree
    own_worker_tree()
    sys.path.remove(runtime_root)
    sys.argv = [str(script), *sys.argv[3:]]
    paused, last_reports, lock = set(), {}, threading.RLock()
    pause_requested = threading.Event()
    sampler_identity = [None]
    root_text = str(project) + os.sep

    def relevant(frame):
        if frame.f_code.co_filename.startswith(runtime_root + os.sep):
            return False
        return frame.f_code.co_filename == str(script) or frame.f_code.co_filename.startswith(root_text)

    def snapshot(frame):
        frames, used = [], 0
        while frame is not None and len(frames) < 32:
            if relevant(frame):
                values = {}
                for name, value in list(frame.f_locals.items())[:16]:
                    if type(value) in {str, int, float, bool, type(None)}:
                        text = '<large int>' if type(value) is int and value.bit_length() > 1024 else str(value)[:80]
                        values[name[:64]] = text
                    else:
                        kind = type(value)
                        label = kind.__name__[:64] if type(kind) is type else 'object'
                        values[name[:64]] = '<' + label + '>'
                entry = {'file': frame.f_code.co_filename, 'line': frame.f_lineno,
                         'function': frame.f_code.co_name, 'locals': values}
                used += len(json.dumps(entry).encode('utf-8'))
                if used > 65536:
                    break
                frames.append(entry)
            frame = frame.f_back
        return frames

    def active_threads():
        # A library-created Python thread may have no project frame (for
        # example a Timer calling a builtin). It still owns execution and
        # must finish or acknowledge a traced pause before its slot is reused.
        return set(sys._current_frames()) - {sampler_identity[0]} - set(infrastructure)

    def report(frame, identifier, quiescent=False, bootstrap=False):
        body = {'id': config['id'], 'token': config['token'], 'pid': os.getpid(), 'quiescent': quiescent, 'bootstrap': bootstrap,
                'active_threads': [str(i) for i in active_threads()],
                'thread': {'id': str(identifier), 'name': next((t.name for t in threading.enumerate() if t.ident == identifier), 'Python thread'),
                           'stack': snapshot(frame), 'paused': identifier in paused}}
        if pipe_report is not None:
            return pipe_report(body)
        request = Request(config['url'] + '/worker/checkpoint', data=json.dumps(body).encode('utf-8'),
                          headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=3) as response:
                return json.load(response)['action']
        except Exception as error:
            # Stop the entire worker, including other threads. A disconnected
            # service cannot silently leave a Python thread running.
            print('Session connection lost; worker terminated', file=sys.stderr, flush=True)
            os._exit(75)

    def gate(frame, bootstrap=False):
        identifier = threading.get_ident()
        action = report(frame, identifier, bootstrap=bootstrap)
        while action == 'pause':
            pause_requested.set()
            with lock:
                paused.add(identifier)
                quiescent = active_threads().issubset(paused)
            action = report(frame, identifier, quiescent)
            if action == 'pause':
                time.sleep(0.05)
        with lock:
            paused.discard(identifier)
        if action == 'run':
            pause_requested.clear()
        if action == 'stop':
            os._exit(130)

    def trace(frame, event, _argument):
        if not relevant(frame):
            return None
        if event not in {'line', 'call', 'return'}:
            return trace
        identifier = threading.get_ident()
        current = time.monotonic()
        if not pause_requested.is_set() and current - last_reports.get(identifier, 0) < 0.05:
            return trace
        last_reports[identifier] = current
        gate(frame)
        return trace

    gate(None, bootstrap=True)
    if config['language'] == 'spell':
        from openbexi_spell_plugin.runtime import activate
        activate(config.get('dss_url'))
        import spell.lang
    sys.path[:0] = list(dict.fromkeys([str(script.parent), str(project)]))

    def sample_stacks():
        # Trace checkpoints alone would leave an old frame visible while a
        # procedure is blocked in input(), sleep(), or another native call.
        sampler_identity[0] = threading.get_ident()
        while True:
            time.sleep(0.15)
            for identifier, frame in sys._current_frames().items():
                if identifier == sampler_identity[0] or identifier in infrastructure:
                    continue
                with lock:
                    quiescent = active_threads().issubset(paused)
                action = report(frame, identifier, quiescent)
                if action == 'pause':
                    pause_requested.set()
                elif action == 'stop':
                    os._exit(130)

    threading.Thread(target=sample_stacks, name='session-stack-sampler', daemon=True).start()
    threading.settrace(trace)
    sys.settrace(trace)
    try:
        runpy.run_path(str(script), run_name='__main__')
    finally:
        sys.settrace(None)
        threading.settrace(None)


if __name__ == '__main__':
    main()
