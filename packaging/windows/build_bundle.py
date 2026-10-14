"""Build a deterministic offline Windows bundle from pinned runtime and wheels.

This never imports the application or uses packages installed on the build host.
The output directory must be new. Version is read from the supplied IDE wheel.
"""
import argparse
import base64
import csv
from email.parser import BytesParser
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import py_compile
import shutil
import sys
import tarfile
import tomllib
import urllib.request
import zipfile


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STAMP = (2026, 1, 1, 0, 0, 0)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(p in ('.', '..') or ':' in p or '\\' in p for p in path.parts):
        raise ValueError(f'Unsafe archive path: {name!r}')
    return path


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def runtime_archive(cache, lock):
    archive = cache / 'cpython-3.13.15-windows-x64.tar.gz'
    cache.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        temporary = archive.with_suffix('.download')
        with urllib.request.urlopen(lock['url'], timeout=120) as response, temporary.open('wb') as output:
            shutil.copyfileobj(response, output)
        if sha(temporary.read_bytes()) != lock['sha256']:
            raise ValueError('Downloaded runtime hash mismatch; retained .download for inspection')
        temporary.replace(archive)
    if archive.stat().st_size != lock['size'] or sha(archive.read_bytes()) != lock['sha256']:
        raise ValueError('Runtime does not match runtime.lock.json')
    return archive


def put(root, relative, data):
    destination = root.joinpath(*safe_name(relative).parts)
    if destination.exists():
        raise ValueError(f'Overlapping package file: {relative}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)


def unpack_runtime(archive, payload):
    with tarfile.open(archive, 'r:gz') as source:
        for member in source:
            name = safe_name(member.name)
            if name.parts[0] != 'python':
                raise ValueError(f'Unexpected runtime prefix: {member.name}')
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f'Nonregular runtime member: {member.name}')
            relative = PurePosixPath(*name.parts[1:])
            # Generated scripts have installation-specific shebangs. Use python -m pip.
            if relative.parts[0].lower() == 'scripts' or '__pycache__' in relative.parts or relative.suffix == '.pyc':
                continue
            put(payload, 'runtime/' + relative.as_posix(), source.extractfile(member).read())


def unpack_wheel(wheel, payload):
    with zipfile.ZipFile(wheel) as source:
        names = source.namelist()
        metadata_name, = [name for name in names if name.endswith('.dist-info/METADATA')]
        record_name, = [name for name in names if name.endswith('.dist-info/RECORD')]
        metadata = BytesParser().parsebytes(source.read(metadata_name))
        records = {row[0]: row[1:] for row in csv.reader(io.StringIO(source.read(record_name).decode()))}
        if len(set(names)) != len(names):
            raise ValueError('Duplicate wheel archive paths')
        for name in names:
            safe_name(name)
            if name.endswith('/'):
                continue
            data = source.read(name)
            digest, size = records[name]
            if name != record_name:
                expected = 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
                if digest != expected or int(size) != len(data):
                    raise ValueError(f'Invalid wheel RECORD: {name}')
            parts = PurePosixPath(name).parts
            if parts[0].endswith('.data'):
                if parts[1] not in ('purelib', 'platlib'):
                    raise ValueError(f'Unsupported wheel data category: {name}')
                name = PurePosixPath(*parts[2:]).as_posix()
            put(payload, 'runtime/Lib/site-packages/' + name, data)
    return {'filename': wheel.name, 'name': metadata['Name'], 'version': metadata['Version'], 'sha256': sha(wheel.read_bytes())}


def source_snapshot(root, wheel, version, payload):
    if tomllib.loads((root / 'pyproject.toml').read_text())['project']['version'] != version:
        raise ValueError('Source snapshot and IDE wheel versions differ')
    with zipfile.ZipFile(wheel) as distribution:
        for name in distribution.namelist():
            if name.endswith('.py') and '.dist-info/' not in name:
                source = root / 'src' / name
                if not source.is_file() or source.read_bytes() != distribution.read(name):
                    raise ValueError(f'Source snapshot does not match wheel: {name}')
    allowed = {'src', 'examples', 'tests', 'scripts', 'docs', 'packaging'}
    top_files = {'pyproject.toml', 'LICENSE', 'NOTICE', 'README.md', 'ROADMAP.md',
                 'build-requirements.lock', 'requirements-windows-cp313.lock', 'test-requirements.lock'}
    files = {}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source in sorted(root.rglob('*')):
            relative = source.relative_to(root)
            if relative.parts[0] not in allowed and relative.as_posix() not in top_files:
                continue
            if '__pycache__' in relative.parts or any(part.endswith('.egg-info') for part in relative.parts):
                continue
            if source.is_symlink():
                raise ValueError('Source snapshot must not contain symlinks')
            if not source.is_file() or source.suffix == '.pyc':
                continue
            data = source.read_bytes()
            files[relative.as_posix()] = sha(data)
            entry = zipfile.ZipInfo(relative.as_posix(), STAMP)
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data, compresslevel=9)
    put(payload, 'source/openbexi-ide-source.zip', buffer.getvalue())
    return files


def native_path(path):
    value = str(path.resolve())
    if os.name != 'nt' or value.startswith('\\\\?\\'):
        return value
    return ('\\\\?\\UNC\\' + value[2:] if value.startswith('\\\\')
            else '\\\\?\\' + value)


