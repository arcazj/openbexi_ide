"""Real packaged native concurrency rejection, Stop, process cleanup and rerun."""
import json
from pathlib import Path
import shutil
import tempfile
import time
from PySide6.QtWidgets import QApplication
from openbexi_ide.controller import RunController
from openbexi_runtime.launch import LaunchSpec

app = QApplication([])


def wait(predicate, timeout=45):
    end = time.monotonic()+timeout
    while not predicate() and time.monotonic()<end:
        app.processEvents()
        time.sleep(.01)
    assert predicate(), 'Ownership workflow timed out'


def native_processes():
    rows = []
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():
            continue
        try:
            command = (directory/'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
        except OSError:
            continue
        if any(name in command for name in ('/bridge/spell-host-ipc','spell_native/bin/', '/opt/host/adapter.py')):
            rows.append({'pid':int(directory.name),'command':command})
    return rows


report = {'passed':False, 'checks':[]}
try:
    assert not native_processes(), native_processes()
    with tempfile.TemporaryDirectory(prefix='learning-ownership-') as temporary:
        project = Path(temporary)/'project'
        shutil.copytree('/opt/openbexi/examples', project)
        first, second = RunController(), RunController()
        output, exits, errors, rejected, rejection = [], [], [], [], []
        first.output.connect(output.append)
        first.finished.connect(exits.append)
        first.error.connect(errors.append)
        second.output.connect(rejection.append)
        second.finished.connect(rejected.append)
        try:
            first.start(LaunchSpec(project, project/'test_spell/stop_and_rerun.py', language='spell'))
            wait(lambda:'STOP_DEMO sample=' in ''.join(output) or bool(errors) or bool(exits))
            assert not errors and not exits, (errors, exits, output)
            owned = native_processes()
            assert owned
            second.start(LaunchSpec(project, project/'test_spell/test_spell.py', language='spell'))
            wait(lambda:bool(rejected))
            assert rejected == [1] and 'already open' in ''.join(rejection), (rejected,rejection)
            assert first.running and not exits
            report['checks'].append('second run rejected without interrupting first')
            first.stop()
            wait(lambda:bool(exits))
            assert not errors and exits == [130], (errors,exits,output)
            wait(lambda:not native_processes())
            report['checks'].append('Stop reaped adapter, bridge, listener and executor')
            exits.clear(); output.clear()
            first.start(LaunchSpec(project, project/'test_spell/command_wait_telemetry.py', language='spell'))
            wait(lambda:bool(exits) or bool(errors))
            assert not errors and exits == [0] and 'SPELL_COMMAND_TELEMETRY_PASS' in ''.join(output), (errors,exits,output)
            wait(lambda:not native_processes())
            report['checks'].append('rerun completed with fresh telemetry and no remaining native processes')
            report['owned_processes'] = owned
        finally:
            first.stop(); second.stop()
            wait(lambda:not first.running and not second.running)
    report['passed'] = True
finally:
    Path('/evidence/native-ownership.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)
