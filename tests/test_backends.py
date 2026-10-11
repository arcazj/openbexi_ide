import json
from pathlib import Path
import subprocess
import sys

import pytest

from openbexi_runtime.launch import LaunchSpec, interpreter_info


def test_installed_backend_discovery_launch_removal_and_plain_python(tmp_path):
    environment = tmp_path / 'runtime'
    subprocess.run([sys.executable, '-I', '-m', 'venv', '--without-pip', str(environment)],
                   check=True, timeout=20)
    python = environment / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    site = Path(subprocess.check_output([str(python), '-I', '-c',
        "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True).strip())
    module = site / 'neutral_backend_fixture.py'
    module.write_text('''import json,sys
def describe():
    return {'api':1, 'id':'fixture', 'label':'Fixture runtime',
            'runner':'neutral_backend_fixture', 'debugAdapter':'neutral_backend_fixture'}
if __name__ == '__main__':
    print(json.dumps(sys.argv[1:]))
''')
    metadata = site / 'neutral_backend_fixture-1.0.dist-info'
    metadata.mkdir()
    (metadata / 'METADATA').write_text('Metadata-Version: 2.1\nName: neutral-backend-fixture\nVersion: 1.0\n')
    entry = metadata / 'entry_points.txt'
    entry.write_text('[openbexi.backends.v1]\nfixture = neutral_backend_fixture:describe\n')
    info = interpreter_info(python, require_debugger=True, language='fixture')
    assert info['debugpy'] is None
    assert info['backend']['id'] == 'fixture'
    script = tmp_path / 'main.py'
    script.write_text('print(42)\n')
    spec = LaunchSpec(tmp_path, script, python, ('two words', 'café'), 'fixture')
    result = subprocess.check_output(spec.command(info['backend']), text=True, encoding='utf-8')
    assert json.loads(result) == ['--project', str(tmp_path), '--program', str(script), '--', 'two words', 'café']
    with pytest.raises(ValueError, match='Validate the installed'):
        spec.command()
    module.write_text("def describe():\n    return {'api':2, 'id':'fixture'}\n")
    malformed = interpreter_info(python)
    assert malformed['backends'] == [] and malformed['backendErrors'][0]['id'] == 'fixture'
    with pytest.raises(ValueError, match='Install the fixture'):
        interpreter_info(python, language='fixture')
    entry.unlink()
    module.unlink()
    assert interpreter_info(python)['backends'] == []
    assert subprocess.check_output(LaunchSpec(tmp_path, script, python).command(), text=True).strip() == '42'
