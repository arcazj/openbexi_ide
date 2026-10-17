"""Publish the learning collection, preserving edited files in explicit backups."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import uuid


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generated_digest(folder):
    """Recognize the old publisher's exact content-addressed folders."""
    value = hashlib.sha256()
    for path in sorted(folder.rglob('*')):
        if path.is_symlink():
            return None
        if not path.is_file():
            continue
        if path.suffix not in {'.py', '.md', '.json'} or '__pycache__' in path.parts:
            return None
        value.update(path.relative_to(folder).as_posix().encode() + b'\0' + path.read_bytes())
    return value.hexdigest()[:12]


def publish(source=Path('/opt/openbexi/examples'), projects=Path('/workspace/projects')):
    source, projects = source.resolve(), projects.resolve()
    legacy = json.loads(Path(__file__).with_name('legacy-example-hashes.json').read_text())
    shipped = {path.relative_to(source).as_posix(): path for path in sorted(source.rglob('*'))
               if path.is_file() and path.suffix in {'.py', '.md', '.json'} and '__pycache__' not in path.parts}
    reports = []
    for name in ('demo', 'durable'):
        project = projects / name
        if not project.is_dir() or project.is_symlink():
            continue
        state = project / '.openbexi'
        if state.is_symlink():
            raise ValueError('Example state directory cannot be a symbolic link')
        state.mkdir(exist_ok=True)
        previous_path = state/'example-installation.json'
        if previous_path.is_symlink():
            raise ValueError('Example installation record cannot be a symbolic link')
        previous = json.loads(previous_path.read_text()) if previous_path.is_file() else {}
        backups = state / 'example-backups' / uuid.uuid4().hex
        report = {'project': str(project), 'installed': [], 'preserved': [], 'kept_edits': [], 'removed_generated': []}

        def backup(path):
            relative = path.relative_to(project)
            target = backups / relative
            if not target.resolve().is_relative_to(project.resolve()):
                raise ValueError('Example backup escapes project')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), target)
            report['preserved'].append(str(target.relative_to(project)))

        for relative, original in shipped.items():
            target = project / relative
            if any(part.is_symlink() for part in (target, *target.parents)):
                raise ValueError('Example destination cannot contain a symbolic link: ' + str(target))
            if target.exists():
                if target.is_file() and digest(target) == digest(original):
                    continue
                if previous.get('files', {}).get(relative) == digest(original):
                    report['kept_edits'].append(relative)
                    continue
                backup(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.example-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(original.read_bytes())
            temporary.replace(target)
            report['installed'].append(relative)
        for relative in legacy:
            target = project / relative
            if relative not in shipped and target.is_file() and not target.is_symlink():
                backup(target)
        for folder in sorted(project.iterdir()):
            match = re.fullmatch(r'examples-([0-9a-f]{12})', folder.name)
            if not match or not folder.is_dir() or folder.is_symlink():
                continue
            if not folder.resolve().is_relative_to(project.resolve()):
                raise ValueError('Generated examples escape project')
            if generated_digest(folder) == match[1]:
                shutil.rmtree(folder)
                report['removed_generated'].append(folder.name)
            else:
                backup(folder)
        manifest = dict(schema=1, files={name:digest(path) for name,path in shipped.items()}, report=report)
        (state/'example-installation.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
        reports.append(report)
    return reports


if __name__ == '__main__':
    print(json.dumps(publish(), indent=2))
