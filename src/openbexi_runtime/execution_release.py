"""Offline release preparation and authority for the network-disabled Python profile.

The operator's OS account and Docker daemon are trusted. Session clients cannot
prepare, approve, replace or revoke releases. Source and runtime are image-bound.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import time
import tokenize
import uuid

from .procedure_identity import definition_id, version_id
from .session_identity import unique_object
from .session_store import canonical

PROFILE = 'python-docker-offline/1'
PLUGIN_PROFILE = 'plugin-docker-isolated/1'
SCHEMA = 'openbexi.execution-release/1'
IMAGE = re.compile(r'sha256:[0-9a-f]{64}')
RUNTIME_PROBE = '''import hashlib, importlib.metadata as m, json, platform, sys
from pathlib import Path
print(json.dumps(dict(implementation=platform.python_implementation(),
 version=list(sys.version_info[:3]), executable_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
 packages=sorted([dict(name=d.metadata['Name'], version=d.version) for d in m.distributions()], key=lambda x:x['name']))))
'''


def docker(*args, timeout=30, **kwargs):
    result = subprocess.run(['docker', *map(str, args)], capture_output=True, timeout=timeout, **kwargs)
    if result.returncode:
        raise ValueError('Docker operation failed: ' + result.stderr.decode(errors='replace')[-2000:])
    return result.stdout


def image_info(identity):
    if not isinstance(identity, str) or IMAGE.fullmatch(identity) is None:
        raise ValueError('Execution requires a full immutable Docker image ID')
    info = json.loads(docker('image', 'inspect', identity))[0]
    if info['Id'] != identity or info['Os'] != 'linux' or info['Architecture'] != 'amd64':
        raise ValueError('Execution requires the exact Linux amd64 runtime image')
    if info['Config'].get('Volumes'):
        raise ValueError('Execution runtime images cannot declare writable volumes')
    return info


def isolation_options():
    return ['--network=none', '--read-only', '--user=65532:65532', '--cap-drop=ALL',
            '--security-opt=no-new-privileges:true', '--pids-limit=64', '--memory=256m',
            '--memory-swap=256m', '--cpus=1', '--init', '--log-driver=none',
            '--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16777216,mode=1777',
            '--workdir=/tmp', '--env=HOME=/tmp', '--env=PYTHONDONTWRITEBYTECODE=1']


def probe_image(image, code, *arguments):
    """Own probes explicitly, including timeout and invalid runtime failures."""
    identity = uuid.uuid4().hex
    name = 'openbexi-release-probe-' + identity
    try:
        return json.loads(docker('run', '--rm', '--name', name, '--label', 'org.openbexi.probe=' + identity,
                                 *isolation_options(), '--entrypoint=python', image, '-I', '-B', '-c', code, *arguments))
    finally:
        remaining = docker('ps', '-a', '--filter', 'name=^/' + name + '$', '--format', '{{.ID}}', timeout=5)
        if remaining.strip():
            info = json.loads(docker('inspect', name, timeout=5))[0]
            if (info['Config'].get('Labels') or {}).get('org.openbexi.probe') != identity:
                raise ValueError('Release probe ownership differs')
            docker('rm', '--force', info['Id'], timeout=5)


def prepare(project, script, runtime_image, output, *, additional_procedures=(), backend=None):
    from .source_capture import capture
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    base = image_info(runtime_image)
    binding = None
    if backend:
        from .shared_backends import bind_backend
        binding = bind_backend(backend)
        if binding.get('image') != runtime_image:
            raise ValueError('Provider binding differs from the reviewed runtime image')
    source, source_digest, inventory = capture(project, script, output)
    context = output / 'context'
    context.mkdir()
    shutil.copytree(source, context / 'project')
    # Include only this neutral runtime, never an operator workspace or secrets.
    shutil.copytree(Path(__file__).parent, context / 'runtime' / 'openbexi_runtime',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    # BuildKit treats a bare sha256 ID in FROM as a registry repository name.
    # Give the verified local image a content-named tag, then check ancestry.
    base_tag = 'openbexi-execution-base:' + runtime_image.removeprefix('sha256:')
    docker('tag', runtime_image, base_tag)
    recipe = ('FROM ' + base_tag + '\n'
              'COPY --chmod=0555 project /release\n'
              'COPY --chmod=0555 runtime /opt/openbexi-runtime\n'
              'ENTRYPOINT []\nCMD []\n')
    (context / 'Dockerfile').write_text(recipe, encoding='utf-8')
    docker('build', '--network=none', '--iidfile', output / 'image.id', context, timeout=300)
    image = (output / 'image.id').read_text().strip()
    built = image_info(image)
    layers = base['RootFS']['Layers']
    if built['RootFS']['Layers'][:len(layers)] != layers:
        raise ValueError('Release image does not inherit the approved base layers')
    runtime = probe_image(image, RUNTIME_PROBE)
    if runtime['implementation'] != 'CPython' or runtime['version'][:2] != [3, 13]:
        raise ValueError('Execution requires CPython 3.13')
    procedures = {}
    for name in (script, *additional_procedures):
        if name not in inventory['files'] or not name.endswith('.py'):
            raise ValueError('Released procedures must be committed Python files')
        with tokenize.open(source / name) as stream:
            definition = definition_id(name, stream.read())
        procedures[name] = {'definition': definition,
                            'version': version_id(definition, inventory['files'][name]['sha256'], image, source_digest)}
    manifest = {'schema': SCHEMA, 'profile': PROFILE, 'image': image, 'base_image': base['Id'],
                'source_digest': source_digest, 'source': inventory, 'runtime': runtime,
                'procedures': procedures}
    if backend:
        manifest.update(profile=PLUGIN_PROFILE,backend=dict(provider=backend,binding=binding))
        from .shared_backends import load_backend
        load_backend(backend).for_release(manifest)
    release = digest(manifest)
    (output / 'release.json').write_text(canonical(manifest) + '\n', encoding='utf-8')
    return {'release': release, 'manifest': str(output / 'release.json'), 'image': image,
            'approved': False}


def digest(manifest):
    return hashlib.sha256(canonical(manifest).encode()).hexdigest()


def validate(manifest):
    plugin = type(manifest) is dict and manifest.get('profile') == PLUGIN_PROFILE
    keys = {'schema', 'profile', 'image', 'base_image','source_digest','source','runtime','procedures'}
    if plugin:
        keys.add('backend')
    if (type(manifest) is not dict or set(manifest) != keys
            or manifest['schema'] != SCHEMA or manifest['profile'] not in {PROFILE,PLUGIN_PROFILE}):
        raise ValueError('Unsupported execution release manifest')
    if plugin:
        backend = manifest['backend']
        if (type(backend) is not dict or set(backend) != {'provider','binding'}
                or type(backend['provider']) is not str or re.fullmatch('[a-z][a-z0-9_-]{0,63}',backend['provider']) is None
                or type(backend['binding']) is not dict or len(canonical(backend)) > 8192
                or backend['binding'].get('image') != manifest['base_image']):
            raise ValueError('Invalid immutable provider binding')
    for field in ('image', 'base_image'):
        if not isinstance(manifest[field], str) or IMAGE.fullmatch(manifest[field]) is None:
            raise ValueError('Release runtime image identity is invalid')
    source = manifest['source']
    if (type(source) is not dict or set(source) != {'schema', 'git_commit', 'git_tree', 'files'}
            or source['schema'] != 'openbexi.source-capture/1' or digest(source) != manifest['source_digest']):
        raise ValueError('Release source inventory identity differs')
    if any(not isinstance(source[k], str) or re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', source[k]) is None
           for k in ('git_commit', 'git_tree')):
        raise ValueError('Invalid release Git provenance')
    if type(source['files']) is not dict or not 1 <= len(source['files']) <= 4096:
        raise ValueError('Invalid release file inventory')
    names = set()
    for name, row in source['files'].items():
        path = PurePosixPath(name)
        if (not name or str(path) != name or path.is_absolute() or '..' in path.parts
                or '\\' in name or ':' in name or name.casefold() in names
                or type(row) is not dict or set(row) != {'sha256', 'git_blob', 'mode'}
                or row['mode'] not in {'100644', '100755'}
                or not isinstance(row['sha256'], str) or re.fullmatch('[0-9a-f]{64}', row['sha256']) is None
                or not isinstance(row['git_blob'], str) or re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', row['git_blob']) is None):
            raise ValueError('Invalid release file path or content identity')
        names.add(name.casefold())
    if type(manifest['procedures']) is not dict or not 1 <= len(manifest['procedures']) <= 128:
        raise ValueError('Release requires 1..128 explicit procedures')
    for script, row in manifest['procedures'].items():
        if (not isinstance(script, str) or script not in source.get('files', {})
                or not script.endswith('.py') or script.startswith('/') or '\\' in script or ':' in script
                or any(p in {'', '.', '..'} for p in script.split('/'))
                or type(row) is not dict or set(row) != {'definition', 'version'}):
            raise ValueError('Invalid released procedure path or identity')
        expected = version_id(row['definition'], source['files'][script]['sha256'],
                              manifest['image'], manifest['source_digest'])
        if expected != row['version']:
            raise ValueError('Release procedure version identity differs')
    if (type(manifest['runtime']) is not dict or manifest['runtime'].get('implementation') != 'CPython'
            or manifest['runtime'].get('version', [])[:2] != [3, 13]):
        raise ValueError('Release runtime requires CPython 3.13')
    return manifest


def read_manifest(path):
    path = Path(path)
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Release manifest exceeds its bound')
    return validate(json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_object))


def verify_image(manifest):
    """Recheck the image's actual source and interpreter before approving it."""
    image_info(manifest['image'])
    if manifest['profile'] == PLUGIN_PROFILE:
        from .shared_backends import load_backend
        load_backend(manifest['backend']['provider']).for_release(manifest)
    probe = '''import hashlib, json, sys, tokenize
from pathlib import Path
root=Path('/release')
files={}
total=0
for p in root.rglob('*'):
 if p.is_symlink(): raise ValueError('Release contains a link')
 if p.is_file():
  size=p.stat().st_size; total+=size
  if size>8*1024*1024 or total>64*1024*1024 or len(files)>=4096: raise ValueError('Release exceeds source bounds')
  files[p.relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
sources={}
for script in sys.argv[1:]:
 with tokenize.open(root / script) as f: sources[script]=f.read()
print(json.dumps(dict(files=files, sources=sources)))
'''
    actual = probe_image(manifest['image'], probe, *manifest['procedures'])
    if actual['files'] != {name: row['sha256'] for name, row in manifest['source']['files'].items()}:
        raise ValueError('Runtime image source differs from the release manifest')
    for script, row in manifest['procedures'].items():
        if definition_id(script, actual['sources'][script]) != row['definition']:
            raise ValueError('Runtime image procedure definition differs from the release manifest')
    runtime = probe_image(manifest['image'], RUNTIME_PROBE)
    if runtime != manifest['runtime']:
        raise ValueError('Runtime provenance differs from the release manifest')


