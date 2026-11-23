"""Build the local qualification desktop from digest-pinned images and wheels.

Supply directories containing the release wheels and the three dependency
wheels listed in docker/v08-qualification-inputs.json. The build is offline.
The default manifest preserves the published rc1 baseline. A candidate manifest
also pins the optimized v0.8 native image and its in-image build.json.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_alias(identity):
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', identity):
        raise ValueError('Expected a Docker image config digest')
    actual = subprocess.check_output(
        ['docker', 'image', 'inspect', identity, '--format', '{{.Id}}'], text=True
    ).strip()
    if actual != identity:
        raise ValueError('Image identity differs: ' + identity)
    alias = 'openbexi-local-qualification-base:' + actual.removeprefix('sha256:')
    subprocess.run(['docker', 'tag', actual, alias], check=True)
    return alias


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'docker/v08-qualification-inputs.json')
    parser.add_argument('--tag')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    context = output / 'context'
    wheels = context / 'wheels'
    wheels.mkdir(parents=True)
    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text())
    native = manifest.get('native')
    tag = args.tag or ('openbexi-ide-spell-v08-qualification:' +
                       (manifest['spell_commit'][:12] if native else '1.2.1-rc1-clean'))
    expected = dict(manifest['wheels'])
    expected.update({name: row['sha256'] for name, row in manifest['dependencies'].items()})
    report = dict(manifest, passed=False, tag=tag, build_inputs={})
    try:
        for name, digest in expected.items():
            candidates = [directory / name for directory in args.artifacts if (directory / name).is_file()]
            if not candidates:
                raise ValueError('Required wheel is missing: ' + name)
            if any(sha(path) != digest for path in candidates):
                raise ValueError('Wheel checksum differs: ' + name)
            shutil.copy2(candidates[0], wheels / name)
        alias = image_alias(manifest['base_image'])
        archive_path = output / 'published-ide.tar'
        subprocess.run(
            ['git', 'archive', '--format=tar', '--output=' + str(archive_path), manifest['ide_commit']],
            cwd=ROOT, check=True,
        )
        with tarfile.open(archive_path) as archive:
            archive.extractall(context / 'ide', filter='data')
        dockerfile = 'v08-candidate.Dockerfile' if native else 'v08-qualification.Dockerfile'
        inputs = [
            (manifest_path, context / 'published-pair.json'),
            (ROOT / 'docker/verify_release_wheels.py', context / 'verify_installed.py'),
            (ROOT / 'docker' / dockerfile, context / 'Dockerfile'),
        ]
        native_args = []
        if native:
            if native['source_commit'] != manifest['spell_commit']:
                raise ValueError('Native build and SPELL package sources differ')
            native_args = ['--build-arg', 'NATIVE_IMAGE=' + image_alias(native['image'])]
            inputs += [(ROOT / 'docker' / name, context / name)
                       for name in ('verify_v08_native.py', 'v08_desktop.py')]
        for source, destination in inputs:
            shutil.copy2(source, destination)
            report['build_inputs'][destination.name] = sha(source)
        command = [
            'docker', 'build', '--network=none', '--pull=false', '--progress=plain',
            '--build-arg', 'DESKTOP_IMAGE=' + alias, *native_args, '--tag', tag, str(context),
        ]
        with (output / 'build.log').open('wb') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        report['build_exit_code'] = result.returncode
        if result.returncode:
            raise RuntimeError('Desktop build failed; see build.log')
        report['image'] = subprocess.check_output(
            ['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'], text=True
        ).strip()
        report['passed'] = True
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({key: report.get(key) for key in ('passed', 'image', 'error')}), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
