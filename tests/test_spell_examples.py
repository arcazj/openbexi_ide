"""Exercise the shipped SDK examples through the IDE's real script worker."""
import json
from pathlib import Path
import shutil
import threading

import pytest

from openbexi_runtime.launch import LaunchSpec
from test_runtime import capture
from test_debugger import wait_until

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples/test_spell'


@pytest.mark.parametrize('debug', [False, True])
def test_spell_sdk_through_desktop_run_and_debug(app, tmp_path, debug):
    pytest.importorskip('openbexi_spell_plugin')
    from openbexi_ide.controller import RunController
    from openbexi_ide.debugger import DebugController
    controller = DebugController() if debug else RunController()
    script = tmp_path / 'test_spell.py'
    shutil.copyfile(EXAMPLES / script.name, script)
    exits, output, errors = [], [], []
    controller.finished.connect(exits.append)
    controller.output.connect(output.append)
    controller.error.connect(errors.append)
    try:
        spec = LaunchSpec(tmp_path, script)
        controller.start(spec, {}) if debug else controller.start(spec)
        wait_until(app, lambda: bool(exits) or bool(errors))
        assert not errors, errors
        assert exits == [0]
        assert 'SPELL_EXAMPLE_PASS profile=browser-sdk' in ''.join(output)
        assert json.loads((tmp_path/'test_spell_result.json').read_text())['native_data'] is False
    finally:
        controller.stop()
        wait_until(app, lambda: not controller.running)


def test_spell_runs_in_browser_sdk_without_native_library(tmp_path):
    pytest.importorskip('openbexi_spell_plugin')
    script = tmp_path / 'test_spell.py'
    shutil.copyfile(EXAMPLES / script.name, script)
    code, output, errors = capture(LaunchSpec(tmp_path, script))
    assert code == 0, errors + output
    assert 'SPELL_EXAMPLE_PASS profile=browser-sdk' in output
    result = json.loads((tmp_path / 'test_spell_result.json').read_text())
    assert result['profile'] == 'browser-sdk' and result['native_data'] is False
    assert result['checks'] == ['Display', 'absolute and relative TIME', 'WaitFor']


@pytest.mark.parametrize('filename', ['spell_sdk_telemetry.py', 'spell_menu.py'])
def test_read_only_telemetry_example_with_real_dss(tmp_path, monkeypatch, filename):
    dss = pytest.importorskip('dss.local')
    runtime, tcp, http = dss.create_servers(tmp_path / 'dss.sqlite', 0)
    threads = [threading.Thread(target=server.serve_forever) for server in (tcp, http)]
    for thread in threads:
        thread.start()
    monkeypatch.setenv('OPENBEXI_DSS_URL', 'http://127.0.0.1:' + str(http.server_port))
    script = tmp_path / filename
    shutil.copyfile(EXAMPLES / script.name, script)
    shutil.copyfile(EXAMPLES/'feature_catalog.json', tmp_path/'feature_catalog.json')
    try:
        before = runtime.engine.state()['core']['commands_executed']
        code, output, errors = capture(LaunchSpec(tmp_path, script, arguments=('--all',)))
        assert code == 0, errors + output
        if filename == 'spell_menu.py':
            assert 'SPELL_MENU_COMPLETE checks=11 failures=0' in output
            rows = json.loads((tmp_path/'spell_menu_results.json').read_text())['results']
            assert sum(row['status'] == 'PASS' for row in rows) == 6
            assert sum(row['status'] == 'UNAVAILABLE' for row in rows) == 5
            assert len(json.loads((tmp_path/'feature_catalog.json').read_text(encoding='utf-8'))['rows']) == 763
            code, output, errors = capture(LaunchSpec(tmp_path, script),
                'invalid\n12\nTIME\n1\n14\n15\n16\nno\n16\nSEND CMD1\n0\n')
            assert code == 0, errors + output
            assert 'Invalid choice' in output and 'Published native v0.5 catalogue' in output
            assert 'PASS Send CMD1' in output
            assert runtime.engine.state()['core']['commands_executed'] == before + 1
            return
        assert 'SPELL_TELEMETRY_PASS' in output
        assert runtime.engine.state()['core']['commands_executed'] == before
    finally:
        for server in (tcp, http):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(5)
            assert not thread.is_alive()
        runtime.engine.close()
