"""Bind matching bundle bytes and a complete installed lifecycle to a report."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference(path):
    path = path.resolve()
    return {'path': path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path), 'sha256': sha(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-a', type=Path, required=True)
    parser.add_argument('--build-b', type=Path, required=True)
    parser.add_argument('--lifecycle', type=Path, required=True)
    parser.add_argument('--installer-checks', type=Path, required=True)
    parser.add_argument('--extraction', type=Path, help='Actual Windows tar extraction evidence directory')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    builds = []
    for directory in (args.build_a, args.build_b):
        build = json.loads((directory / 'build.json').read_text())
        artifact = directory / Path(build['artifact']).name
        assert sha(artifact) == build['sha256']
        manifest_path = directory / 'bundle/package.json'
        manifest = json.loads(manifest_path.read_text())
        assert manifest['payload_id'] == build['payload_id']
        with zipfile.ZipFile(artifact) as archive:
            assert archive.read('package.json') == manifest_path.read_bytes()
            for name, expected in manifest['files'].items():
                assert hashlib.sha256(archive.read('payload/' + name)).hexdigest() == expected, name
        builds.append({'build': reference(directory / 'build.json'), 'artifact': reference(artifact),
                       'manifest': reference(manifest_path), 'version': build['version'], 'payload_id': build['payload_id'],
                       'provenance': build['provenance']})
    assert builds[0]['artifact']['sha256'] == builds[1]['artifact']['sha256']
    assert builds[0]['payload_id'] == builds[1]['payload_id']
    lifecycle_path = args.lifecycle / 'result.json'
    lifecycle = json.loads(lifecycle_path.read_text())
    assert lifecycle['passed'] and lifecycle['version'] == builds[0]['version']
    assert lifecycle['bundle_manifest_sha256'] == builds[0]['manifest']['sha256']
    for name, digest in lifecycle.get('retained_harnesses', {}).items():
        assert Path(name).name == name
        assert sha(args.lifecycle/'harnesses'/name) == digest
    desktop_path = args.lifecycle / 'desktop/result.json'
    assert sha(desktop_path) == lifecycle['desktop_sha256']
    if 'shared_debug_sha256' in lifecycle:
        assert sha(args.lifecycle/'shared-debug/result.json') == lifecycle['shared_debug_sha256']
    if 'menu_sha256' in lifecycle:
        assert sha(args.lifecycle/'menu/result.json') == lifecycle['menu_sha256']
    if 'spell' in lifecycle:
        spell_path = args.lifecycle / lifecycle['spell']['result']
        assert sha(spell_path) == lifecycle['spell']['result_sha256']
    checks_path = args.installer_checks / 'result.json'
    checks = json.loads(checks_path.read_text())
    assert checks['passed']
    for name, digest in checks['recipes'].items():
        assert digest == builds[0]['provenance']['recipes'][name], name
    report = {'format': 1, 'product': 'OpenBEXI IDE', 'version': builds[0]['version'],
              'distribution_prerequisites_passed': True, 'release_accepted': False,
              'builds': builds, 'lifecycle': reference(lifecycle_path), 'installer_checks': reference(checks_path),
              'checks': lifecycle['checks'] + checks['checks'],
              'scope': lifecycle['scope'],
              'remaining': ['Earlier IDE milestone live noVNC acceptance', 'Fresh Windows VM qualification',
                            'Final release version/source/installer qualification; this report never promotes a release'],
              'recorder_sha256': sha(Path(__file__))}
    if args.extraction:
        path = args.extraction / 'extraction.json'
        extraction = json.loads(path.read_text())
        assert extraction['passed'] and extraction['artifact_sha256'] == builds[0]['artifact']['sha256']
        assert extraction['package_manifest_sha256'] == builds[0]['manifest']['sha256']
        report['extraction'] = reference(path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'output': str(args.output), 'sha256': sha(args.output), 'version': report['version'],
                      'distribution_prerequisites_passed': True, 'release_accepted': False}, indent=2))


if __name__ == '__main__':
    main()
