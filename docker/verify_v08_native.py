"""Check the deployed native family, Python packages and dynamic linker paths."""
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import sysconfig

root = Path('/opt/qualification-inputs')
manifest = json.loads((root / 'published-pair.json').read_bytes())
home = Path('/opt/v08-native-home')
build_file = home / 'build.json'


def verify(path, expected):
    with path.open('rb') as stream:
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
    if value != expected:
        raise ValueError(f'{path} SHA-256 {value} differs from {expected}')
    return value


build_hash = verify(build_file, manifest['native']['build_sha256'])
build = json.loads(build_file.read_bytes())
if (build['native_build_profile'] != 'optimized' or build['sanitizer_enabled']
        or not build['native_prompt_hooks'] or not build['native_terminal_hooks']):
    raise ValueError('Incomplete shipped native profile')
artifacts = {
    'SPELL-Listener': 'candidate_listener_sha256', 'SPELL-Context': 'candidate_context_sha256',
    'SPELL-Executor': 'candidate_executor_sha256', 'spell-host-ipc': 'candidate_bridge_sha256',
    'libspell_executor313.so': 'candidate_shared_runtime_sha256',
}
hashes = {}
for name, key in artifacts.items():
    path = home / 'bin' / name
    hashes[name] = verify(path, build[key])
    deps = subprocess.check_output(['ldd', str(path)], text=True)
    if 'not found' in deps:
        raise ValueError('Unresolved dependencies for ' + name)
    if 'libspell_executor313.so =>' in deps and str(home / 'bin/libspell_executor313.so') not in deps:
        raise ValueError('Loaded a different native shared library for ' + name)
hashes['launch-listener.py'] = verify(home / 'launch-listener.py', build['listener_launcher_sha256'])
hashes['libSPELL_DTA_v3.py'] = verify(
    Path(sysconfig.get_path('purelib')) / 'libSPELL_DTA_v3.py', build['profile_dta_shim']['after'])
versions = {'openbexi-ide': '1.2.2', 'openbexi-spell-plugin': '0.1.0'}
versions.update({'openbexi-spell-' + part: '0.8.0' for part in ('dss', 'host', 'server', 'shared')})
for name, expected in versions.items():
    if version(name) != expected:
        raise ValueError('Installed package version differs for ' + name)
    wheel = f"{name.replace('-', '_')}-{expected}-py3-none-any.whl"
    if wheel not in manifest['wheels']:
        raise ValueError('Missing pinned product wheel ' + wheel)
receipt = dict(passed=True, profile='optimized', build_sha256=build_hash, files=hashes, versions=versions,
               ide_commit=manifest['ide_commit'], spell_commit=manifest['spell_commit'])
(root / 'native-verification.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
