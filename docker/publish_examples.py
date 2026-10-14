"""Add a versioned example folder without replacing a user's project files."""
import hashlib
from pathlib import Path
import shutil
import tempfile

NATIVE_ONLY_TEST_SPELL = '2009d8e2f5ef2f45aea85ccde8958ee4f4c5303ac1dbcb8b781d05e6268d3323'


def publish(source=Path('/opt/openbexi/examples'), projects=Path('/workspace/projects')):
    files = sorted(p for p in source.rglob('*') if p.is_file() and p.suffix in {'.py', '.md', '.json'}
                   and '__pycache__' not in p.parts)
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(source).as_posix().encode() + b'\0' + path.read_bytes())
    name = 'examples-' + digest.hexdigest()[:12]
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
            target = staging / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        staging.rename(destination)
        destinations.append(destination)
    return destinations


def refresh_spell(source=Path('/opt/openbexi/examples'), projects=Path('/workspace/projects')):
    """Refresh the known shipped smoke example, preserving edited files and backups."""
    destinations = publish(source, projects)
    result = []
    script = source/'test_spell/test_spell.py'
    replacement = (script if script.is_file() else source/'test_spell.py').read_bytes()
    for destination in destinations:
        target = destination.parent/'test_spell.py'
        if target.is_symlink():
            result.append(dict(path=str(target), status='preserved-symlink'))
            continue
        if target.exists():
            original = target.read_bytes()
            if original == replacement:
                result.append(dict(path=str(target), status='current'))
                continue
            if hashlib.sha256(original).hexdigest() != NATIVE_ONLY_TEST_SPELL:
                result.append(dict(path=str(target), status='preserved-edited-file'))
                continue
            backup = target.parent/('.test_spell-original-'+NATIVE_ONLY_TEST_SPELL[:12]+'.py')
            if backup.exists():
                if backup.is_symlink() or backup.read_bytes() != original:
                    raise ValueError('Existing example backup differs: '+str(backup))
            else:
                with backup.open('xb') as stream:
                    stream.write(original)
            target.write_bytes(replacement)
            status = 'refreshed-shipped-file'
        else:
            with target.open('xb') as stream:
                stream.write(replacement)
            status = 'added'
        result.append(dict(path=str(target), status=status))
    return dict(folders=list(map(str,destinations)), files=result)


if __name__ == '__main__':
    for destination in publish():
        print(destination)
