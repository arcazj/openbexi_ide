"""Bind native shared acceptance to exact core/provider source and wheel bytes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import xml.etree.ElementTree as ET
import zipfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def counts(path):
    suites = ET.parse(path).findall('.//testsuite')
    result = {k: sum(int(s.get(k, '0')) for s in suites) for k in ('tests', 'failures', 'errors', 'skipped')}
    assert not any(result[k] for k in ('failures', 'errors', 'skipped')), result
    return result


def verify_wheel(path, source):
    with zipfile.ZipFile(path) as wheel:
        for file in source.glob('**/*.py'):
            assert wheel.read(file.relative_to(source).as_posix()).replace(b'\r\n', b'\n') == file.read_bytes().replace(b'\r\n', b'\n'), file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core-tests', type=Path, required=True)
    parser.add_argument('--native-tests', type=Path, required=True)
    parser.add_argument('--installed-core', type=Path, required=True)
    parser.add_argument('--installed-native', type=Path, required=True)
    parser.add_argument('--plugin-root', type=Path, required=True)
    args = parser.parse_args()
    root, plugin = Path(__file__).resolve().parents[1], args.plugin_root.resolve()
    core_counts, native_counts = counts(args.core_tests), counts(args.native_tests)
    assert core_counts['tests'] >= 96 and native_counts['tests'] >= 14
    installed_core = json.loads(args.installed_core.read_text())
    installed_native = json.loads(args.installed_native.read_text())
    assert installed_core['passed'] and installed_native['passed']
    artifacts = installed_native['artifacts']
    for value in artifacts.values():
        assert sha(Path(value['path'])) == value['sha256']
    assert installed_core['wheel_sha256'] == artifacts['core']['sha256']
    verify_wheel(Path(artifacts['core']['path']), root / 'src')
    verify_wheel(Path(artifacts['provider']['path']), plugin / 'shared_plugin/src')
    verify_wheel(Path(artifacts['host']['path']), plugin / 'host_plugin/src')
    for name, path in [('core_tests', args.core_tests), ('native_tests', args.native_tests),
                       ('installed_core', args.installed_core), ('installed_native', args.installed_native)]:
        artifacts[name] = {'path': str(path.resolve()), 'sha256': sha(path)}
    paths = [*root.glob('src/**/*.py'), *root.glob('tests/*.py'),
             root / 'scripts/qualify_native_shared_installed.py', Path(__file__).resolve(),
             root / 'docs/NATIVE_SHARED_SERVICE.md', root / 'pyproject.toml', root / 'NOTICE']
    plugin_paths = [*plugin.glob('shared_plugin/src/**/*.py'), plugin / 'shared_plugin/pyproject.toml',
                    plugin / 'shared_plugin/LICENSE', plugin / 'shared_plugin/README.md',
                    plugin / 'docs/SHARED_RUNTIME.md']
    sources = {**{'ide/' + p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest() for p in paths},
               **{'plugin/' + p.relative_to(plugin).as_posix(): hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest() for p in plugin_paths}}
    report = {'schema': 'openbexi.native-shared-development-qualification/1',
              'qualified_utc': datetime.now(timezone.utc).isoformat(),
              'profile_accepted': True, 'release_accepted': False,
              'scope': 'Original native shared Development only; IDE v0.3 and plugin v0.4-v0.6 remain open',
              'base_commits': {name: subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=path, text=True).strip()
                               for name, path in [('ide', root), ('plugin', plugin)]},
              'platform': platform.platform(), 'python': platform.python_version(),
              'binding': installed_native['binding'], 'docker': installed_native['docker'],
              'core_tests': core_counts, 'native_and_contract_tests': native_counts,
              'native_test_count': 11, 'repeated_core_contract_tests': 3,
              'installed_core_checks': installed_core['checks'], 'installed_native_checks': installed_native['checks'],
              'source_hash_format': 'SHA-256 with CRLF normalized to LF', 'sources': dict(sorted(sources.items())),
              'artifacts': artifacts,
              'limits': ['Windows x64 service controlling Linux amd64 Docker only',
                         'Trusted installed provider and Docker administrator; writable Development filesystem',
                         'Whole-container pause; no shared native debugger stack/evaluation contract',
                         'No independent in-container lease watchdog; service-loss cleanup requires owned recovery',
                         'Original isolated example driver only; no operational DSS network',
                         'Forced termination and detached descendants retain holds; no automatic replay',
                         'Single durable authority; full upstream/reproducible provenance remains open'],
              'remaining_gates': ['Approved native Execution and operational external-effect receipts',
                                  'Original registry/factory/driver manager, SPELLDriver.proto and binary/Kafka DSS integration',
                                  'Shared native debugger inspection and full runtime provenance',
                                  '763-row conformance, distribution/upgrades and actual-host release acceptance']}
    encoded = json.dumps(report, indent=2) + '\n'
    (root / 'docs/NATIVE_SHARED_QUALIFICATION.json').write_text(encoded, encoding='utf-8')
    (plugin / 'docs/SHARED_QUALIFICATION.json').write_text(encoded, encoding='utf-8')
    print(json.dumps({'core_tests': core_counts, 'native_and_contract_tests': native_counts,
                      'installed_checks': len(installed_core['checks']) + len(installed_native['checks']),
                      'release_accepted': False}))


if __name__ == '__main__':
    main()
