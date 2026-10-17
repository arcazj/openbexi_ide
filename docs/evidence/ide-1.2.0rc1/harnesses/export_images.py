import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

work = Path(__file__).resolve().parent
root = work.parents[1]
assets = root / 'dist/1.2.0rc1'
report = {}
for tag, name in (
    ('openbexi-ide:1.2.0rc1', 'openbexi-ide-1.2.0rc1-linux-amd64.tar.gz'),
    ('openbexi-spell-host:0.3.1-dev3', 'openbexi-spell-host-0.3.1-dev3-linux-amd64.tar.gz'),
):
    identity = subprocess.check_output(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'], text=True).strip()
    destination = assets / name
    assert not destination.exists(), destination
    print('Exporting ' + tag, flush=True)
    with (work / (name + '.stderr')).open('wb') as log, destination.open('wb') as output:
        process = subprocess.Popen(['docker', 'save', tag], stdout=subprocess.PIPE, stderr=log)
        with gzip.GzipFile(filename='', mode='wb', fileobj=output, mtime=0, compresslevel=6) as compressed:
            shutil.copyfileobj(process.stdout, compressed, length=1024 * 1024)
        assert process.wait(timeout=120) == 0
    with destination.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    report[tag] = {'image': identity, 'artifact': name, 'sha256': digest, 'size': destination.stat().st_size}
    (work / 'docker-archives.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report[tag]), flush=True)
