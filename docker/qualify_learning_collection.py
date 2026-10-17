"""Run each native learning procedure through the installed IDE controller."""
import json
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
import time
from PySide6.QtWidgets import QApplication
from openbexi_ide.controller import RunController
from openbexi_runtime.launch import LaunchSpec

app = QApplication([])
report = {'passed': False, 'cases': []}
names = ['test_spell', 'spell_native_data', 'spell_native_time', 'command_wait_telemetry',
         'telemetry_for_loop', 'telemetry_raw_engineering', 'telemetry_verify_conditions',
         'telemetry_timeout_recovery', 'command_setpoint', 'command_group',
         'command_rejection_recovery', 'command_execution_failure',
         'limits_and_ground_parameters', 'resources_roundtrip', 'ranging_lifecycle', 'spell_all_features', 'command_temperature_ramp']
names += ['spell_sdk_telemetry', 'monitoring_driver_guard', 'spell_native_prompt',
          'spell_native_child', 'spell_native_parent', 'spell_menu', 'stop_and_rerun']
if sys.argv[1:]:
    names = sys.argv[1:]


def wait(predicate, timeout=60):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert predicate(), 'IDE example timed out'


with tempfile.TemporaryDirectory(prefix='learning-collection-') as temporary:
    project = Path(temporary) / 'project'
    shutil.copytree('/opt/openbexi/examples', project)
    for name in names:
        controller = RunController()
        exits, errors, output = [], [], []
        controller.finished.connect(exits.append)
        controller.error.connect(errors.append)
        controller.output.connect(output.append)
        case = {'name': name, 'passed': False,
                'source_sha256':hashlib.sha256((project/'test_spell'/f'{name}.py').read_bytes()).hexdigest()}
        started = time.monotonic()
        try:
            arguments = ('{"LAB_MODE":"Monitoring"}',) if name == 'monitoring_driver_guard' else ()
            controller.start(LaunchSpec(project, project/'test_spell'/f'{name}.py', language='spell', arguments=arguments))
            answers = {'spell_native_prompt':['0','1'], 'spell_native_child':['1'],
                       'spell_native_parent':['0','1'], 'spell_menu':['18','0']}.get(name, [])
            if name == 'spell_menu' and Path('/evidence/menu-answers.json').is_file():
                answers = json.loads(Path('/evidence/menu-answers.json').read_text())
            for index, answer in enumerate(answers, 1):
                wait(lambda: ''.join(output).count('SPELL choices (enter the native option index):') >= index or bool(exits) or bool(errors))
                assert not exits and not errors, (exits, errors, output)
                controller.send_input(answer)
            if name == 'stop_and_rerun':
                wait(lambda: 'STOP_DEMO sample=' in ''.join(output) or bool(exits) or bool(errors))
                assert not exits and not errors, (exits, errors)
                controller.stop()
                wait(lambda: bool(exits) or bool(errors))
                assert not errors and exits == [130], (errors, exits)
            else:
                wait(lambda: bool(exits) or bool(errors))
                assert not errors and exits == [0], (errors, exits)
                assert '_PASS' in ''.join(output), 'Missing completion marker'
            case['passed'] = True
        except Exception as error:
            case['error'] = str(error)
        finally:
            controller.stop()
            wait(lambda: not controller.running)
            case.update(output=''.join(output), errors=errors, exits=exits, seconds=time.monotonic()-started)
            report['cases'].append(case)
            Path('/evidence/learning-collection.json').write_text(json.dumps(report, indent=2))
            print(json.dumps({k:v for k,v in case.items() if k not in ('output',)}), flush=True)
            if not case['passed']:
                print(case['output'][-4000:], flush=True)
report['passed'] = all(case['passed'] for case in report['cases'])
Path('/evidence/learning-collection.json').write_text(json.dumps(report, indent=2))
raise SystemExit(0 if report['passed'] else 1)
