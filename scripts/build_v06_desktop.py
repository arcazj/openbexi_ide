"""Build the Docker desktop offline from the accepted SPELL v0.6 artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
NATIVE = 'sha256:ef97426030ab9db06f573710ebbec56ff2486ed558697c058ce9d724c9036100'
DESKTOP = 'sha256:aaf3d19d5a98a39c8b82c477e3fbbd2bfafc57ef627f31c0c0202c0c37e60d1d'
HOST_SHA256 = '17b63183600cbfaad15bc4ed76d0d5651cc264368164aa8f825a377ccc38de33'
SDK_SHA256 = 'bffd26c8d08df391e8d1c51acbfbf581dbfb250a643130b18132f8987eabf869'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-wheel', type=Path, required=True)
    parser.add_argument('--sdk-wheel', type=Path, required=True)
    parser.add_argument('--tag', default='openbexi-ide:1.1.1-spell-v0.6')
    args = parser.parse_args()
    wheel = args.host_wheel.resolve(strict=True)
    assert wheel.name == 'openbexi_spell_host-0.6.0-py3-none-any.whl'
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == HOST_SHA256, 'Unqualified host wheel'
    sdk = args.sdk_wheel.resolve(strict=True)
    assert sdk.name == 'openbexi_spell_plugin-0.1.0-py3-none-any.whl'
    assert hashlib.sha256(sdk.read_bytes()).hexdigest() == SDK_SHA256, 'Unqualified simulator wheel'
    output = ROOT / '.qualification/spell-v06-desktop' / uuid.uuid4().hex
    artifacts = output / 'artifacts'; artifacts.mkdir(parents=True)
    shutil.copy2(wheel, artifacts / wheel.name)
    shutil.copy2(sdk, artifacts / sdk.name)
    report = dict(passed=False, tag=args.tag, native=NATIVE, desktop_base=DESKTOP,
                  host_sha256=HOST_SHA256, sdk_sha256=SDK_SHA256, sources={})
    try:
        for directory in ('src', 'tests', 'examples', 'docker', 'scripts'):
            for path in sorted((ROOT / directory).rglob('*')):
                if (path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc'
                        and path.name != 'spell_menu_results.json'):
                    report['sources'][path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        for name in ('pyproject.toml', 'README.md', 'LICENSE', 'NOTICE'):
            report['sources'][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name, identity in (('native', NATIVE), ('desktop', DESKTOP)):
            actual = subprocess.check_output(['docker', 'image', 'inspect', identity, '--format', '{{.Id}}'], text=True).strip()
            assert actual == identity
            subprocess.run(['docker', 'tag', identity, 'openbexi-v06-' + name + '-input:' + identity[7:]], check=True)
        command = ['docker', 'build', '--network=none', '--pull=false', '--progress=plain',
                   '-f', 'docker/v06-desktop.Dockerfile', '--build-context', 'v06_artifacts=' + str(artifacts),
                   '--build-arg', 'NATIVE_IMAGE=openbexi-v06-native-input:' + NATIVE[7:],
                   '--build-arg', 'DESKTOP_IMAGE=openbexi-v06-desktop-input:' + DESKTOP[7:],
                   '-t', args.tag, str(ROOT)]
        with (output / 'build.log').open('wb') as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        report['image'] = subprocess.check_output(['docker', 'image', 'inspect', args.tag, '--format', '{{.Id}}'], text=True).strip()
        report['passed'] = True
    finally:
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(dict(passed=report['passed'], output=str(output), image=report.get('image'))), flush=True)
    return not report['passed']


if __name__ == '__main__':
    raise SystemExit(main())
