"""Build a local test desktop from immutable IDE 1.2.1 / SPELL rc1 wheels.

Supply directories containing the release wheels and the three dependency
wheels listed in docker/v08-qualification-inputs.json. The build is offline.
It retains the v0.7 native runtime; v0.8 authority/native acceptance is separate.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tag', default='openbexi-ide-spell-v08-qualification:1.2.1-rc1-clean')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    context = output / 'context'
    wheels = context / 'wheels'
    wheels.mkdir(parents=True)
    manifest_path = ROOT / 'docker/v08-qualification-inputs.json'
    manifest = json.loads(manifest_path.read_text())
    expected = dict(manifest['wheels'])
    expected.update({name: row['sha256'] for name, row in manifest['dependencies'].items()})
    report = dict(manifest, passed=False, tag=args.tag, build_inputs={})
    try:
        for name, digest in expected.items():
            candidates = [directory / name for directory in args.artifacts if (directory / name).is_file()]
            if not candidates:
                raise ValueError('Required wheel is missing: ' + name)
            if any(sha(path) != digest for path in candidates):
                raise ValueError('Wheel checksum differs: ' + name)
            shutil.copy2(candidates[0], wheels / name)
        actual = subprocess.check_output(
            ['docker', 'image', 'inspect', manifest['base_image'], '--format', '{{.Id}}'], text=True
        ).strip()
        if actual != manifest['base_image']:
            raise ValueError('Desktop base image identity differs')
        alias = 'openbexi-local-qualification-base:' + actual.removeprefix('sha256:')
        subprocess.run(['docker', 'tag', actual, alias], check=True)
        archive_path = output / 'published-ide.tar'
        subprocess.run(
            ['git', 'archive', '--format=tar', '--output=' + str(archive_path), manifest['ide_commit']],
            cwd=ROOT, check=True,
        )
        with tarfile.open(archive_path) as archive:
            archive.extractall(context / 'ide', filter='data')
        for source, destination in (
            (manifest_path, context / 'published-pair.json'),
            (ROOT / 'docker/verify_release_wheels.py', context / 'verify_installed.py'),
            (ROOT / 'docker/v08-qualification.Dockerfile', context / 'Dockerfile'),
        ):
            shutil.copy2(source, destination)
            report['build_inputs'][source.relative_to(ROOT).as_posix()] = sha(source)
        command = [
            'docker', 'build', '--network=none', '--pull=false', '--progress=plain',
            '--build-arg', 'DESKTOP_IMAGE=' + alias, '--tag', args.tag, str(context),
        ]
        with (output / 'build.log').open('wb') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        report['build_exit_code'] = result.returncode
        if result.returncode:
            raise RuntimeError('Desktop build failed; see build.log')
        report['image'] = subprocess.check_output(
            ['docker', 'image', 'inspect', args.tag, '--format', '{{.Id}}'], text=True
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
