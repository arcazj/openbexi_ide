"""Bind the tested partial milestone to exact evidence and canonical source bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import xml.etree.ElementTree as ET
import zipfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(path):
    return path.read_bytes().replace(b'\r\n', b'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tests', type=Path, required=True)
    parser.add_argument('--installed', type=Path, required=True)
    parser.add_argument('--wheel', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tree = ET.parse(args.tests)
    suites = tree.findall('.//testsuite')
    counts = {key: sum(int(s.get(key, '0')) for s in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
    assert counts['tests'] >= 83 and not any(counts[key] for key in ('failures', 'errors', 'skipped')), counts
    installed = json.loads(args.installed.read_text(encoding='utf-8'))
    assert installed['passed'] and installed['wheel_sha256'] == digest(args.wheel)
    sources = {}
    paths = sorted([*root.glob('src/**/*.py'), *root.glob('tests/*.py'),
                    root / 'pyproject.toml', root / 'NOTICE',
                    root / 'scripts/qualify_durable_installed.py', Path(__file__).resolve()])
    for path in paths:
        sources[path.relative_to(root).as_posix()] = hashlib.sha256(normalized(path)).hexdigest()
    # The accepted candidate must contain precisely the current runtime/GUI
    # source, not an older wheel with the same (unchanged release) version label.
    with zipfile.ZipFile(args.wheel) as archive:
        for path in root.glob('src/**/*.py'):
            assert archive.read(path.relative_to(root / 'src').as_posix()).replace(b'\r\n', b'\n') == normalized(path), path
    report = {
        'schema': 'openbexi.durable-prerequisite-qualification/1',
        'release_accepted': False,
        'scope': 'IDE v0.3 partial durable Development prerequisite; plugin v0.4-v0.6 remain open',
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'platform': platform.platform(), 'python': platform.python_version(),
        'tests': counts,
        'source_hash_format': 'SHA-256 of bytes with CRLF normalized to LF',
        'sources': sources,
        'artifacts': {name: {'path': path.resolve().relative_to(root).as_posix(), 'sha256': digest(path)}
                      for name, path in (('wheel', args.wheel), ('source_tests', args.tests), ('installed', args.installed))},
        'installed_checks': installed['checks'],
        'remaining_gates': [
            'IDE v0.3 approved immutable release authority and qualified Execution isolation',
            'Interpreter and third-party dependency provenance beyond the captured Git tree',
            'Native shared runtime and fine-grained external-effect receipts',
            'Plugin v0.4 original DSS driver/RPC integration and three-mode acceptance',
            'Plugin v0.5 all 763 independent inventory requirements',
            'Plugin v0.6 reproducibility, upgrades, actual hosts and DSS distribution'],
    }
    (root / 'docs/DURABLE_QUALIFICATION.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'tests': counts, 'wheel_sha256': digest(args.wheel), 'release_accepted': False}))


if __name__ == '__main__':
    main()
