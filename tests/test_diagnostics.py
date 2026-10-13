"""Diagnostics inspect package metadata without importing backend code."""
import json
import sys
import subprocess
from pathlib import Path

from openbexi_runtime import diagnostics


def test_metadata_inventory_never_imports_a_plugin_or_exposes_environment(tmp_path, monkeypatch):
    marker = tmp_path/'imported'
    (tmp_path/'dangerous_backend.py').write_text(f'open({str(marker)!r}, "w").write("effect")\n')
    info = tmp_path/'diagnostic_fixture-1.0.dist-info'
    info.mkdir()
    (info/'METADATA').write_text('Metadata-Version: 2.1\nName: diagnostic-fixture\nVersion: 1.0\n')
    (info/'entry_points.txt').write_text('[openbexi.backends.v1]\nfixture = dangerous_backend:describe\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv('OPENBEXI_DIAGNOSTIC_SECRET', 'never-copy-this-value')
    value = diagnostics.report()
    text = json.dumps(value)
    assert {'name':'diagnostic-fixture', 'version':'1.0', 'backends':['fixture']} in value['optional_plugins']
    assert not marker.exists() and 'dangerous_backend' not in sys.modules
    assert 'never-copy-this-value' not in text and str(tmp_path) not in text
    assert 'target' not in text


def test_missing_desktop_dependency_is_reported_but_headless_remains_usable(monkeypatch):
    original = diagnostics.package_version
    monkeypatch.setattr(diagnostics, 'package_version', lambda name: None if name=='debugpy' else original(name))
    assert diagnostics.report()['ready']
    value = diagnostics.report(desktop=True)
    assert not value['ready'] and value['desktop_dependencies']['debugpy']['installed'] is None


def test_untrusted_version_metadata_is_bounded(monkeypatch):
    monkeypatch.setattr(diagnostics.metadata, 'version', lambda name: 'path/credential\n' + 'x'*10000)
    assert diagnostics.package_version('example') == 'invalid-metadata'


def test_public_doctor_command_needs_no_session_credentials(tmp_path):
    command = [sys.executable, '-I', str(Path(__file__).resolve().parents[1]/'run_cli.py'),
               '--connection', str(tmp_path/'nonexistent-credentials'), 'doctor', '--desktop']
    completed = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
    value = json.loads(completed.stdout)
    assert value['ready'] and value['python']['isolated']
    assert str(tmp_path) not in completed.stdout
