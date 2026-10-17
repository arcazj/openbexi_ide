"""Run the remaining Python demos, graphics and shared parallel procedures."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time

os.environ['DISPLAY'] = ':99'
os.environ['QT_QPA_PLATFORM'] = 'xcb'
display = subprocess.Popen(['Xvfb',':99','-screen','0','1600x1000x24','-nolisten','tcp','-ac'],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
report = {'passed':False,'cases':[]}
try:
    deadline = time.monotonic()+10
    while not Path('/tmp/.X11-unix/X99').exists():
        assert display.poll() is None and time.monotonic()<deadline
        time.sleep(.05)
    from PySide6.QtWidgets import QApplication
    from openbexi_ide.controller import RunController
    from openbexi_ide.debugger import DebugController
    from openbexi_runtime.launch import LaunchSpec
    from openbexi_runtime.session import Session
    from openbexi_runtime.session_http import SessionServer
    from openbexi_runtime.cli import request
    app = QApplication([])
    def wait(predicate, timeout=40):
        end = time.monotonic()+timeout
        while not predicate() and time.monotonic()<end:
            app.processEvents(); time.sleep(.01)
        assert predicate(), 'Python desktop demo timed out'
    with tempfile.TemporaryDirectory(prefix='python-desktop-') as temporary:
        project = Path(temporary)/'project'
        shutil.copytree('/opt/openbexi/examples',project)
        for name, marker in [('debug_demo','total: 16'),('graphics_demo','Statistics window'),('graphics_tkinter','TK_GRAPHICS')]:
            for debug in (False,True):
                controller = DebugController() if debug else RunController()
                exits, errors, output = [], [], []
                controller.finished.connect(exits.append)
                controller.error.connect(errors.append)
                controller.output.connect(output.append)
                args = ('--close-after','1800') if name.startswith('graphics') else ()
                spec = LaunchSpec(project,project/'test_python_support'/f'{name}.py',arguments=args)
                try:
                    controller.start(spec,{}) if debug else controller.start(spec)
                    if name.startswith('graphics'):
                        wait(lambda:marker in ''.join(output) or bool(exits) or bool(errors))
                        until = time.monotonic()+.2
                        while time.monotonic()<until:
                            app.processEvents(); time.sleep(.01)
                        assert app.primaryScreen().grabWindow(0).save(f'/evidence/{name}-{debug}.png')
                    wait(lambda:bool(exits) or bool(errors))
                    assert not errors and exits == [0] and marker in ''.join(output), (name,debug,errors,exits,output)
                    report['cases'].append(dict(file=name,debug=debug,passed=True,output=''.join(output)))
                finally:
                    controller.stop(); wait(lambda:not controller.running)
        session = Session(project,max_parallel=2,lease_seconds=60)
        server = SessionServer(('127.0.0.1',0),session)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            url = session.worker_url
            actor = request(url,'/connect',{'name':'Learning validation','invite':session.developer_invite})
            epoch = request(url,'/claim',{},actor['token'])['epoch']
            ids = [request(url,'/run',{'epoch':epoch,'script':f'test_python_support/session_{name}.py'},actor['token'])['id'] for name in ('first','second')]
            wait(lambda:all(session.procedures[identifier].status == 'RUNNING' for identifier in ids))
            wait(lambda:all(session.procedures[identifier].status == 'COMPLETED' for identifier in ids))
            assert all(session.procedures[identifier].exit_code == 0 for identifier in ids)
            report['cases'].append(dict(file='session_first.py + session_second.py',passed=True,parallel=2,
                                       procedures=[session.procedures[identifier].public() for identifier in ids]))
        finally:
            session.close(); server.shutdown(); server.server_close(); thread.join(timeout=5)
    report['passed'] = True
finally:
    display.terminate(); display.wait(timeout=5)
    Path('/evidence/python-desktop.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'passed':report['passed'],'cases':len(report['cases'])}),flush=True)
