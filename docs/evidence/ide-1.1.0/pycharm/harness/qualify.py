"""Build a separate in-IDE test plugin and start a private real IDE instance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile
import shutil
from build import packed

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--plugin', type=Path, required=True)
    parser.add_argument('--interpreter', type=Path, required=True)
    parser.add_argument('--image', help='Candidate runtime image for this isolated qualification')
    parser.add_argument('--editor-fixture', type=Path, help='Real generated editor definitions to test the synthetic library provider')
    parser.add_argument('--ui-only', action='store_true', help='Verify native result table and capture after a presentation-only change')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--remove-from', type=Path, help='Previously successful private instance to uninstall and restart')
    options = parser.parse_args()
    evidence = options.output.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    sdk = options.sdk.resolve()
    plugins = evidence / 'plugins'
    plugins.mkdir()
    previous = options.remove_from.resolve() if options.remove_from else None
    test_class = 'RemovalQualification' if previous else 'HostQualification'
    harness = evidence / 'harness' / (test_class + '.java')
    harness.parent.mkdir()
    shutil.copy2(ROOT / ('qualification/' + test_class + '.java'), harness)
    shutil.copy2(Path(__file__), harness.parent / 'qualify.py')
    input_hashes = {
        'qualify.py': hashlib.sha256((harness.parent / 'qualify.py').read_bytes()).hexdigest(),
        'qualification/' + test_class + '.java': hashlib.sha256(harness.read_bytes()).hexdigest(),
    }
    plugin_hash = hashlib.sha256(options.plugin.read_bytes()).hexdigest()
    runtime_packages = json.loads(subprocess.check_output([
        str(options.interpreter.resolve()), '-I', '-c',
        "import json; from importlib.metadata import version; print(json.dumps({name:version(name) for name in ['openbexi-ide','openbexi-spell-host']}))"
    ], text=True, timeout=30))
    if previous:
        boundary = (ROOT.parent / '.qualification/v0.3').resolve()
        if not previous.is_relative_to(boundary) or not json.loads((previous / 'result.json').read_text())['passed']:
            raise ValueError('Removal requires a successful task-owned private instance')
        if json.loads((previous / 'process.json').read_text())['sdk'] != str(sdk):
            raise ValueError('Removal must restart the same SDK')
        plugins = previous / 'plugins'
        product_jar = (plugins / 'openbexi-spell/lib/openbexi-spell.jar').resolve(strict=True)
        old_test = (plugins / 'openbexi-qualification/lib/qualification.jar').resolve(strict=True)
        if not all(path.is_relative_to(previous) for path in (product_jar, old_test)):
            raise ValueError('Private plugin path escaped its instance')
        # Preserve these exact files as evidence outside the plugin search path.
        product_jar.rename(evidence / 'removed-product.jar')
        old_test.rename(evidence / 'previous-qualification.jar')
    with zipfile.ZipFile(options.plugin) as package:
        # This archive is the task's own compiled candidate; validate paths.
        for info in package.infolist():
            target = plugins / info.filename
            if not target.resolve().is_relative_to(plugins):
                raise ValueError('Plugin path outside private sandbox')
        if not previous:
            package.extractall(plugins)
    library = plugins / 'openbexi-spell/lib/openbexi-spell.jar'
    classes = evidence / 'test-classes'
    classes.mkdir()
    compiled = subprocess.run([str(sdk / 'jbr/bin/javac.exe'), '--release', '21', '-encoding', 'UTF-8',
        '-classpath', os.pathsep.join([str(sdk / 'lib/*'), str(library)]), '-d', str(classes),
        str(harness)], capture_output=True, text=True, timeout=60)
    (evidence / 'test-compile.log').write_text(compiled.stdout + compiled.stderr)
    compiled.check_returncode()
    descriptor = '''<idea-plugin><id>org.openbexi.spell.qualification</id><name>SPELL Private Qualification</name>
<version>1</version><vendor>OpenBEXI</vendor><depends>com.intellij.modules.platform</depends>
<depends>org.openbexi.spell</depends><extensions defaultExtensionNs="com.intellij">
<postStartupActivity implementation="org.openbexi.spell.qualification.HostQualification"/>
</extensions></idea-plugin>'''
    if previous:
        descriptor = descriptor.replace('<depends>org.openbexi.spell</depends>', '').replace('HostQualification', 'RemovalQualification')
    entries = {p.relative_to(classes).as_posix(): p.read_bytes() for p in classes.rglob('*.class')}
    entries['META-INF/plugin.xml'] = descriptor.encode()
    test_jar = plugins / 'openbexi-qualification/lib/qualification.jar'
    test_jar.parent.mkdir(parents=True, exist_ok=True)
    test_jar.write_bytes(packed(entries))
    project = evidence / 'project'
    if previous:
        project = previous / 'project'
    else:
        project.mkdir()
        (project / 'README.txt').write_text('Private OpenBEXI SPELL host qualification project.\n')
        if options.editor_fixture:
            shutil.copytree(options.editor_fixture, project / '.openbexi/editor/current')
    # A recognized, independent config prevents automatic migration from the
    # user's normal IDE and its restart into the normal launcher.
    config = evidence / 'config/options'
    config.mkdir(parents=True)
    (config / 'other.xml').write_text('<application/>\n', encoding='utf-8')
    vmoptions = evidence / 'config/private.vmoptions'
    vmoptions.write_text('-Xmx1024m\n', encoding='utf-8')
    info = json.loads((sdk / 'product-info.json').read_text())
    launch = next(item for item in info['launch'] if item['os'] == 'Windows' and item['arch'] == 'amd64')
    arguments = ['-Xms256m', '-Xmx1024m', '-ea']
    arguments += [value.replace('%IDE_HOME%', sdk.as_posix()) for value in launch['additionalJvmArguments']]
    arguments += ['-Didea.home.path=' + sdk.as_posix(), '-Didea.initially.ask.config=false',
        '-Djb.vmOptionsFile=' + vmoptions.as_posix(),
        '-Dintellij.startup.wizard=false',
        '-Dide.experimental.ui.onboarding=false',
        '-Didea.trust.all.projects=true', '-Didea.auto.reload.plugins=false', '-Dsplash=false',
        '-Dopenbexi.qualification=' + evidence.as_posix(),
        '-Dopenbexi.interpreter=' + options.interpreter.resolve().as_posix()]
    if options.image:
        arguments.append('-Dopenbexi.image=' + options.image)
    if options.ui_only:
        arguments.append('-Dopenbexi.uiOnly=true')
    for name in ['config', 'system', 'log', 'plugins']:
        location = plugins if name == 'plugins' else (previous / name if previous and name == 'config' else evidence / name)
        arguments.append('-Didea.' + name + '.path=' + location.as_posix())
    arguments += ['-classpath', os.pathsep.join(str(sdk / 'lib' / name) for name in launch['bootClassPathJarNames']),
                  launch['mainClass'], str(project)]
    argfile = evidence / 'java.args'
    argfile.write_text('\n'.join(json.dumps(value) for value in arguments), encoding='utf-8')
    with (evidence / 'launcher.log').open('wb') as log:
        process = subprocess.Popen([str(sdk / 'jbr/bin/java.exe'), '@' + str(argfile)],
            cwd=sdk, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        (evidence / 'process.json').write_text(json.dumps({'pid': process.pid, 'sdk': str(sdk), 'build': info['buildNumber']}) + '\n')
        print('Private IDE PID', process.pid, 'evidence', evidence, flush=True)
        try:
            code = process.wait(timeout=240)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
            raise
    if code or not (evidence / 'result.json').exists():
        raise RuntimeError('Private IDE qualification failed; inspect ' + str(evidence))
    report = json.loads((evidence / 'result.json').read_text())
    report['runtime_images'] = sorted({json.loads(path.read_text())['image']
        for path in project.glob('.openbexi/runs/*/manifest.json')})
    if 'Plugin to blame: OpenBEXI SPELL' in (evidence / 'launcher.log').read_text(encoding='utf-8', errors='replace'):
        report.update(passed=False, error='IDE reported an OpenBEXI SPELL plugin error; inspect launcher.log')
    report.update({'sdk': {key: info[key] for key in ('name', 'version', 'buildNumber')},
        'plugin_sha256': plugin_hash, 'runtime_packages': runtime_packages,
        'inputs': input_hashes})
    (evidence / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    if not report['passed']:
        raise RuntimeError(report.get('error', 'Host qualification failed'))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
