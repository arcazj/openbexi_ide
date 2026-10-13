"""Verify a release ZIP and extract it with Windows' built-in tar.exe."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import zipfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    assert sha(artifact) == args.sha256, 'Release ZIP hash mismatch'
    with zipfile.ZipFile(artifact) as archive:
        names = set()
        for entry in archive.infolist():
            name = PurePosixPath(entry.filename)
            assert not name.is_absolute() and name.parts and '..' not in name.parts
            assert ':' not in entry.filename and '\\' not in entry.filename
            assert entry.filename.casefold() not in names and not stat.S_ISLNK(entry.external_attr >> 16)
            names.add(entry.filename.casefold())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    bundle = output / 'bundle with spaces'
    bundle.mkdir()
    tar = Path(os.environ['SYSTEMROOT']) / 'System32/tar.exe'
    version = subprocess.check_output([str(tar), '--version'], text=True).strip()
    subprocess.run([str(tar), '-xf', str(artifact), '-C', str(bundle)], check=True)
    manifest = json.loads((bundle / 'package.json').read_text())
    for name, expected in manifest['files'].items():
        assert sha(bundle / 'payload' / name) == expected, name
    report = {'passed': True, 'artifact_sha256': args.sha256, 'package_manifest_sha256': sha(bundle / 'package.json'),
              'bundle': str(bundle), 'tar_version': version, 'tar_sha256': sha(tar),
              'files_verified': len(manifest['files']), 'version': manifest['version']}
    (output / 'extraction.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
