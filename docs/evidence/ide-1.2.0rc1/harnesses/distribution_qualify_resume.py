"""Qualify an offline bundle in a fresh private installation and retain evidence.

An optional prior bundle proves real cross-version upgrade. Optional SPELL tests
use the sibling's existing actual-host harness, copied and bound to this installed
interpreter/image. This is a clean directory on this host, not a fresh Windows VM.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('C:\\projects\\openbexi_ide\\.qualification\\ide-1.2.0rc1\\source-final')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--previous-bundle', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--spell-host-wheel', type=Path)
    parser.add_argument('--spell-harness', type=Path)
    parser.add_argument('--spell-image')
    parser.add_argument('--shared-debug', action='store_true', help='Qualify installed collaborative debugger peers')
    parser.add_argument('--console-menu', action='store_true', help='Qualify packaged interactive menu with real Run/Debug input')
    args = parser.parse_args()
    spell = (args.spell_host_wheel, args.spell_harness, args.spell_image)
    if any(spell) and not all(spell):
        parser.error('Supply all three --spell-* arguments together')
    bundle = args.bundle.resolve()
    evidence = args.output.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    # Bind execution to retained harness bytes even if the working checkout is
    # subsequently edited while this installed lifecycle is running.
    harnesses = evidence/'harnesses'
    harnesses.mkdir()
    names = ['distribution_qualify.py', 'distribution_desktop.py']
    if args.shared_debug:
        names.append('distribution_shared_debug.py')
    if args.console_menu:
        names.append('distribution_menu.py')
    for name in names:
        (harnesses/name).write_bytes((ROOT/'scripts'/name).read_bytes())
    installation = Path('C:\\projects\\openbexi_ide\\.qualification\\ide-1.2.0rc1\\windows-lifecycle\\installation with spaces')
    shortcuts = evidence / 'private Start menu'
    project = evidence / 'user project'
    project.mkdir()
    preferences = evidence / 'user preferences.ini'
    preferences.write_text('[General]\ntheme=dark\n')
    program = project / 'keep.py'
    program.write_text("print('retained user project')\n")
    saved_example = project / 'graphics_demo.py'
    saved_example.write_text('# user edited graphics example\n')
    protected = {str(p): sha(p) for p in (preferences, program, saved_example)}
    manifest = json.loads((bundle / 'package.json').read_text())
    report = {'passed': False, 'release_accepted': False, 'version': manifest['version'],
              'bundle_manifest_sha256': sha(bundle / 'package.json'), 'checks': [],
              'harness_sha256': sha(Path(__file__)),
              'retained_harnesses': {name:sha(harnesses/name) for name in names},
              'scope': 'Private clean directory on existing Windows host; offscreen Qt, no actual noVNC or fresh VM claim'}
    powershell = str(Path(os.environ['SYSTEMROOT']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')

    def command(label, arguments, env=None, succeeds=True):
        completed = subprocess.run(list(map(str, arguments)), capture_output=True, text=True, encoding='utf-8', errors='replace',
                                   cwd=evidence, env=env, timeout=1200)
        (evidence / (label + '.log')).write_text(completed.stdout + completed.stderr, encoding='utf-8')
        if (completed.returncode == 0) != succeeds:
            raise RuntimeError(f'{label} failed ({completed.returncode}); see {label}.log')
        return completed.stdout if succeeds else completed.stdout + completed.stderr

    def install(source, label):
        options = ['-ShortcutDirectory', shortcuts] if '$ShortcutDirectory' in (source / 'install.ps1').read_text() else ['-NoShortcuts']
        return json.loads(command(label, [powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                         source / 'install.ps1', '-Root', installation, *options]))

    try:
        if args.previous_bundle:
            previous = install(args.previous_bundle.resolve(), 'install-previous')
            previous_active = Path(previous['active'])
            report['previous_version'] = previous['version']
            report['previous_manifest_sha256'] = sha(args.previous_bundle / 'package.json')
        installed = install(bundle, 'install-candidate')
        interpreter = Path(installed['python'])
        active = Path(installed['active'])
        assert (shortcuts / 'OpenBEXI IDE.lnk').is_file()
        report['interpreter'] = str(interpreter)
        if args.previous_bundle:
            assert previous_active.is_dir() and previous_active != active
            report['checks'].append('Actual previous-version install then candidate upgrade; old interpreter retained')
        # The ordinary desktop and its debugger need no machine Python on PATH.
        clean_env = dict(os.environ, PATH=str(Path(os.environ['SYSTEMROOT']) / 'System32'),
                         PYTHONPATH=str(evidence / 'must-not-be-imported'), PYTHONHOME='invalid-untrusted-python-home',
                         QT_QPA_PLATFORM='offscreen')
        desktop_output = evidence / 'desktop'
        desktop_args = [interpreter, '-I', '-B', harnesses/'distribution_desktop.py', '--output', desktop_output, '--usability']
        if (active / 'examples').is_dir():
            desktop_args += ['--examples', active / 'examples']
        command('desktop', desktop_args, clean_env)
        desktop = json.loads((desktop_output / 'result.json').read_text())
        assert desktop['passed'] and desktop['version'] == manifest['version']
        report['desktop_sha256'] = sha(desktop_output / 'result.json')
        report['checks'] += desktop['checks']
        if args.console_menu:
            menu_output = evidence/'menu'
            command('menu', [interpreter, '-I', '-B', harnesses/'distribution_menu.py',
                             '--output', menu_output, '--examples', active/'examples'], clean_env)
            menu = json.loads((menu_output/'result.json').read_text())
            assert menu['passed'] and menu['version'] == manifest['version']
            report['menu_sha256'] = sha(menu_output/'result.json')
            report['checks'] += menu['checks']
        if args.shared_debug:
            shared_output = evidence/'shared-debug'
            command('shared-debug', [interpreter, '-I', '-B', harnesses/'distribution_shared_debug.py',
                                    '--output', shared_output], clean_env)
            shared = json.loads((shared_output/'result.json').read_text())
            assert shared['passed'] and shared['version'] == manifest['version']
            report['shared_debug_sha256'] = sha(shared_output/'result.json')
            report['checks'] += shared['checks']
        report['checks'].append('Machine Python absent from PATH; Python environment injection ignored')
        command('launcher-help', [powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', installation / 'launch.ps1', '--help'])
        if all(spell):
            image = subprocess.check_output(['docker', 'image', 'inspect', args.spell_image, '--format', '{{.Id}}'], text=True).strip()
            original = args.spell_harness.read_text(encoding='utf-8')
            adapted = original
            replacements = {
                "    sys.path.insert(0, str(args.ide / 'src'))": "    import openbexi_ide\n    assert Path(openbexi_ide.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())",
                "[str(args.interpreter), '-I', '-m', 'pip', *arguments]": "[str(args.interpreter), '-I', '-B', '-m', 'pip', *arguments]",
                "pip('install', '--no-deps', '--force-reinstall', str(args.wheel.resolve()))": "pip('install', '--no-index', '--no-compile', '--no-deps', '--force-reinstall', str(args.wheel.resolve()))",
                "            QTest.qWait(10)": "            QTest.qWait(10)\n            time.sleep(0.005)",
                "        report['ide_commit'] = subprocess.check_output(['git', '-C', str(args.ide), 'rev-parse', 'HEAD'], text=True).strip()": "        from importlib.metadata import version\n        report['ide_distribution_version'] = version('openbexi-ide')\n        report['ide_module_origin'] = openbexi_ide.__file__",
                "        report['image'] = subprocess.check_output(['docker', 'image', 'inspect', 'openbexi-spell-host:0.3.0', '--format', '{{.Id}}'], text=True).strip()": "        report['runtime_images'] = sorted({json.loads(p.read_text())['image'] for p in project.glob('.openbexi/runs/*/manifest.json') if 'image' in json.loads(p.read_text())})",
            }
            for before, after in replacements.items():
                assert adapted.count(before) == 1, before
                adapted = adapted.replace(before, after)
            harness = evidence / 'host/scripts/qualify_openbexi_host.py'
            harness.parent.mkdir(parents=True)
            harness.write_text(adapted, encoding='utf-8', newline='\n')
            command('spell-host', [interpreter, '-I', '-B', harness, '--ide', ROOT, '--interpreter', interpreter,
                                   '--wheel', args.spell_host_wheel.resolve()],
                    dict(os.environ, QT_QPA_PLATFORM='offscreen', OPENBEXI_SPELL_IMAGE=image))
            result_path, = (evidence / 'host/.qualification/v0.3/openbexi').glob('*/result.json')
            result = json.loads(result_path.read_text())
            assert result['passed'] and result['runtime_images'] == [image] and result['ide_distribution_version'] == manifest['version']
            report['spell'] = {'image': image, 'host_wheel_sha256': sha(args.spell_host_wheel),
                               'original_harness_sha256': sha(args.spell_harness), 'adapted_harness_sha256': sha(harness),
                               'result_sha256': sha(result_path), 'result': str(result_path.relative_to(evidence))}
            report['checks'] += result['checks']
        uninstall_args = [powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', installation / 'uninstall.ps1']
        if 'No files removed.' in (installation / 'uninstall.ps1').read_text():
            holder = subprocess.Popen([str(interpreter), '-I', '-B', '-c', "import time;print('OWNED_PROCESS_READY',flush=True);time.sleep(120)"],
                                      stdout=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                assert holder.stdout.readline().strip() == 'OWNED_PROCESS_READY'
                refused = command('uninstall-active-refused', uninstall_args, succeeds=False)
                assert 'No files removed.' in refused and interpreter.exists()
                assert (active / 'runtime/Lib/site-packages/openbexi_ide/app.py').is_file()
                report['checks'].append('Active bundled interpreter blocks uninstall before file deletion')
            finally:
                holder.terminate()
                holder.wait(timeout=10)
        result = json.loads(command('uninstall', uninstall_args))
        assert result['uninstalled'] and result['preserved'] == [], result
        assert not installation.exists(), installation
        assert not (shortcuts / 'OpenBEXI IDE.lnk').exists()
        assert protected == {str(p): sha(p) for p in (preferences, program, saved_example)}
        report['checks'].append('Complete manifest-owned uninstall; project, saved example and preferences unchanged')
        report['passed'] = True
    except Exception as error:
        report['error'] = repr(error)
    (evidence / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
