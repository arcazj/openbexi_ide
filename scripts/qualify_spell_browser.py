"""Exercise the SPELL menu through actual Edge/noVNC input and passive Qt state."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import time
import uuid

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', required=True)
    parser.add_argument('--image', required=True)
    args = parser.parse_args()
    token = uuid.uuid4().hex
    output = ROOT/'.qualification/ide-rc4-browser'/token
    output.mkdir(parents=True)
    remote = '/tmp/spell-browser-'+token
    def docker(*arguments):
        return subprocess.check_output(['docker', *arguments], timeout=30)
    state = json.loads(docker('inspect', args.container))[0]
    assert state['Image'] == args.image
    assert state['NetworkSettings']['Ports']['6080/tcp'] == [dict(HostIp='127.0.0.1', HostPort='6080')]
    (output/'container.json').write_text(json.dumps(state, indent=2)+'\n')
    # Create the writable project as the container user before archive extraction;
    # tar's implicit parent directory otherwise belongs to root.
    docker('exec',args.container,'mkdir','-p',remote+'/project')
    source = ROOT/'examples/test_spell'
    files = {'observer.py':ROOT/'scripts/qualify_novnc_observer.py',
             **{'project/'+p.name:p for p in source.iterdir() if p.is_file()},
             'project/test_menu.py':source/'spell_menu.py'}
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w') as archive:
        for name, path in files.items():
            raw = path.read_bytes()
            info = tarfile.TarInfo(name); info.size=len(raw); info.uid=info.gid=10003; info.mode=0o644
            archive.addfile(info, io.BytesIO(raw))
    subprocess.run(['docker','cp','-a','-',args.container+':'+remote], input=payload.getvalue(),check=True,capture_output=True,timeout=30)
    docker('exec','-d',args.container,'python','-I',remote+'/observer.py','--project',remote+'/project','--output',remote+'/observed')
    def read():
        return json.loads(docker('exec',args.container,'cat',remote+'/observed/state.json'))
    def wait(predicate, label, timeout=30):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            try:
                value = read()
                if predicate(value):
                    (output/(label+'.json')).write_text(json.dumps(value,indent=2)+'\n')
                    return value
            except (subprocess.CalledProcessError, json.JSONDecodeError):
                pass
            time.sleep(.15)
        raise AssertionError('Browser condition timed out: '+label)
    current = wait(lambda s:s['visible'],'initial')
    report = dict(passed=False,image=args.image,inputs={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in files.items()},
        scope='Actual browser Run/Debug, menu input, scrolling and X; fixture filename test_menu.py has exact shipped spell_menu.py bytes')
    try:
        with sync_playwright() as automation:
            browser = automation.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
            context = browser.new_context(viewport=dict(width=1660,height=1080))
            context.tracing.start(screenshots=True,snapshots=True,sources=True)
            page = context.new_page()
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto('http://127.0.0.1:6080/vnc.html?autoconnect=1&resize=off',wait_until='networkidle')
            page.locator('canvas').wait_for(state='visible')
            page.wait_for_timeout(1000)
            canvas=page.locator('canvas').bounding_box()
            assert canvas['width']==1600 and canvas['height']==1000
            def click(name):
                x,y,w,h=read()['geometry'][name]
                page.mouse.click(canvas['x']+x+w/2,canvas['y']+y+h/2)
            def answer(text, enter=False):
                click('input')
                wait(lambda s:s['input_enabled'] and s['input_focused'],'input-focused')
                page.keyboard.type(text)
                wait(lambda s:s['input']==text,'input-delivered')
                page.keyboard.press('Enter') if enter else click('send')
            click('run')
            wait(lambda s:s['busy'] and s['console'].endswith('Choose 0-16: '),'run-menu')
            answer('13')
            wait(lambda s:'UNAVAILABLE SPECIAL' in s['console'] and s['console'].endswith('Choose 0-16: '),'run-all')
            answer('12',True)
            wait(lambda s:s['console'].endswith('Family name or ALL: '),'catalogue-prompt')
            answer('ALL')
            before=wait(lambda s:'763 reference entries. Source commit:' in s['console'] and s['console'].endswith('Choose 0-16: '),'catalogue')
            x,y,w,h=before['geometry']['console']
            page.mouse.move(canvas['x']+x+w/2,canvas['y']+y+h/2)
            page.mouse.wheel(0,-600)
            wait(lambda s:s['scroll']['value']<before['scroll']['value'],'wheel-up')
            page.mouse.wheel(0,600)
            wait(lambda s:s['scroll']['value']==before['scroll']['value'],'wheel-down')
            answer('0',True)
            wait(lambda s:not s['busy'] and 'SPELL_MENU_COMPLETE checks=11 failures=0' in s['console'],'run-finished')
            page.screenshot(path=str(output/'run-finished.png'))
            click('debug')
            wait(lambda s:s['busy'] and s['console'].endswith('Choose 0-16: '),'debug-menu')
            answer('1')
            wait(lambda s:'PASS PY' in s['console'] and s['console'].endswith('Choose 0-16: '),'debug-choice')
            answer('0',True)
            final=wait(lambda s:not s['busy'] and 'SPELL_MENU_COMPLETE checks=1 failures=0' in s['console'],'debug-finished')
            assert 'Traceback' not in final['console'] and 'FAIL ' not in before['console']
            page.screenshot(path=str(output/'debug-finished.png'))
            x,y,w,h=final['frame'];page.mouse.click(canvas['x']+x+w-14,canvas['y']+y+10)
            wait(lambda s:s['closed'] and not s['visible'],'titlebar-x')
            assert not errors,errors
            context.tracing.stop(path=str(output/'browser-trace.zip'))
            report.update(passed=True,browser_version=browser.version,page_errors=errors,
                checks=['Run all','catalogue 763 entries','Send','Enter','scroll up/down','Debug choice','titlebar X'])
            browser.close()
    except Exception as error:
        report['error']=repr(error)
    finally:
        subprocess.run(['docker','cp',args.container+':'+remote+'/observed',str(output/'observer')],check=True,capture_output=True,timeout=30)
        report['evidence']={p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*') if p.is_file()}
        (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=report['passed'],evidence=str(output),error=report.get('error'))),flush=True)
    return not report['passed']


if __name__=='__main__':
    raise SystemExit(main())
