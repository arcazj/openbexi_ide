"""Verify installed release members against the exact downloaded wheel bytes."""

import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import sysconfig
import zipfile

root = Path('/opt/qualification-inputs')
manifest = json.loads((root / 'published-pair.json').read_text())
site = Path(sysconfig.get_path('purelib'))
checked = {}
for name, digest in manifest['wheels'].items():
    path = root / 'wheels' / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    count = 0
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            if entry.is_dir() or entry.filename.endswith('/RECORD'):
                continue
            assert not entry.filename.startswith('/') and '..' not in Path(entry.filename).parts
            actual = site / entry.filename
            assert actual.is_file() and actual.read_bytes() == archive.read(entry), entry.filename
            count += 1
    checked[name] = count
result = {
    'passed': True,
    'wheel_members': checked,
    'versions': {name: metadata.version(name) for name in (
        'openbexi-ide', 'openbexi-spell-host', 'openbexi-spell-server',
        'openbexi-spell-dss', 'openbexi-spell-shared', 'PySide6-Essentials',
        'debugpy', 'Pygments', 'grpcio', 'protobuf', 'typing_extensions',
    )},
    'scope': manifest['scope'],
    'full_v08_qualified': False,
}
(root / 'installed-byte-verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
