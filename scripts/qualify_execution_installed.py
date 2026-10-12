"""Qualify a fresh non-editable core wheel against actual Docker isolation.

Run with the installed interpreter's -I flag. All approvals are synthetic test
fixtures in the new output directory; no operational procedure is approved.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

import openbexi_runtime
from openbexi_runtime.cli import request
from openbexi_runtime.execution_release import docker
from openbexi_runtime.execution_container import container_name


def wait(predicate, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.04)
    raise AssertionError('Installed Execution condition did not arrive')


def cli(*args, succeeds=True):
    result = subprocess.run([sys.executable, '-I', '-m', 'openbexi_runtime.cli', *map(str, args)],
                            capture_output=True, timeout=300)
    assert (result.returncode == 0) == succeeds, result.stderr.decode(errors='replace')
    return json.loads(result.stdout) if succeeds else result.stderr.decode(errors='replace')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--runtime-image', required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    assert 'site-packages' in openbexi_runtime.__file__
    assert importlib.util.find_spec('PySide6') is None and importlib.util.find_spec('spell') is None
    project = root / 'project'
    project.mkdir()
    (project / 'main.py').write_text('''import os, pathlib, socket
from dependency import value
assert os.getuid() == 65532
for target in ('/release/dependency.py', '/usr/local/lib/forbidden'):
    try: pathlib.Path(target).write_text('tampered')
    except OSError: pass
    else: raise AssertionError('writable released runtime')
s=socket.socket(); s.settimeout(.2)
try: s.connect(('192.0.2.1',9))
except OSError: pass
else: raise AssertionError('external network available')
finally: s.close()
assert not pathlib.Path('/var/run/docker.sock').exists()
print(value, flush=True)
''')
    (project / 'dependency.py').write_text("value='installed approved dependency'\n")
    (project / 'wait.py').write_text("import time\nprint('ready',flush=True)\nwhile True: time.sleep(.02)\n")
    for command in (['init', '-q'], ['add', '.'], ['-c', 'user.name=Qualification',
                    '-c', 'user.email=qualification@example.invalid', '-c', 'commit.gpgsign=false',
                    'commit', '-qm', 'Synthetic execution qualification source']):
        subprocess.run(['git', '-C', str(project), *command], capture_output=True, check=True)
    release = cli('release-prepare', 'main.py', '--procedure', 'wait.py', '--project', project,
                  '--runtime-image', args.runtime_image, '--output', root / 'prepared')
    state, info = root / 'authority', root / 'server.json'
    assert 'not approved' in cli('serve', '--project', project, '--state-directory', state,
                                '--execution-release', release['release'], '--port', '0', succeeds=False)
    approval = cli('release-approve', '--manifest', release['manifest'], '--expected-release', release['release'],
        '--state-directory', state, '--actor', 'Installed qualification',
        '--evidence', 'Synthetic fixture; isolated package acceptance only')
    # A host edit cannot affect execution of the already approved image.
    (project / 'dependency.py').write_text("raise RuntimeError('mutable host file executed')\n")
    command = [sys.executable, '-I', '-m', 'openbexi_runtime.cli', 'serve', '--project', str(project),
               '--state-directory', str(state), '--execution-release', release['release'],
               '--info', str(info), '--port', '0']
    child = None
    def start():
        nonlocal child
        previous = info.read_bytes() if info.exists() else None
        child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        wait(lambda: info.exists() and info.read_bytes() != previous)
        configuration = json.loads(info.read_bytes())
        actor = request(configuration['url'], '/connect', {'name': 'Installed operator',
                                                         'invite': configuration['developer_invite']})
        return configuration, actor

    try:
        config, actor = start()
        url = config['url']
        epoch = request(url, '/claim', {}, actor['token'])['epoch']
        done = request(url, '/run', {'epoch': epoch, 'script': 'main.py'}, actor['token'])['id']
        def completed():
            snapshot = request(url, '/session', token=actor['token'])
            return snapshot if any(p['id'] == done and p['status'] == 'COMPLETED'
                                   for p in snapshot['procedures']) else None
        snapshot = wait(completed)
        assert any('installed approved dependency' in e.get('text', '') for e in snapshot['events'])
        active = request(url, '/run', {'epoch': epoch, 'script': 'wait.py'}, actor['token'])['id']
        wait(lambda: any(e.get('procedure') == active and 'ready' in e.get('text', '')
                        for e in request(url, '/session', token=actor['token'])['events']))
        queued = request(url, '/run', {'epoch': epoch, 'script': 'main.py'}, actor['token'])['id']
        name = container_name(config['session'], active)
        child.kill()
        child.communicate(timeout=10)
        child = None
        wait(lambda: not json.loads(docker('inspect', name))[0]['State']['Running'])
        old_actor = actor
        recovered, actor = start()
        url = recovered['url']
        snapshot = request(url, '/session', token=actor['token'])
        assert snapshot['mode'] == 'Execution' and snapshot['release_id'] == release['release']
        assert snapshot['controller'] is None
        rows = {p['id']: p for p in snapshot['procedures']}
        assert rows[active]['status'] == 'RECOVERY_REQUIRED' and rows[active]['uncertain_effects']
        assert rows[queued]['status'] == 'PAUSED' and rows[queued]['pid'] is None
        assert not docker('ps', '-a', '--filter', 'name=^/' + name + '$', '--format', '{{.ID}}').strip()
        try:
            request(url, '/session', token=old_actor['token'])
        except ValueError:
            pass
        else:
            raise AssertionError('Old credential survived service loss')
        report = {'passed': True, 'scope': 'Offline Python Execution prerequisite; IDE v0.3 remains open',
                  'runtime_origin': openbexi_runtime.__file__, 'python': sys.version,
                  'wheel_sha256': hashlib.sha256(args.wheel.read_bytes()).hexdigest(),
                  'release': release, 'approval': approval, 'runtime_image': args.runtime_image,
                  'docker': json.loads(docker('version', '--format', '{{json .Server}}')),
                  'checks': ['fresh non-editable core without Qt or SPELL', 'CLI prepare and offline approval',
                             'unapproved release denied', 'immutable source despite changed host dependency',
                             'non-root read-only runtime without network or host mounts',
                             'real service kill stops owned container', 'restart fences old credentials',
                             'uncertainty hold and paused queue without replay']}
        (root / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        if child is not None:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)


if __name__ == '__main__':
    main()
