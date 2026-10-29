"""Publish the explicitly authorized unqualified pair; preserve before cleanup."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
REPO = os.environ['GITHUB_REPOSITORY']
assert REPO in ('arcazj/openbexi_spell_plugin', 'arcazj/openbexi_ide')
SPELL = REPO.endswith('_plugin')
TAG = 'v0.8-rc1' if SPELL else 'v1.2.1'
OUT = Path(os.environ['RUNNER_TEMP']) / ('release-' + TAG)
OUT.mkdir(exist_ok=True)

def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()

def api(endpoint, method='GET', payload=None):
    args = ['gh', 'api', endpoint, '--method', method]
    if payload is not None:
        args += ['--input', '-']
    value = run(*args, input=json.dumps(payload) if payload is not None else None)
    return json.loads(value) if value else None

def pages(endpoint):
    value = run('gh', 'api', '--paginate', '--slurp', endpoint)
    return [x for page in json.loads(value) for x in page]

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def download_verified(directory):
    directory.mkdir(exist_ok=True)
    run('gh', 'release', 'download', TAG, '--repo', REPO, '--dir', str(directory))
    for line in (directory/'SHA256SUMS.txt').read_text().splitlines():
        expected, name = line.split('  ', 1)
        assert Path(name).name == name
        assert digest(directory/name) == expected, name

def publish():
    sha = run('git', 'rev-parse', 'HEAD')
    assert sha == os.environ['GITHUB_SHA']
    assert os.environ['GITHUB_REF'] == 'refs/heads/main'
    releases = pages(f'repos/{REPO}/releases?per_page=100')
    existing = next((r for r in releases if r['tag_name'] == TAG), None)
    if existing:
        assert not existing['draft']
        run('git', 'fetch', 'origin', 'refs/tags/'+TAG)
        assert run('git', 'rev-parse', 'FETCH_HEAD^{}') == sha, 'Published tag conflict'
        download_verified(OUT/'existing-verified')
        print('Existing release and all checksums verified; bytes unchanged.')
        return
    branches = pages(f'repos/{REPO}/branches?per_page=100')
    run('git', 'fetch', 'origin', '+refs/heads/*:refs/remotes/origin/*', '--tags')
    for branch in branches:
        assert run('git', 'rev-parse', 'refs/remotes/origin/'+branch['name']) == branch['commit']['sha']
    (OUT/'branch-heads.json').write_text(json.dumps({'repository':REPO,'branches':{b['name']:b['commit']['sha'] for b in branches}},indent=2)+'\n')
    bundle = OUT/'branch-recovery.bundle'
    run('git', 'bundle', 'create', str(bundle), '--all')
    run('git', 'bundle', 'verify', str(bundle))
    run('git', 'archive', '--format=zip', '--prefix='+REPO.split('/')[1]+'-'+TAG+'/', '--output='+str(OUT/('source-'+TAG+'.zip')), sha)
    components = ['server','host_plugin','shared_plugin','driver_plugin'] if SPELL else ['.']
    for component in components:
        run(sys.executable, '-m', 'build', '--wheel', '--sdist', '--outdir', str(OUT), str(ROOT/component))
    run(sys.executable, '-m', 'venv', str(OUT/'smoke-env'))
    py = str(OUT/'smoke-env/bin/python')
    wheels = sorted(str(p) for p in OUT.glob('*.whl'))
    run(py, '-m', 'pip', 'install', '--no-deps', *wheels)
    code = ('import openbexi_spell_server; assert openbexi_spell_server.__version__ == "0.8.0rc1"; import openbexi_spell_host; assert openbexi_spell_host.__version__ == "0.8.0rc1"' if SPELL else 'import importlib.metadata; assert importlib.metadata.version("openbexi-ide") == "1.2.1"; import openbexi_runtime.processes')
    run(py, '-I', '-c', code, cwd=OUT)
    module = 'openbexi_spell_server' if SPELL else 'openbexi_runtime.spell_server_client'
    run(py, '-I', '-m', module, '--help', cwd=OUT)
    run(sys.executable, '-m', 'pip', 'install', '--no-deps', *wheels)
    # Focused source regressions are reported separately from full acceptance.
    tests = ['server/tests/test_v08_native_legacy_source.py'] if SPELL else ['tests/test_process_pid_namespaces.py','tests/test_process_reaping.py']
    env = dict(os.environ, PYTHONPATH=str(ROOT/('server/src' if SPELL else 'src')), QT_QPA_PLATFORM='offscreen', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    with (OUT/'focused-tests.log').open('w') as log:
        test = subprocess.run([sys.executable,'-m','pytest',*tests,'-q','--tb=short','--junitxml='+str(OUT/'focused-tests.xml')],env=env,stdout=log,stderr=subprocess.STDOUT)
    manifest = {'repository':REPO,'tag':TAG,'commit':sha,'tree':run('git','rev-parse','HEAD^{tree}'),'python':sys.version,'qualification':'UNQUALIFIED','full_qualification_passed':False,'focused_test_exit_code':test.returncode,'wheel_install_and_cli_help':'passed','native_images_built':False,'offline_desktop_bundles_built':False,'scope':'Source archives and Python wheels only; no native/full desktop joint acceptance.'}
    (OUT/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (OUT/'UNQUALIFIED_RELEASE.md').write_text((ROOT/'docs/UNQUALIFIED_RELEASE.md').read_text())
    (OUT/'prompt4v0.8-qualification.md').write_text((ROOT/'prompt4v0.8-qualification.md').read_text())
    files = sorted(p for p in OUT.iterdir() if p.is_file())
    sums = OUT/'SHA256SUMS.txt'
    sums.write_text(''.join(digest(p)+'  '+p.name+'\n' for p in files))
    refs = pages(f'repos/{REPO}/git/matching-refs/tags/{TAG}')
    exact = next((r for r in refs if r['ref'] == 'refs/tags/'+TAG),None)
    if exact:
        run('git','fetch','origin','refs/tags/'+TAG)
        assert run('git','rev-parse','FETCH_HEAD^{}') == sha, 'Existing tag conflict'
    else:
        tag = api(f'repos/{REPO}/git/tags','POST',{'tag':TAG,'message':TAG+' — UNQUALIFIED; qualification incomplete','object':sha,'type':'commit'})
        api(f'repos/{REPO}/git/refs','POST',{'ref':'refs/tags/'+TAG,'sha':tag['sha']})
    command = ['gh','release','create',TAG,'--repo',REPO,'--verify-tag','--title',('OpenBEXI SPELL '+TAG if SPELL else 'OpenBEXI IDE '+TAG)+' — UNQUALIFIED','--notes-file',str(OUT/'UNQUALIFIED_RELEASE.md')]
    if SPELL:
        command += ['--prerelease']
    run(*command, *(str(p) for p in files), str(sums))
    download_verified(OUT/'download-verification')
    print('Published release; independent asset download and SHA-256 verification passed.')

def cleanup():
    assert api(f'repos/{REPO}')['default_branch'] == 'main', 'Set main as default first'
    check = OUT/'cleanup-verification'
    download_verified(check)
    run('git','bundle','verify',str(check/'branch-recovery.bundle'))
    archived = json.loads((check/'branch-heads.json').read_text())
    assert archived['repository'] == REPO
    for status in ['in_progress','queued','waiting','pending','requested']:
        for r in api(f'repos/{REPO}/actions/runs?status={status}&per_page=100')['workflow_runs']:
            assert str(r['id']) == os.environ['GITHUB_RUN_ID'], 'Other active work: '+str(r['id'])
    branches = pages(f'repos/{REPO}/branches?per_page=100')
    for b in branches:
        if b['name'] != 'main':
            assert archived['branches'].get(b['name']) == b['commit']['sha'], 'Unarchived branch change: '+b['name']
            assert not b['protected'], 'Protected branch: '+b['name']
    from urllib.parse import quote
    removed=[]
    for b in branches:
        if b['name'] == 'main':
            continue
        current=api(f'repos/{REPO}/git/ref/heads/'+quote(b['name'],safe=''))
        assert current['object']['sha'] == archived['branches'][b['name']]
        api(f'repos/{REPO}/git/refs/heads/'+quote(b['name'],safe=''),'DELETE')
        removed.append(b['name'])
        print('Removed archived branch:',b['name'],flush=True)
    cache_result=subprocess.run(['gh','cache','delete','--all','--repo',REPO],capture_output=True,text=True)
    final=pages(f'repos/{REPO}/branches?per_page=100')
    assert [b['name'] for b in final] == ['main']
    result={'repository':REPO,'removed_branches':removed,'remaining_branches':['main'],'cache_exit_code':cache_result.returncode,'cache_output':cache_result.stdout+cache_result.stderr,'release_assets_verified':True,'run_id':os.environ['GITHUB_RUN_ID']}
    report=OUT/('cleanup-'+os.environ['GITHUB_RUN_ID']+'.json')
    report.write_text(json.dumps(result,indent=2)+'\n')
    run('gh','release','upload',TAG,str(report),'--repo',REPO)
    assert cache_result.returncode == 0, 'Cache deletion incomplete; see cleanup report'
    print(json.dumps(result))

if __name__ == '__main__':
    {'publish':publish,'cleanup':cleanup}[sys.argv[1]]()
