"""Retain actual headless browser inputs and screenshots for the noVNC gate.

JSON commands on stdin drive only Playwright mouse/keyboard APIs. Remote Qt
state is read separately; this harness does not inject Qt or X11 input.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--browser',required=True,type=Path)
    parser.add_argument('--url',default='http://127.0.0.1:6088/vnc.html?autoconnect=1&resize=off')
    args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    events=[];commands=[]
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(executable_path=str(args.browser),headless=True,
            args=['--no-first-run','--no-default-browser-check'])
        context=browser.new_context(viewport={'width':1660,'height':1080},device_scale_factor=1)
        context.tracing.start(screenshots=True,snapshots=True,sources=True)
        page=context.new_page()
        page.on('console',lambda event:events.append(dict(kind='console',level=event.type,text=event.text)))
        page.on('pageerror',lambda error:events.append(dict(kind='pageerror',text=str(error))))
        def socket(ws):
            events.append(dict(kind='websocket',url=ws.url))
            ws.on('framesent',lambda payload:events.append(dict(kind='sent',size=len(payload),
                sha256=hashlib.sha256(payload if isinstance(payload,bytes) else payload.encode()).hexdigest())))
        page.on('websocket',socket)
        page.goto(args.url,wait_until='networkidle')
        page.locator('canvas').wait_for(state='visible',timeout=30000)
        page.wait_for_timeout(1500)
        metadata=dict(browser_version=browser.version,executable=str(args.browser.resolve()),
            executable_sha256=hashlib.sha256(args.browser.read_bytes()).hexdigest(),url=args.url,
            harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            scope='Real browser mouse/key/wheel events through noVNC; no Qt or X11 input injection')
        (output/'browser.json').write_text(json.dumps(metadata,indent=2)+'\n')
        def observe(label):
            file=output/(label+'.png');page.screenshot(path=str(file),full_page=True)
            result=dict(screenshot=str(file),canvas=page.locator('canvas').bounding_box(),
                title=page.title(),text=page.locator('body').inner_text()[:3000])
            print(json.dumps(result),flush=True)
            return result
        observe('000-connected')
        try:
            for line in sys.stdin:
                command=json.loads(line);operation=command['operation'];index=len(commands)+1
                item=dict(command=command,time_ns=time.time_ns());commands.append(item)
                try:
                    if operation=='click':page.mouse.click(command['x'],command['y'],click_count=command.get('count',1))
                    elif operation=='wheel':
                        page.mouse.move(command['x'],command['y']);page.mouse.wheel(command.get('dx',0),command['dy'])
                    elif operation=='key':page.keyboard.press(command['key'])
                    elif operation=='type':page.keyboard.type(command['text'],delay=command.get('delay',50))
                    elif operation=='observe':pass
                    elif operation=='close':break
                    else:raise ValueError('Unknown browser operation')
                    page.wait_for_timeout(command.get('settle_ms',500))
                    item['observation']=observe(f'{index:03d}-'+command.get('label',operation))
                except Exception as error:
                    item['error']=str(error);print(json.dumps({'error':str(error)}),flush=True)
                finally:
                    (output/'actions.json').write_text(json.dumps(commands,indent=2)+'\n')
        finally:
            (output/'events.json').write_text(json.dumps(events,indent=2)+'\n')
            context.tracing.stop(path=str(output/'browser-trace.zip'))
            browser.close()


if __name__=='__main__':main()
