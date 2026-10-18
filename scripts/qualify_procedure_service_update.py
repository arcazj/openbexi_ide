"""Native service upgrade refuses live executions and migrates idle history."""
import argparse
import json
from importlib.metadata import version
from pathlib import Path
import sys
import time
import traceback

from openbexi_runtime.procedure_client import Client, ensure_service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    project = args.output / 'project'; project.mkdir()
    (project / 'waiting.py').write_text("from spell.lang.functions import Prompt\nfrom spell.lang.constants import YES_NO\nPrompt('Keep this execution alive', Type=YES_NO)\n", encoding='utf-8')
    report = dict(passed=False, version=version('openbexi-ide'), checks=[])
    client = None; identifier = None
    def run():
        return next(item for item in client.request('/api/state')['runs'] if item['id'] == identifier)
    def wait(predicate):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if predicate(): return
            time.sleep(.1)
        raise AssertionError('Timed out waiting for native service state')
    try:
        endpoint = ensure_service(project)
        client = Client.connect(endpoint, 'Native upgrade qualification')
        identifier = client.request('/api/run', dict(script='waiting.py', interpreter=sys.executable, noDebug=True), timeout=120)['id']
        wait(lambda: run()['prompt'] is not None)
        config = json.loads(endpoint.read_text(encoding='utf-8')); original_pid = config['pid']
        config['implementation'] = 'qualification-prior-build'
        endpoint.write_text(json.dumps(config), encoding='utf-8')
        try:
            ensure_service(project)
        except RuntimeError as error:
            assert 'live procedures' in str(error), error
        else:
            raise AssertionError('Update replaced a service with a live executor')
        assert run()['active'] and json.loads(endpoint.read_text())['pid'] == original_pid
        report['checks'].append('A changed service implementation refuses replacement while an original native prompt is live')
        client.request('/api/command', dict(id=identifier, command='disconnect', arguments={'terminateDebuggee': True}))
        wait(lambda: not run()['active'])
        endpoint = ensure_service(project)
        updated = json.loads(endpoint.read_text(encoding='utf-8'))
        assert updated['pid'] != original_pid and updated['implementation'] != 'qualification-prior-build'
        client = Client.connect(endpoint, 'Updated service')
        restored = run()
        assert not restored['active'] and restored['status'] == 'ABORTED' and 'Keep this execution alive' in restored['sources'][str(project / 'waiting.py')]
        report['checks'].append('Idle update starts a new service and restores the original captured source and terminal record without replay')
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        if client:
            try:
                if identifier and run()['active']:
                    client.request('/api/command', dict(id=identifier, command='disconnect', arguments={'terminateDebuggee': True}))
                client.request('/api/disconnect', {})
            except Exception:
                pass
        (args.output / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2)); return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
