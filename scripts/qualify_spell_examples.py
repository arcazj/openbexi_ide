"""Run shipped SPELL examples in the installed desktop SDK and native runtime.

Retains exact sources, Docker identities, pytest output and native DAP transcripts.
This qualifies examples, not full SPELL language or IDE release acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-image')
    parser.add_argument('--native-image')
    parser.add_argument('--plugin-root', type=Path)
    args = parser.parse_args()
    if bool(args.sdk_image) == bool(args.native_image):
        parser.error('Select exactly one SDK or native image')
    if args.native_image and not args.plugin_root:
        parser.error('Native qualification needs --plugin-root for the independent DAP client')
    output = ROOT/'.qualification/spell-examples'/uuid.uuid4().hex
    project = output/'examples'
    shutil.copytree(ROOT/'examples', project, ignore=shutil.ignore_patterns('__pycache__', '*.json'))
    report = dict(passed=False, inputs={p.relative_to(ROOT).as_posix():sha(p)
        for p in sorted((ROOT/'examples').glob('*.py'))}, mode='sdk' if args.sdk_image else 'native')
    report['harness_sha256'] = sha(Path(__file__))
    report['image'] = subprocess.check_output(['docker','image','inspect',args.sdk_image or args.native_image,
        '--format','{{.Id}}'], text=True).strip()
    try:
        if args.sdk_image:
            tests = output/'tests'
            tests.mkdir()
            for name in ('conftest.py','test_runtime.py','test_debugger.py','test_spell_examples.py'):
                shutil.copyfile(ROOT/'tests'/name, tests/name)
                report['inputs']['tests/'+name] = sha(tests/name)
            name = 'openbexi-spell-examples-'+uuid.uuid4().hex
            created = False
            try:
                subprocess.run(['docker','create','--name',name,'--network=none','--cap-drop=ALL',
                    '--security-opt=no-new-privileges','--pids-limit=256','-e','QT_QPA_PLATFORM=offscreen',
                    '--entrypoint','python',report['image'],'-m','pytest','/evidence/tests/test_spell_examples.py',
                    '-q','--junitxml=/evidence/linux.xml'],check=True,capture_output=True)
                created = True
                subprocess.run(['docker','cp',str(output)+ '/.',name+':/evidence'],check=True,capture_output=True)
                # docker cp creates root-owned files; only this owned test tree is changed.
                result = subprocess.run(['docker','start','-a',name],capture_output=True,timeout=120)
                (output/'linux.log').write_bytes(result.stdout+result.stderr)
                state = json.loads(subprocess.check_output(['docker','inspect',name]))[0]
                (output/'container.json').write_text(json.dumps(state,indent=2)+'\n')
                subprocess.run(['docker','cp',name+':/evidence/linux.xml',str(output/'linux.xml')],
                    check=True,capture_output=True)
                assert result.returncode == state['State']['ExitCode'] == 0, (result.stdout+result.stderr).decode(errors='replace')
                assert b'4 passed' in result.stdout
                report['checks'] = 4
            finally:
                if created:
                    subprocess.run(['docker','rm','-f',name],check=True,capture_output=True)
        else:
            sys.path.insert(0,str(args.plugin_root.resolve()/'scripts'))
            import qualify_host_adapter as host
            host.IMAGE, host.EVIDENCE = report['image'], output
            report['client_sha256'] = sha(Path(host.__file__))
            cases = [('test_spell.py', [], 'SPELL_EXAMPLE_PASS'),
                     ('spell_native_data.py', [], 'SPELL_EXAMPLE_PASS'),
                     ('spell_native_time.py', [], 'SPELL_TIME_PASS'),
                     ('spell_native_prompt.py', ['0','1'], 'SPELL_PROMPT_PASS [True, False]'),
                     ('spell_native_child.py', ['1'], 'SPELL_CHILD_PASS choice=False'),
                     ('spell_native_parent.py', ['0','1'], 'SPELL_PARENT_PASS choice=False')]
            report['cases'] = {}
            for filename, answers, marker in cases:
                client = host.Client(project)
                try:
                    client.launch(filename,noDebug=True)
                    client.request('configurationDone')
                    for answer in answers:
                        prompt = client.event('openbexi/inputRequest')
                        client.request('openbexi/input',text=answer,promptId=prompt['promptId'])
                    assert client.event('exited')['exitCode'] == 0, filename
                    client.event('terminated')
                    text = ''.join(m['body']['output'] for m in client.transcript if m.get('event')=='output')
                    assert marker in text, text
                    if filename == 'test_spell.py':
                        assert json.loads(client.read_file('test_spell_result.json'))['native_data'] is True
                    if filename == 'spell_native_prompt.py':
                        assert json.loads(client.read_file('spell_prompt_result.json')) == dict(first=True,second=False)
                    if filename == 'spell_native_parent.py':
                        assert 'SPELL_CHILD_PASS choice=True' in text
                    report['cases'][filename] = dict(passed=True,answers=answers,marker=marker)
                finally:
                    client.close(filename.removesuffix('.py'))
        report['passed'] = True
    except Exception as error:
        report['error'] = repr(error)
    finally:
        report['evidence'] = {p.relative_to(output).as_posix():sha(p) for p in sorted(output.rglob('*')) if p.is_file()}
        (output/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(passed=report['passed'],evidence=str(output),error=report.get('error'))),flush=True)
    return not report['passed']


if __name__ == '__main__':
    raise SystemExit(main())
