import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile

import pytest
from PySide6.QtCore import QTimer, Qt

from openbexi_ide.plugin_manager import PluginManager, validate_plugin_wheel
from openbexi_runtime.launch import LaunchSpec, interpreter_info


def fixture_wheel(root, name='neutral-productivity-plugin'):
    import base64
    stem = name.replace('-', '_') + '-1.0'
    metadata = stem + '.dist-info/'
    files = {
        'neutral_productivity_plugin.py': b"def describe():\n    return {'api':1,'id':'fixture','label':'Fixture','runner':'neutral_productivity_plugin','debugAdapter':'neutral_productivity_plugin'}\n",
        metadata + 'METADATA': f'Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n'.encode(),
        metadata + 'WHEEL': b'Wheel-Version: 1.0\nGenerator: OpenBEXI fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
        metadata + 'entry_points.txt': b'[openbexi.backends.v1]\nfixture = neutral_productivity_plugin:describe\n',
    }
    record = io.StringIO(newline='')
    writer = csv.writer(record)
    for path, content in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip('=')
        writer.writerow((path, 'sha256=' + digest, len(content)))
    writer.writerow((metadata + 'RECORD', '', ''))
    files[metadata + 'RECORD'] = record.getvalue().encode()
    wheel = root / (stem + '-py3-none-any.whl')
    with zipfile.ZipFile(wheel, 'w') as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return wheel


def await_ui(app, predicate):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Plugin operation did not finish')


def test_actual_wheel_install_remove_and_plain_python(app, tmp_path):
    environment = tmp_path/'python'
    subprocess.run([sys.executable, '-I', '-m', 'venv', str(environment)], check=True, timeout=45)
    python = environment/('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    wheel = fixture_wheel(tmp_path)
    dialog = PluginManager(python)
    dialog.show()
    ticks = []
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start()
    try:
        await_ui(app, lambda: dialog.operation is None and dialog.status.text() == 'No runtime plugins installed.')
        assert dialog.install_wheel(wheel)
        assert not dialog.install_button.isEnabled()
        before = len(ticks)
        await_ui(app, lambda: dialog.operation is None and dialog.packages.count() == 1)
        assert len(ticks) > before
        package = dialog.packages.item(0).data(Qt.UserRole)
        assert package['name'] == 'neutral-productivity-plugin' and package['version'] == '1.0'
        assert interpreter_info(python, language='fixture')['backend']['id'] == 'fixture'
        dialog.packages.setCurrentRow(0)
        assert dialog.remove_button.isEnabled() and dialog.remove_selected()
        await_ui(app, lambda: dialog.operation is None and dialog.packages.count() == 0)
        assert interpreter_info(python)['backends'] == []
        script = tmp_path/'ordinary.py'
        script.write_text('print(42)\n')
        assert subprocess.check_output(LaunchSpec(tmp_path, script, python).command(), text=True).strip() == '42'
    finally:
        timer.stop()
        dialog.close()


def test_protected_and_nonplugin_wheels_are_rejected_before_pip(tmp_path):
    protected = fixture_wheel(tmp_path, 'openbexi-ide')
    with pytest.raises(ValueError, match='cannot be installed'):
        validate_plugin_wheel(protected)
    wheel = tmp_path/'ordinary-1.0-py3-none-any.whl'
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr('ordinary-1.0.dist-info/METADATA', 'Metadata-Version: 2.1\nName: ordinary\nVersion: 1.0\n')
    with pytest.raises(ValueError, match='does not declare'):
        validate_plugin_wheel(wheel)
