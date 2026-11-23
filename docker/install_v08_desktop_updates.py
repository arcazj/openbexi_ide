"""Apply digest-pinned offline runtime updates to the Debian qualification image."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

inputs = Path('/opt/qualification-inputs')
manifest = json.loads((inputs / 'published-pair.json').read_bytes())
pins = manifest.get('desktop_updates')
if pins is None:
    sys.exit(0)


def verified_files(directory, digests):
    files = {}
    for name, expected in digests.items():
        path = inputs / 'updates' / directory / name
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise ValueError('Desktop runtime input differs: ' + name)
        files[name] = str(path)
    return files


debs = verified_files('debs', pins['debian'])
wheels = verified_files('wheels', {name: row['sha256'] for name, row in pins['python'].items()})
environment = {**os.environ, 'DEBIAN_FRONTEND': 'noninteractive'}
apt = ['apt-get', '-y', '--no-install-recommends']
subprocess.run([*apt, 'install', *debs.values()], env=environment, check=True)

# websockify serves static noVNC files. Preserve their Debian notice and
# content while removing the unused Node server and its bundled HTTP client.
static = Path('/usr/share/novnc')
notice = Path('/usr/share/doc/novnc/copyright')
with tempfile.TemporaryDirectory() as staging:
    saved = Path(staging)
    shutil.copytree(static, saved / 'assets', symlinks=True,
                    ignore=lambda directory, names: {'utils'} if Path(directory) == static else set())
    shutil.copy2(notice, saved / 'copyright')
    subprocess.run([*apt, 'purge', 'novnc', 'node-corepack', 'nodejs', 'libnode115',
                    'node-acorn', 'node-undici'], env=environment, check=True)
    shutil.copytree(saved / 'assets', static, dirs_exist_ok=True, symlinks=True)
    notice.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(saved / 'copyright', notice)

for executable in (sys.executable, '/opt/spell-native/bin/python'):
    pip = [executable, '-I', '-m', 'pip']
    installed = {p['name'].lower() for p in json.loads(subprocess.check_output(
        [*pip, 'list', '--format=json', '--disable-pip-version-check'], text=True))}
    upgrades = [wheels[n] for n, item in pins['python'].items() if item['package'].lower() in installed]
    if upgrades:
        subprocess.run([*pip, 'install', '--no-index', '--no-deps', *upgrades], check=True)
    subprocess.run([*pip, 'check'], check=True)
shutil.rmtree(inputs / 'updates')
