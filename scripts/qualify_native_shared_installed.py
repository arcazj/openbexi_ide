"""Exercise installed core/optional native provider wheels without repository imports."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

import openbexi_runtime
import openbexi_spell_shared
import openbexi_spell_host
from openbexi_runtime.cli import request


def wait(predicate, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.04)
    raise AssertionError('Installed native shared condition did not arrive')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--core-wheel', type=Path, required=True)
    parser.add_argument('--provider-wheel', type=Path, required=True)
    parser.add_argument('--host-wheel', type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    origins = {m.__name__: m.__file__ for m in (openbexi_runtime, openbexi_spell_shared, openbexi_spell_host)}
    assert all('site-packages' in path for path in origins.values())
    assert importlib.util.find_spec('PySide6') is None and importlib.util.find_spec('spell') is None
    project = root / 'project'
    project.mkdir()
    (project / 'main.py').write_text("from spell.lang.functions import Display\nfrom pathlib import Path\nDisplay('INSTALLED_NATIVE_OK')\nPath('result.txt').write_text('installed native result')\n")
    (project / 'wait.py').write_text("import time\nfrom spell.lang.functions import Display\nDisplay('INSTALLED_NATIVE_WAIT')\nwhile True:\n    time.sleep(.02)\n")
    for command in (['init', '-q'], ['add', '.'], ['-c', 'user.name=Qualification',
                    '-c', 'user.email=qualification@example.invalid', '-c', 'commit.gpgsign=false',
                    'commit', '-qm', 'Native shared installed qualification']):
        subprocess.run(['git', '-C', str(project), *command], capture_output=True, check=True)
    state, info = root / 'authority', root / 'server.json'
    command = [sys.executable, '-I', '-m', 'openbexi_runtime.cli', 'serve', '--project', str(project),
               '--state-directory', str(state), '--info', str(info), '--port', '0']
    child = None
    def start():
        nonlocal child
        previous = info.read_bytes() if info.exists() else None
        child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        wait(lambda: info.exists() and info.read_bytes() != previous, timeout=20)
        configuration = json.loads(info.read_bytes())
        actor = request(configuration['url'], '/connect', {'name': 'Installed native tester',
                                                         'invite': configuration['developer_invite']})
        epoch = request(configuration['url'], '/claim', {}, actor['token'])['epoch']
        return configuration, actor, epoch
    def stop():
        nonlocal child
        if child is not None:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)
            child = None
    try:
        config, actor, epoch = start()
        url, token = config['url'], actor['token']
        def snapshot():
            return request(url, '/session', token=token)
        def run(script):
            return request(url, '/run', {'epoch': epoch, 'script': script, 'language': 'spell'}, token)['id']
        done = run('main.py')
        wait(lambda: any(p['id'] == done and p['status'] == 'COMPLETED' for p in snapshot()['procedures']))
        artifact = state / 'results/.openbexi/runs' / done / 'artifacts/result.txt'
        assert artifact.read_text() == 'installed native result'
        monitor = request(url, '/connect', {'name': 'Reader', 'invite': config['monitor_invite']})
        try:
            request(url, '/run', {'epoch': epoch, 'script': 'main.py', 'language': 'spell'}, monitor['token'])
        except ValueError as error:
            assert 'read-only' in str(error)
        else:
            raise AssertionError('Monitor admitted native work')
        active = run('wait.py')
        wait(lambda: any('INSTALLED_NATIVE_WAIT' in e.get('text', '') for e in snapshot()['events']))
        queued = run('main.py')
        original = snapshot()
        assert next(p for p in original['procedures'] if p['id'] == queued)['pid'] is None
        stop()
        (project / 'main.py').write_text('raise RuntimeError("mutable host must not execute")\n')
        old_token, old_epoch = token, epoch
        config, actor, epoch = start()
        url, token = config['url'], actor['token']
        recovered = snapshot()
        assert recovered['session'] == original['session'] and epoch > old_epoch
        rows = {p['id']: p for p in recovered['procedures']}
        held = rows[active]
        assert held['status'] == 'RECOVERY_REQUIRED' and held['uncertain_effects'] and held['has_token']
        assert held['pid'] is None and rows[queued]['status'] == 'PAUSED' and rows[queued]['pid'] is None
        name, labels = openbexi_spell_shared.identities(config['session'], active)
        assert openbexi_spell_shared.owned(name, labels, held['backend']['image']) is None
        try:
            request(url, '/session', token=old_token)
        except ValueError:
            pass
        else:
            raise AssertionError('Old credential survived service loss')
        for route, body in (('/run', {'script': 'wait.py', 'language': 'spell'}), ('/resume', {'procedure': active})):
            try:
                request(url, route, {'epoch': epoch, **body}, token)
            except ValueError:
                pass
            else:
                raise AssertionError('Uncertain native work replayed')
        request(url, '/configure', {'epoch': epoch, 'max_parallel': 2}, token)
        request(url, '/resume', {'epoch': epoch, 'procedure': queued}, token)
        wait(lambda: any(p['id'] == queued and p['status'] == 'COMPLETED' for p in snapshot()['procedures']))
        assert any(e.get('procedure') == queued and 'INSTALLED_NATIVE_OK' in e.get('text', '') for e in snapshot()['events'])
        report = {'passed': True, 'scope': 'native shared Development; no operational Execution approval',
                  'python': sys.version, 'origins': origins, 'binding': held['backend'],
                  'docker': json.loads(openbexi_spell_shared.docker('version', '--format', '{{json .Server}}')),
                  'artifacts': {name: {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                                for name, path in [('core', args.core_wheel), ('provider', args.provider_wheel), ('host', args.host_wheel)]},
                  'checks': ['non-editable core/provider/host wheels without Qt or host SPELL imports',
                             'original native runtime executes committed source and exports results',
                             'monitor cannot submit native work', 'real service kill and owned-container recovery',
                             'old credentials fenced and uncertain work cannot replay',
                             'queued capture explicitly resumes after host edit',
                             'durable native output and image binding survive restart']}
        (root / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        stop()


if __name__ == '__main__':
    main()