def bytecode(payload):
    # Checked hashes and relative co_filename values make bytes independent of
    # output directory/mtime. Importlib fixes co_filename to the actual source
    # location when loading them, preserving debugger/traceback source paths.
    if sys.implementation.name != 'cpython' or sys.version_info[:3] != (3, 13, 15):
        raise ValueError('Build with exact CPython 3.13.15 for deterministic bundled bytecode')
    count = 0
    # The Tcl/Tix resource tree contains legacy Python 2 utility data that is
    # not importable CPython 3 code. Compile the actual import path and examples.
    for tree in (payload / 'runtime/Lib', payload / 'examples'):
        for source in sorted(tree.rglob('*.py')):
            compiled = Path(importlib.util.cache_from_source(str(source), optimization=''))
            # py_compile adds an atomic-write suffix to the cache name. Even
            # when source paths fit MAX_PATH, that temporary name may not.
            py_compile.compile(native_path(source), cfile=native_path(compiled), dfile=source.relative_to(payload).as_posix(),
                               doraise=True, optimize=0, invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH)
            count += 1
    return {'implementation': 'CPython', 'version': '3.13.15', 'optimization': 0,
            'invalidation': 'checked-hash', 'co_filename': 'relative payload path', 'files': count,
            'scope': ['runtime/Lib', 'examples']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ide-wheel', type=Path, required=True)
    parser.add_argument('--wheels', type=Path, required=True, help='Directory containing the four locked Windows dependency wheels')
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--examples', type=Path, help='Immutable release source snapshot examples directory')
    parser.add_argument('--source-snapshot', type=Path, help='Immutable source snapshot matching every Python file in the IDE wheel')
    args = parser.parse_args()
    recipes = {p.name: sha(p.read_bytes()) for p in sorted(HERE.iterdir()) if p.is_file()}
    lock = json.loads((HERE / 'runtime.lock.json').read_text())
    archive = runtime_archive(args.cache.resolve(), lock)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    bundle = Path(native_path(output / 'bundle'))
    payload = bundle / 'payload'
    payload.mkdir(parents=True)
    unpack_runtime(archive, payload)
    requirements = (REPO / 'requirements-windows-cp313.lock').read_text()
    expected_hashes = set(re.findall(r'--hash=sha256:([a-f0-9]{64})', requirements))
    dependencies = [p for p in args.wheels.glob('*.whl') if sha(p.read_bytes()) in expected_hashes]
    if len(dependencies) != len(expected_hashes) or {sha(p.read_bytes()) for p in dependencies} != expected_hashes:
        raise ValueError('Missing or duplicate dependency wheels from requirements-windows-cp313.lock')
    packages = [unpack_wheel(path, payload) for path in sorted(dependencies) + [args.ide_wheel]]
    ide = packages[-1]
    if ide['name'].replace('_', '-').lower() != 'openbexi-ide' or not re.fullmatch(r'[0-9A-Za-z.+-]+', ide['version']):
        raise ValueError('Expected an openbexi-ide wheel with a safe version')
    sources = source_snapshot(args.source_snapshot.resolve(), args.ide_wheel, ide['version'], payload) if args.source_snapshot else {}
    # A historical IDE source snapshot can predate these distribution recipes.
    # Ship their exact bytes separately so the recorded hashes remain rebuildable.
    for name in recipes:
        put(payload, 'source/distribution/packaging/windows/' + name, (HERE / name).read_bytes())
    examples = {}
    if args.examples:
        example_root = args.examples.resolve()
        for path in sorted(example_root.rglob('*')):
            if path.is_symlink():
                raise ValueError('Example inputs must not contain symlinks')
            if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
                continue
            name = path.relative_to(example_root).as_posix()
            data = path.read_bytes()
            put(payload, 'examples/' + name, data)
            examples[name] = sha(data)
        if not examples:
            raise ValueError('Empty example snapshot')
    compiled = bytecode(payload)
    provenance = {'runtime': lock, 'packages': packages, 'requirements_sha256': sha(requirements.encode()),
                  'examples': examples,
                  'sources': sources,
                  'bytecode': compiled,
                  'licenses': {p.relative_to(payload).as_posix(): sha(p.read_bytes()) for p in sorted(payload.rglob('*'))
                               if p.is_file() and any(word in p.name.lower() for word in ('license', 'copying', 'notice'))},
                  'recipes': recipes,
                  'archive_timestamp': STAMP, 'format': 1}
    put(payload, 'provenance.json', json_bytes(provenance))
    files = {p.relative_to(payload).as_posix(): sha(p.read_bytes()) for p in sorted(payload.rglob('*')) if p.is_file()}
    manifest = {'product': 'OpenBEXI IDE', 'format': 1, 'version': ide['version'], 'files': files}
    manifest['payload_id'] = sha(json_bytes(manifest))
    (bundle / 'package.json').write_bytes(json_bytes(manifest))
    for name in ('install.ps1', 'uninstall.ps1', 'launch.ps1', 'common.ps1', 'Install.cmd', 'README.txt'):
        shutil.copyfile(HERE / name, bundle / name)
    artifact = output / f'OpenBEXI-IDE-{ide["version"]}-windows-x64.zip'
    with zipfile.ZipFile(artifact, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():
                entry = zipfile.ZipInfo(path.relative_to(bundle).as_posix(), STAMP)
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                target.writestr(entry, path.read_bytes(), compresslevel=9)
    result = {'artifact': str(artifact), 'sha256': sha(artifact.read_bytes()), 'payload_id': manifest['payload_id'],
              'version': ide['version'], 'files': len(files), 'provenance': provenance, 'release_accepted': False}
    if recipes != {p.name: sha(p.read_bytes()) for p in sorted(HERE.iterdir()) if p.is_file()}:
        raise ValueError('Packaging recipes changed while building; do not promote this artifact')
    (output / 'build.json').write_bytes(json_bytes(result))
    print(json.dumps({key: value for key, value in result.items() if key != 'provenance'}, indent=2))


if __name__ == '__main__':
    main()
