"""Bind offline Python Execution acceptance to tested source and installed bytes."""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tests', type=Path, required=True)
    parser.add_argument('--installed', type=Path, required=True)
    parser.add_argument('--wheel', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    suites = ET.parse(args.tests).findall('.//testsuite')
    counts = {k: sum(int(s.get(k, '0')) for s in suites) for k in ('tests', 'failures', 'errors', 'skipped')}
    assert counts['tests'] >= 93 and not any(counts[k] for k in ('failures', 'errors', 'skipped')), counts
    installed = json.loads(args.installed.read_text(encoding='utf-8'))
    assert installed['passed'] and installed['wheel_sha256'] == sha(args.wheel)
    assert installed['approval']['approved']
    with zipfile.ZipFile(args.wheel) as wheel:
        for path in root.glob('src/**/*.py'):
            assert wheel.read(path.relative_to(root / 'src').as_posix()).replace(b'\r\n', b'\n') == path.read_bytes().replace(b'\r\n', b'\n'), path
        notice = next(n for n in wheel.namelist() if n.endswith('/licenses/NOTICE'))
        assert wheel.read(notice).replace(b'\r\n', b'\n') == (root / 'NOTICE').read_bytes().replace(b'\r\n', b'\n')
    source_paths = [*root.glob('src/**/*.py'), *root.glob('tests/*.py'),
                    root / 'scripts/qualify_execution_installed.py', Path(__file__).resolve(),
                    root / 'docker/Dockerfile.execution', root / 'pyproject.toml', root / 'NOTICE',
                    root / 'docs/EXECUTION_SERVICE.md']
    release_manifest = Path(installed['release']['manifest'])
    report = {
        'schema': 'openbexi.execution-prerequisite-qualification/1',
        'qualified_utc': datetime.now(timezone.utc).isoformat(),
        'profile_accepted': True, 'release_accepted': False,
        'scope': 'Approved offline Python Execution only; IDE v0.3 and plugin v0.4-v0.6 remain open',
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'platform': platform.platform(), 'python': platform.python_version(),
        'docker': installed['docker'], 'runtime_image': installed['runtime_image'],
        'tests': counts, 'installed_checks': installed['checks'],
        'source_hash_format': 'SHA-256 of UTF-8 bytes with CRLF normalized to LF',
        'sources': {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                    for p in sorted(source_paths)},
        'artifacts': {name: {'path': path.resolve().relative_to(root).as_posix(), 'sha256': sha(path)}
                      for name, path in [('wheel', args.wheel), ('tests', args.tests), ('installed', args.installed),
                                         ('synthetic_release_manifest', release_manifest)]},
        'limits': ['Reviewed offline Python only; no native shared SPELL or DSS endpoints',
                   'Docker daemon and administering OS account are trusted',
                   'Single durable authority; no distributed admission across independent authorities',
                   'Image freezes installed bytes; upstream provenance and reproducible builds remain open',
                   'Temporary outputs discarded; no persistent artifact export',
                   'Approval fixtures are synthetic and confer no operational authorization'],
        'remaining_gates': ['Native shared-runtime integration and operational external-effect receipts',
                            'Full runtime supply-chain provenance and operational isolation qualification',
                            'Plugin v0.4 original DSS driver/RPC integration and three-mode acceptance',
                            'Plugin v0.5 independent 763-row conformance inventory',
                            'Plugin v0.6 distribution, upgrades, reproducibility and actual-host acceptance']}
    (root / 'docs/EXECUTION_QUALIFICATION.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'tests': counts, 'wheel_sha256': sha(args.wheel), 'release_accepted': False}))


if __name__ == '__main__':
    main()