class ReleaseAuthority:
    def __init__(self, store):
        self.store = store
        store.db.executescript('''
            CREATE TABLE IF NOT EXISTS releases (
                id TEXT PRIMARY KEY, manifest TEXT NOT NULL, approved INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS release_audit (
                sequence INTEGER PRIMARY KEY, value TEXT NOT NULL);
        ''')

    def decide(self, manifest, *, approved, actor, evidence):
        validate(manifest)
        if type(approved) is not bool or len(canonical(manifest).encode()) > 2 * 1024 * 1024:
            raise ValueError('Invalid release decision or oversized manifest')
        if any(not isinstance(s, str) or not s.strip() or len(s) > 2000 for s in (actor, evidence)):
            raise ValueError('Release decision requires an actor and retained review evidence')
        if approved:
            verify_image(manifest)
        release = digest(manifest)
        with self.store.db:
            count = self.store.db.execute('SELECT COUNT(*) FROM release_audit').fetchone()[0]
            if count >= 10000:
                raise ValueError('Release audit capacity reached')
            exists = self.store.db.execute('SELECT 1 FROM releases WHERE id=?', (release,)).fetchone()
            count, size = self.store.db.execute('SELECT COUNT(*),COALESCE(SUM(LENGTH(manifest)),0) FROM releases').fetchone()
            if not exists and (count >= 128 or size + len(canonical(manifest)) > 64 * 1024 * 1024):
                raise ValueError('Release catalog capacity reached')
            self.store.db.execute('INSERT INTO releases VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET approved=excluded.approved',
                                  (release, canonical(manifest), int(approved)))
            self.store.db.execute('INSERT INTO release_audit(value) VALUES (?)', (canonical({
                'release': release, 'approved': approved, 'actor': actor, 'evidence': evidence, 'time': time.time()}),))
        return {'release': release, 'approved': approved}

    def require(self, release):
        row = self.store.db.execute('SELECT manifest,approved FROM releases WHERE id=?', (release,)).fetchone()
        if row is None or not row[1]:
            raise ValueError('Execution release is not approved or has been revoked')
        manifest = validate(json.loads(row[0], object_pairs_hook=unique_object))
        if digest(manifest) != release:
            raise ValueError('Approved release identity differs')
        return manifest
