"""Exercise a non-editable core wheel in a fresh interpreter, without Qt/SPELL.

Run with the installed environment's python -I and a new --output directory.
Creates only private qualification projects and processes owned by this script.
"""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import sys
import time

import openbexi_runtime
from openbexi_runtime.cli import request
from openbexi_runtime.processes import process_alive


def wait(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.025)
    raise AssertionError('Installed durable service condition did not arrive')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wheel', type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    assert 'site-packages' in openbexi_runtime.__file__, 'Editable/repository imports cannot qualify an installed artifact'
    import importlib.util
    assert importlib.util.find_spec('PySide6') is None
    assert importlib.util.find_spec('spell') is None
    project = root / 'project'
    project.mkdir()
    (project / 'main.py').write_text('from dependency import value\nprint(value, flush=True)\n')
    (project / 'dependency.py').write_text("value = 'installed captured dependency'\n")
    (project / 'wait.py').write_text('import time\nwhile True: time.sleep(0.02)\n')
    for command in (['init', '-q'], ['add', '.'],
                    ['-c', 'user.name=Qualification', '-c', 'user.email=qualification@example.invalid',
                     '-c', 'commit.gpgsign=false', 'commit', '-qm', 'qualification source']):
        subprocess.run(['git', '-C', str(project), *command], check=True, capture_output=True)
    state, info = root / 'state', root / 'server.json'
    command = [sys.executable, '-I', '-m', 'openbexi_runtime.cli', 'serve', '--project', str(project),
               '--state-directory', str(state), '--info', str(info), '--port', '0']
    def start():
        previous = info.read_bytes() if info.exists() else None
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        wait(lambda: info.exists() and info.read_bytes() != previous)
        configuration = json.loads(info.read_bytes())
        actor = request(configuration['url'], '/connect', {'name': 'Installed qualification',
                                                         'invite': configuration['developer_invite']})
        epoch = request(configuration['url'], '/claim', {}, actor['token'])['epoch']
        return process, configuration, actor, epoch
    child = None
    try:
        child, config, actor, epoch = start()
        url = config['url']
        done = request(url, '/run', {'epoch': epoch, 'script': 'main.py'}, actor['token'])['id']
        wait(lambda: any(p['id'] == done and p['status'] == 'COMPLETED'
                         for p in request(url, '/session', token=actor['token'])['procedures']))
        identifier = request(url, '/run', {'epoch': epoch, 'script': 'wait.py'}, actor['token'])['id']
        def running():
            return next((p for p in request(url, '/session', token=actor['token'])['procedures']
                         if p['id'] == identifier and p['status'] == 'RUNNING'), None)
        procedure = wait(running)
        child.kill()
        child.communicate(timeout=10)
        child = None
        wait(lambda: not process_alive(procedure['worker_pid']))
        previous_actor, previous_epoch = actor, epoch
        child, recovered, actor, epoch = start()
        assert recovered['session'] == config['session'] and epoch > previous_epoch
        url = recovered['url']
        snapshot = request(url, '/session', token=actor['token'])
        held = next(p for p in snapshot['procedures'] if p['id'] == identifier)
        assert held['status'] == 'RECOVERY_REQUIRED' and held['uncertain_effects'] and held['has_token']
        assert held['pid'] is None
        assert any('installed captured dependency' in e.get('text', '') for e in snapshot['events'])
        try:
            request(url, '/session', token=previous_actor['token'])
        except ValueError as error:
            assert 'credential' in str(error)
        else:
            raise AssertionError('Pre-crash credential remained usable')
        for path, body in (('/run', {'script': 'wait.py'}), ('/resume', {'procedure': identifier})):
            try:
                request(url, path, {'epoch': epoch, **body}, actor['token'])
            except ValueError:
                pass
            else:
                raise AssertionError('Recovery hold admitted replay')
        report = {'passed': True, 'scope': 'durable Development prerequisite milestone; release remains open',
                  'python': sys.version, 'platform': sys.platform, 'version': version('openbexi-ide'),
                  'runtime_origin': openbexi_runtime.__file__,
                  'wheel_sha256': hashlib.sha256(args.wheel.read_bytes()).hexdigest(),
                  'checks': ['fresh non-editable core without Qt or SPELL', 'committed source and dependency execution',
                             'real service kill and fresh-process recovery', 'owned worker shutdown',
                             'durable event replay', 'stale credential and epoch fencing',
                             'uncertain reservation prevents duplicate admission and automatic replay']}
        (root / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        if child is not None:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)


if __name__ == '__main__':
    main()
