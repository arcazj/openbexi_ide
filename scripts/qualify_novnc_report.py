"""Validate retained real-browser noVNC evidence without promoting a release."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from PySide6.QtGui import QImage

IMAGE='sha256:78a54b8e5c60ee0e8cb4630baf753516e0814fc2ee878bf3eb12074d00e7687a'
ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',required=True,type=Path)
    args=parser.parse_args();root=args.evidence.resolve()
    browser=load(root/'browser-live/browser.json');actions=load(root/'browser-live/actions.json')
    events=load(root/'browser-live/events.json');observer=load(root/'observer/provenance.json')
    assert browser['harness_sha256']==sha(ROOT/'scripts/qualify_novnc_browser.py')
    assert observer['observer_sha256']==sha(ROOT/'scripts/qualify_novnc_observer.py')
    assert observer['version']=='1.0.0rc3' and observer['qt_platform']=='xcb'
    assert browser['url']=='http://127.0.0.1:6088/vnc.html?autoconnect=1&resize=off'
    assert browser['executable_sha256']==sha(browser['executable'])
    assert not any(e['kind']=='pageerror' for e in events)
    assert any(e['kind']=='websocket' and ':6088/' in e['url'] for e in events)
    assert sum(e['kind']=='sent' for e in events)>100
    by_label={a['command']['label']:a for a in actions}
    assert len(by_label)==len(actions) and not any(a.get('error') for a in actions)
    assert by_label['browser-finish']['command']['operation']=='close'
    for action in actions[:-1]:
        observation=action['observation'];file=Path(observation['screenshot'])
        assert file.is_relative_to(root) and file.is_file()
        assert observation['canvas']==dict(x=30,y=40,width=1600,height=1000)
    inspect=load(root/'container-inspect.json')[0]
    final=load(root/'container-after-stop.json')[0]
    assert inspect['Image']==final['Image']==IMAGE and inspect['Id']==final['Id']
    assert not final['State']['Running'] and final['State']['ExitCode']==0
    assert inspect['HostConfig']['Memory']==2*1024**3
    assert inspect['NetworkSettings']['Ports']['6080/tcp']==[dict(HostIp='127.0.0.1',HostPort='6088')]
    proof=load(root/'artifact-proof.json')
    assert sha(proof['candidate_wheel'])==proof['candidate_sha256']=='98d1a0842149f49d0f5933b20f2f2a384a509ddf9091f8bf3e1d12279cb25022'
    assert sha(root/'docker-installed-ide.whl')==proof['docker_wheel_sha256']
    with zipfile.ZipFile(root/'docker-installed-ide.whl') as installed,zipfile.ZipFile(proof['candidate_wheel']) as candidate:
        members={n:hashlib.sha256(installed.read(n)).hexdigest() for n in installed.namelist() if n.endswith('.py')}
        assert members=={n:hashlib.sha256(candidate.read(n)).hexdigest() for n in candidate.namelist() if n.endswith('.py')}
        assert members==proof['python_members'] and len(members)==39
        assert {'openbexi_ide/'+n:h for n,h in observer['installed_sources'].items()}=={
            n:h for n,h in members.items() if n.startswith('openbexi_ide/')}
    checks={}
    # The observed desktop background is uniform above its launcher content.
    # This detects a surviving title bar/window in every former IDE rectangle.
    for label in ('initial-ide-x','running-debug-ide-titlebar-x','alice-titlebar-x',
            'monitor-titlebar-x','bob-titlebar-x','durable-titlebar-x','durable-monitor-titlebar-x'):
        image=QImage(by_label[label]['observation']['screenshot']);assert not image.isNull()
        assert image.width()==1660 and image.height()==1080
        assert all(image.pixelColor(x,y).getRgb()[:3]==(233,237,243)
            for x in range(200,1460,10) for y in range(120,150,5)),label
        checks[label]=dict(passed=True,action=by_label[label]['command'],screenshot=Path(by_label[label]['observation']['screenshot']).name)
    image=QImage(by_label['terminal-titlebar-x']['observation']['screenshot'])
    assert all(image.pixelColor(x,y).getRgb()[:3]==(233,237,243)
        for x in range(475,1180,10) for y in range(300,330,5))
    assert 'OpenBEXI test terminal' in (root/'terminal-before-x.txt').read_text(encoding='utf-8-sig') or 'tester@' in (root/'terminal-before-x.txt').read_text(encoding='utf-8-sig')
    assert 'xterm' not in (root/'terminal-after-x.txt').read_text(encoding='utf-8-sig')
    checks['terminal-titlebar-x']=dict(passed=True,screenshot=Path(by_label['terminal-titlebar-x']['observation']['screenshot']).name)
    assert 'Local sample statistics' in (root/'graphics-before-x.txt').read_text(encoding='utf-8-sig')
    assert 'Local sample statistics' not in (root/'graphics-after-x.txt').read_text(encoding='utf-8-sig')
    assert load(root/'graphics-x-closed.json')['console'].count('Statistics window closed')==2
    checks['graphics-titlebar-x']=dict(passed=True,screenshot=Path(by_label['graphics-titlebar-x']['observation']['screenshot']).name)
    for prefix,bottom,up,down in [('Run','run-list.json','wheel-up.json','wheel-down.json'),
            ('Debug','debug-list.json','debug-wheel-up.json','debug-wheel-down.json')]:
        a,b,c=(load(root/name) for name in (bottom,up,down))
        assert a['busy'] and a['input_enabled'] and a['input']=='' and a['input_focused']
        assert 'stdlib-import-sweep' in a['console'] and 'Qualification exit: 0' in a['console']
        assert a['scroll']['maximum']>0 and a['scroll']['value']==a['scroll']['maximum']
        assert b['scroll']['value']<a['scroll']['value'] and c['scroll']['value']==a['scroll']['value']
        assert a['console']==b['console']==c['console']
        added=b['events'][len(a['events']):]+c['events'][len(b['events']):]
        assert {e['angle_delta'][1] for e in added if e['type']=='Wheel' and e['spontaneous']}=={-120,120}
        checks[prefix+' console input and wheel']=dict(passed=True,scroll_values=[d['scroll']['value'] for d in (a,b,c)],
            evidence=[bottom,up,down],spontaneous_native_wheel_deltas=[120,-120])
    assert load(root/'send-three.json')['console'].endswith('Topic name: ')
    assert load(root/'send-three.json')['input_focused']
    assert load(root/'menu-five-prompt.json')['console'].endswith('Value (0–100): ')
    assert load(root/'menu-six-closed.json')['console'].count('Statistics window closed')==1
    run=load(root/'run-exited.json')
    assert not run['busy'] and run['console'].endswith('Finished · exit 0\n')
    assert '261 check(s), 39 topic(s), 0 optional capability check(s) skipped.' in run['console']
    assert run['console'].count('Qualification exit: 0')==3
    checks['Run menu 1–6, Send, Return, nested prompts and exit']=dict(passed=True,evidence='run-exited.json')
    final_state=load(root/'final-observer.json')
    assert final_state['closed'] and not final_state['visible'] and not final_state['busy']
    assert any(e['type']=='Close' and e['target']=='MainWindow' and e['spontaneous'] for e in final_state['events'])
    assert load(root/'process-check-final.json')['remaining_target_processes']==[]
    assert 'NoMoreMessages' not in load(root/'debug-wheel-down.json')['console']
    assert 'NoMoreMessages' in (root/'debug-titlebar-close-console-delta.txt').read_text()
    checks['Busy Debug close stops target and adapter']=dict(passed=True,evidence=['final-observer.json','process-check-final.json'])
    def containers(name):return {r['Names']:r for line in (root/name).read_text(encoding='utf-8-sig').splitlines() if (r:=json.loads(line))}
    before=containers('containers-before-cleanup.jsonl');after=containers('containers-after-cleanup.jsonl')
    preserved=('openbexi-ide-test-ide-1','openbexi-ide-v05-ide-1','openbexi-ide-v05-rc2-ide-1','openbexi-ide-v1-rc3-ide-1')
    assert all(before[n]['ID']==after[n]['ID'] and before[n]['Ports']==after[n]['Ports'] for n in preserved)
    sources={name:sha(ROOT/'scripts'/name) for name in ('qualify_novnc_browser.py','qualify_novnc_observer.py','qualify_novnc_report.py')}
    inventory={p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file() and
        'automation-env' not in p.relative_to(root).parts and p.name!='result.json'}
    report=dict(schema='openbexi.ide.novnc-browser/1',passed=True,version='1.0.0rc3',release_accepted=False,
        runtime_image=IMAGE,container=inspect['Id'],browser=browser,installed=observer,
        artifact_proof=proof,checks=checks,preserved_desktops=list(preserved),harness_sources=sources,evidence=inventory,
        limitations=['Only the exact tested Linux rc3 desktop image and headless Edge version are qualified; existing desktops were untouched.',
            'Run exercised menu1–6; Debug exercised menu2/input/scroll and active-session X close. Prior separate Qt suites cover the wider Debug menu.',
            'Observer only launches the installed MainWindow and reads state/events; all qualified interactions are browser mouse, key and wheel events through actual noVNC.',
            'Debug titlebar shutdown appends debugpy NoMoreMessages to the user console during disconnect; absent before close, then Stopped and no surviving target/adapter. Clean shutdown logging is not claimed.',
            'Fresh Windows environment gate and full native SPELL release acceptance remain separate and open.'])
    (root/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(passed=True,checks=len(checks),report=str(root/'result.json'),sha256=sha(root/'result.json'))))


if __name__=='__main__':main()
