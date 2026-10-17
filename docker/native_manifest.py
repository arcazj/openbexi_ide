"""Record installed native distributions, adapter and simulator file identities."""
import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


report = {'schema':1, 'python':sys.version, 'distributions':{}, 'files':{}}
for name in ('openbexi-spell-source','openbexi-spell-dss','grpcio','protobuf','cloudpickle'):
    package = distribution(name)
    files = {str(path):sha(Path(package.locate_file(path))) for path in package.files
             if str(path).endswith('/RECORD')}
    report['distributions'][name] = {'version':package.version, 'records':files}
for directory in (Path('/opt/host'), Path('/bridge'),
                  Path('/opt/spell-native/lib/python3.13/site-packages/dss')):
    for path in sorted(directory.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            report['files'][str(path)] = sha(path)
Path('/opt/spell-native/runtime-manifest.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
