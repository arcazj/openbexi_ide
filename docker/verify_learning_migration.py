"""Verify retained project bytes against a read-only pre-migration volume."""
import hashlib
import json
from pathlib import Path
import runpy

publisher = runpy.run_path('/opt/test-lab/publish_examples.py')
report = {'passed':False, 'projects':[]}
for name in ('demo','durable'):
    original, updated = Path('/original/projects')/name, Path('/workspace/projects')/name
    retained = {hashlib.sha256(path.read_bytes()).hexdigest() for path in updated.rglob('*')
                if path.is_file() and not path.is_symlink()}
    generated = set()
    for directory in original.iterdir():
        if directory.is_dir() and directory.name.startswith('examples-'):
            digest = publisher['generated_digest'](directory)
            if digest and directory.name == 'examples-'+digest:
                generated.add(directory)
    checked = 0
    for path in original.rglob('*'):
        if not path.is_file() or path.is_symlink() or any(path.is_relative_to(directory) for directory in generated):
            continue
        assert hashlib.sha256(path.read_bytes()).hexdigest() in retained, 'Original project bytes were not preserved'
        checked += 1
    visible = sorted(path.name for path in updated.iterdir() if not path.name.startswith('.'))
    assert visible == ['README.md','hello.py','test_python_support','test_spell'], visible
    report['projects'].append(dict(project=name, preserved_files_verified=checked,
                                   retired_generated_folders=len(generated), root_entries=visible))
report['passed'] = True
print(json.dumps(report,indent=2))
