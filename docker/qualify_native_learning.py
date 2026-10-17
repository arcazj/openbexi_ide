"""Exercise the installed learning runtime through real IDE Run and Debug."""
import json
import hashlib
from importlib.metadata import version
from pathlib import Path
import shutil
import tempfile
import time

from PySide6.QtWidgets import QApplication
from openbexi_ide.controller import RunController
from openbexi_ide.debugger import DebugController
from openbexi_runtime.launch import LaunchSpec

app = QApplication([])


def wait(predicate, timeout=60):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert predicate(), 'IDE workflow timed out'


report = {'passed': False, 'cases': []}
report['ide_version'] = version('openbexi-ide')
report['runtime_manifest_sha256'] = hashlib.sha256(Path('/opt/spell-native/runtime-manifest.json').read_bytes()).hexdigest()
try:
    with tempfile.TemporaryDirectory(prefix='native-ide-qualification-') as temporary:
        project = Path(temporary) / 'project'
        shutil.copytree('/opt/openbexi/examples', project)
        script = project / 'test_spell/command_wait_telemetry.py'
        for debug in (False, True):
            controller = DebugController() if debug else RunController()
            exits, errors, output, stacks = [], [], [], []
            controller.finished.connect(exits.append)
            controller.error.connect(errors.append)
            controller.output.connect(output.append)
            try:
                spec = LaunchSpec(project, script, language='spell')
                if debug:
                    controller.stack_changed.connect(stacks.append)
                    line = next(i for i, text in enumerate(script.read_text().splitlines(), 1)
                                if text.startswith("Step('enable'"))
                    controller.start(spec, {script: [line]})
                    wait(lambda: bool(stacks) or bool(errors) or bool(exits))
                    assert not errors and not exits and stacks, (errors, exits, output)
                    assert stacks[-1][0]['line'] == line, stacks
                    controller.control('next')
                    wait(lambda: len(stacks) > 1 or bool(errors))
                    assert not errors, errors
                    controller.control('continue')
                else:
                    controller.start(spec)
                wait(lambda: bool(exits) or bool(errors))
                assert not errors and exits == [0], (errors, exits, output)
                assert 'SPELL_COMMAND_TELEMETRY_PASS' in ''.join(output), output
                report['cases'].append({'debug': debug, 'output': ''.join(output), 'stacks': stacks})
            finally:
                controller.stop()
                wait(lambda: not controller.running)
        manifests = list(project.glob('.openbexi/runs/*/manifest.json'))
        assert len(manifests) == 2, manifests
        report['runs'] = [json.loads(path.read_text()) for path in manifests]
        assert all(row['image'] == 'packaged-native-desktop:sha256:' + report['runtime_manifest_sha256'] for row in report['runs'])
    report['passed'] = True
finally:
    Path('/evidence/native-learning.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'passed':report['passed'], 'cases':len(report['cases']),
                      'ide_version':report['ide_version'], 'runtime_manifest_sha256':report['runtime_manifest_sha256']}), flush=True)
