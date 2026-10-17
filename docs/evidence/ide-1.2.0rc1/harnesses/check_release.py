"""Verify a local Windows/Docker IDE release dossier; missing gates stay open."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


GATES = ('windows_tests', 'linux_tests', 'installed_windows_lifecycle',
         'installed_docker_workflow', 'browser_interaction', 'fresh_windows_install')
ARTIFACTS = ('ide_wheel', 'windows_bundle', 'docker_image_record')


def checked_reference(root, reference):
    if type(reference) is not dict or set(reference) != {'path', 'sha256'}:
        raise ValueError('Evidence requires exactly path and sha256')
    path = (root / reference['path']).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Evidence must be a file inside the selected evidence root')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != reference['sha256']:
        raise ValueError('Evidence digest differs: ' + reference['path'])
    return path


def verify(root, manifest):
    if manifest.get('schema') != 1 or manifest.get('product') != 'openbexi_ide':
        raise ValueError('Unsupported release dossier')
    failures = []
    for kind in ARTIFACTS:
        reference = manifest.get('artifacts', {}).get(kind)
        if not reference:
            failures.append(kind + ': missing artifact')
            continue
        try:
            checked_reference(root, reference)
        except (ValueError, OSError, TypeError, KeyError) as error:
            failures.append(kind + ': ' + str(error))
    for name in GATES:
        gate = manifest.get('gates', {}).get(name, {})
        if gate.get('status') != 'passed':
            failures.append(name + ': ' + str(gate.get('status', 'missing')))
            continue
        try:
            path = checked_reference(root, gate['report'])
            if gate.get('format') == 'junit':
                document = ET.parse(path).getroot()
                suites = [document] if document.tag == 'testsuite' else list(document.iter('testsuite'))
                if not suites or sum(int(s.get('tests', 0)) for s in suites) <= 0:
                    raise ValueError('No test results')
                if any(int(s.get('failures', 0)) or int(s.get('errors', 0)) for s in suites):
                    raise ValueError('Test failures or errors remain')
                skipped = sum(int(s.get('skipped', 0)) for s in suites)
                if sum(int(s.get('tests', 0)) for s in suites) <= skipped:
                    raise ValueError('All tests are skipped')
                if skipped and not gate.get('skip_explanation'):
                    raise ValueError('Skipped tests need a recorded scope explanation')
            elif gate.get('format') == 'json':
                result = json.loads(path.read_text(encoding='utf-8'))
                if result.get('passed') is not True:
                    raise ValueError('Report does not pass')
                if result.get('version') != manifest.get('version'):
                    raise ValueError('Report version differs from release')
            else:
                raise ValueError('Unsupported evidence format')
        except (ValueError, OSError, TypeError, KeyError, ET.ParseError) as error:
            failures.append(name + ': ' + str(error))
    return {'product':'openbexi_ide', 'version':manifest.get('version'),
            'release_accepted': not failures, 'open_gates': failures,
            'scope':'Windows x64 and Linux Docker IDE; optional native plugin acceptance is separate'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = verify(args.root, json.loads(args.manifest.read_text(encoding='utf-8')))
    except (ValueError, OSError) as error:
        result = {'release_accepted':False, 'error':str(error)}
    print(json.dumps(result, indent=2))
    return 0 if result['release_accepted'] else 2


if __name__ == '__main__':
    sys.exit(main())
