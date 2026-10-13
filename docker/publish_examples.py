"""Add a versioned example folder without replacing a user's project files."""
import hashlib
from pathlib import Path
import shutil
import tempfile


def publish(source=Path('/opt/openbexi/examples'), projects=Path('/workspace/projects')):
    files = sorted(p for p in source.iterdir() if p.is_file() and p.suffix in {'.py', '.md'})
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode() + b'\0' + path.read_bytes())
    name = 'examples-v05-' + digest.hexdigest()[:12]
    destinations = []
    for project in ('demo', 'durable'):
        parent = projects / project
        if not parent.is_dir():
            continue
        destination = parent / name
        if destination.exists():
            # Never repair or replace an existing folder: it may contain edits.
            destinations.append(destination)
            continue
        staging = Path(tempfile.mkdtemp(prefix='.examples-preparing-', dir=parent))
        for path in files:
            shutil.copyfile(path, staging / path.name)
        staging.rename(destination)
        destinations.append(destination)
    return destinations


if __name__ == '__main__':
    for destination in publish():
        print(destination)
