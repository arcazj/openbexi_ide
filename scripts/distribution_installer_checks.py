"""Adversarial lifecycle checks for the Windows installer with tiny owned payloads.

Private fixtures exercise ownership/path safety without deleting user data.
Full runtime/application qualification is separate (distribution_desktop.py).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / 'packaging/windows'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(root, version, text):
    bundle = root / ('bundle-' + version)
    payload = bundle / 'payload'
    payload.mkdir(parents=True)
    (payload / 'owned.txt').write_text(text)
    (payload / 'unchanged.txt').write_text('ordinary package file')
    manifest = {'product': 'OpenBEXI IDE', 'format': 1, 'version': version,
                'payload_id': hashlib.sha256(text.encode()).hexdigest(),
                'files': {p.name: digest(p) for p in payload.iterdir()}}
    (bundle / 'package.json').write_text(json.dumps(manifest))
    for source in RECIPES.glob('*.ps1'):
        shutil.copyfile(source, bundle / source.name)
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    root = parser.parse_args().output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    report = {'passed': False, 'checks': [], 'recipes': {p.name: digest(p) for p in RECIPES.glob('*.ps1')}}
    old = fixture(root, '0.2.0', 'older payload')
    new = fixture(root, '0.3.0', 'newer payload')
    installed = root / 'private install with spaces'
    project = root / 'user project'
    project.mkdir()
    sentinel = project / 'program.py'
    sentinel.write_text("print('preserved user project')\n")
    preferences = root / 'preferences.ini'
    preferences.write_text('[General]\ntheme=dark\n')
    protected = {str(p): digest(p) for p in (sentinel, preferences)}

    def run(script, *args, succeeds=True):
        completed = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                    str(script), *map(str, args)], capture_output=True, text=True)
        with (root / 'operations.log').open('a', encoding='utf-8') as log:
            log.write(str(script) + '\n' + completed.stdout + completed.stderr + '\n')
        assert (completed.returncode == 0) == succeeds, completed.stdout + completed.stderr
        return json.loads(completed.stdout) if succeeds else completed.stderr

    def install(bundle, target=installed, succeeds=True):
        return run(bundle / 'install.ps1', '-Root', target, '-NoShortcuts', succeeds=succeeds)

    try:
        first = install(old)
        install(old)
        assert first['version'] == '0.2.0'
        old_active = Path(first['active'])
        second = install(new)
        assert second['version'] == '0.3.0' and old_active.is_dir()
        assert (old_active / 'owned.txt').read_text() == 'older payload'
        active = Path(second['active'])
        assert (active / 'owned.txt').read_text() == 'newer payload'
        report['checks'].append('Fresh install, idempotent install and versioned upgrade retaining the old payload')
        (active / 'owned.txt').write_text('user modified file')
        (active / 'unknown.txt').write_text('user added file')
        (installed / 'user-note.txt').write_text('preserve unknown root file')
        removed = run(installed / 'uninstall.ps1')
        assert removed['uninstalled'] and removed['preserved']
        assert (active / 'owned.txt').read_text() == 'user modified file'
        assert (active / 'unknown.txt').read_text() == 'user added file'
        assert not (active / 'unchanged.txt').exists() and not old_active.exists()
        assert (installed / 'user-note.txt').exists()
        assert any(path.endswith('user-note.txt') for path in removed['preserved'])
        assert protected == {str(p): digest(p) for p in (sentinel, preferences)}
        report['checks'].append('Uninstall removes unchanged files and preserves edits, unknown files, project and preferences')
        unowned = root / 'existing user directory'
        unowned.mkdir()
        (unowned / 'precious.txt').write_text('keep')
        install(new, unowned, succeeds=False)
        assert (unowned / 'precious.txt').read_text() == 'keep'
        report['checks'].append('Refuse pre-existing unowned installation directory')
        clean = root / 'clean lifecycle'
        install(new, clean)
        result = run(clean / 'uninstall.ps1')
        assert result['preserved'] == [] and not clean.exists()
        report['checks'].append('Unmodified uninstall removes the owned directory completely')
        edited_tools = root / 'edited installer tools'
        install(new, edited_tools)
        with (edited_tools / 'launch.ps1').open('a') as modified:
            modified.write('\n# user customization\n')
        result = run(edited_tools / 'uninstall.ps1')
        assert any(path.endswith('launch.ps1') for path in result['preserved'])
        assert (edited_tools / 'launch.ps1').exists() and (edited_tools / '.openbexi-install.json').exists()
        report['checks'].append('Modified installation tools are reported and retain the ownership marker')
        shortcut_install = root / 'shortcut installation'
        menu = root / 'private Start menu'
        run(new / 'install.ps1', '-Root', shortcut_install, '-ShortcutDirectory', menu)
        shortcut = menu / 'OpenBEXI IDE.lnk'
        customizer = root / 'customize-shortcut.ps1'
        customizer.write_text("param([string] $Link)\n$shell = New-Object -ComObject WScript.Shell\n"
                              "$shortcut = $shell.CreateShortcut($Link)\n$shortcut.Description = 'User edited description'\n"
                              "$shortcut.Save()\n@{changed=$true} | ConvertTo-Json\n")
        run(customizer, '-Link', shortcut)
        changed_hash = digest(shortcut)
        run(new / 'install.ps1', '-Root', shortcut_install, '-ShortcutDirectory', menu, succeeds=False)
        assert digest(shortcut) == changed_hash
        result = run(shortcut_install / 'uninstall.ps1')
        assert any(path.endswith('OpenBEXI IDE.lnk') for path in result['preserved'])
        assert digest(shortcut) == changed_hash and (shortcut_install / '.openbexi-install.json').exists()
        report['checks'].append('User-edited Start menu shortcut survives rejected upgrade and uninstall')
        (new / 'payload/owned.txt').write_text('corrupt')
        install(new, root / 'tamper-target', succeeds=False)
        assert not (root / 'tamper-target').exists()
        report['checks'].append('Payload corruption rejected before creating an installation')
        traversal = fixture(root, '9.9.9', 'unsafe')
        manifest = json.loads((traversal / 'package.json').read_text())
        manifest['files'] = {'../outside.txt': '0' * 64}
        (traversal / 'package.json').write_text(json.dumps(manifest))
        install(traversal, root / 'traversal-target', succeeds=False)
        assert not (root / 'traversal-target').exists()
        report['checks'].append('Manifest traversal rejected before writing outside the payload')
        report['passed'] = True
    finally:
        (root / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
