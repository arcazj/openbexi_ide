"""Exercise the installed Windows server panel across a real client-side TCP interruption."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import inspect
import json
from pathlib import Path
import select
import socket
import socketserver
import sys
import threading
import time
from urllib.parse import urlsplit
from urllib.request import url2pathname
import uuid
import zipfile

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QLineEdit
from openbexi_ide.app import MainWindow
from openbexi_runtime.spell_server_client import SpellServerClient


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class Forward(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as upstream:
            upstream.settimeout(3)
            upstream.connect(self.server.gateway)
            with self.server.lock:self.server.connections+=1
            peers={self.request:upstream,upstream:self.request}
            try:
                while live:=select.select(list(peers),[],[],4)[0]:
                    for origin in live:
                        data=origin.recv(65536)
                        if not data:return
                        peers[origin].sendall(data)
            except OSError:
                return


class Relay(socketserver.ThreadingTCPServer):
    allow_reuse_address=True
    daemon_threads=True

    def __init__(self,gateway,port=0):
        self.gateway=gateway;self.lock=threading.Lock();self.connections=0
        super().__init__(('127.0.0.1',port),Forward)
        self.thread=threading.Thread(target=self.serve_forever,kwargs={'poll_interval':.03},daemon=True)
        self.thread.start()

    def stop(self):
        self.shutdown();self.server_close();self.thread.join(timeout=3)
        assert not self.thread.is_alive()


@contextmanager
def through_relay(gateway,port):
    # Keep the approved HTTPS origin and TLS certificate pin on every request.
    # Only the installed panel thread's TCP destination is redirected for this process.
    real=socket.getaddrinfo;matches=[]
    def resolve(host,service,*args,**kwargs):
        if threading.current_thread().name=='spell-v08-client' and (host,service)==gateway:
            matches.append(time.monotonic());return real('127.0.0.1',port,*args,**kwargs)
        return real(host,service,*args,**kwargs)
    socket.getaddrinfo=resolve
    try:yield matches
    finally:socket.getaddrinfo=real


def verify_wheels(installation):
    data=json.loads((installation/'result.json').read_text()); verified={}
    assert data['passed'] and len(data['verified_wheels'])==6
    assert data['subjects']['spell']['commit']=='47e0cb376dac1e49e1f6745318c0eb3e43b2ec4d'
    assert data['subjects']['ide']['commit']=='fadac70d574760cbe21c5e5512a384dddfa36e80'
    for name,record in data['verified_wheels'].items():
        wheel=Path(url2pathname(urlsplit(record['direct_url']['url']).path))
        assert wheel.name==name and digest(wheel)==data['artifacts'][name]
        with zipfile.ZipFile(wheel) as archive:
            member=next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))
            dist=metadata.distribution(next(line[6:] for line in archive.read(member).decode().splitlines() if line.startswith('Name: ')))
            count=0
            for item in archive.namelist():
                if item.endswith(('/','.dist-info/RECORD')):continue
                installed=Path(dist.locate_file(item)).resolve()
                assert installed.is_relative_to(Path(sys.prefix).resolve()) and installed.read_bytes()==archive.read(item)
                count+=1
            assert count==record['members_verified_except_regenerated_RECORD']
            verified[name]={'sha256':digest(wheel),'verified_installed_members':count}
    return data['subjects'],verified


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--case',type=Path,required=True);parser.add_argument('--installation',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    assert Path(sys.prefix).resolve()==(args.installation/'venv').resolve()
    subjects,wheels=verify_wheels(args.installation)
    origin=Path(inspect.getfile(MainWindow)).resolve();assert origin.is_relative_to(Path(sys.prefix).resolve())
    case=args.case.resolve();owner_config=case/'clients/alice/connection.json'; observer_config=case/'clients/watch-01/connection.json'
    cfg=json.loads(owner_config.read_text());url=urlsplit(cfg['url']);gateway=(url.hostname,url.port);assert gateway[0]=='127.0.0.1'
    authority=json.loads((case/'deployment.json').read_text());assert authority['port']==url.port
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs,True)
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);assert app.platformName()=='windows'
    report={'status':'INCOMPLETE','at_utc':datetime.now(timezone.utc).isoformat(),'subjects':subjects,'exact_installed_wheels':wheels,
            'installation_receipt_sha256':digest(args.installation/'result.json'),'qt_platform':app.platformName(),
            'installed_ide_origin':str(origin),'namespace':authority['namespace'],'gateway_certificate_sha256':cfg['fingerprint'],
            'role_image_ids':{k:authority[k] for k in ('server_image','core','worker_image')},
            'harness_sha256':digest(Path(__file__)),'events':[]}
    def note(phase,**data):
        report['events'].append({'phase':phase,'utc':datetime.now(timezone.utc).isoformat(),**data});print(phase,flush=True)
        (out/'result.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    def wait(condition,label,limit=15):
        until=time.monotonic()+limit
        while time.monotonic()<until:
            app.processEvents()
            if condition():return
            QTest.qWait(15)
            time.sleep(.005)
        raise TimeoutError(label)
    project=out/'project';first=project/'positive';target=project/'active'
    first.mkdir(parents=True);target.mkdir()
    marker='local-executed-'+str(uuid.uuid4())+'.txt';code="from pathlib import Path\nPath(__file__).with_name(%r).write_text('local execution observed', encoding='utf-8')\n"%marker
    for parent in (first,target):(parent/'procedure.py').write_text(code,encoding='utf-8')
    assert digest(first/'procedure.py')==digest(target/'procedure.py')
    view=MainWindow(project,QSettings(str(out/'only-this-run.ini'),QSettings.IniFormat));panel=view.spell_server_panel;view.show()
    local_starts=[]; view.run_controller.process.started.connect(lambda:local_starts.append('Run'))
    view.debug_controller.state_changed.connect(lambda *a:local_starts.append('Debug') if view.debug_controller.running else None)
    direct=SpellServerClient.from_config(observer_config)
    def rows():
        assert direct.contexts()==['A'] and direct.read('A','health')['subject']=='watch-01'
        return sorted([{k:row.get(k) for k in ('id','procedure_id','owner','control_state','lifecycle','native_root_result')}
                       for row in direct.read('A','executions')['executions']],key=lambda r:r['id'])
    def controls():return {'local_run':view.run_action.isEnabled(),'local_debug':view.debug_action.isEnabled(),'busy_local':view.is_busy(),
            'server_reserve':panel.reserve_button.isEnabled(),'server_start_native':panel.launch_button.isEnabled(),
            'server_run':panel.command_buttons['CMD_RUN'].isEnabled(),'authenticated_state':bool(panel.state.get('health')),
            'server_client_attached':panel.client is not None,'panel_controller_sessions':len(panel.connections),
            'has_controller_for_selection':bool(panel.client and panel.selected() and panel.client.has_controller('A',panel.selected()['id']))}
    relay=None
    try:
        view.open_file(first/'procedure.py');wait(view.run_action.isEnabled,'enable explicit local control')
        assert view.interpreter.samefile(sys.executable) and view.language.currentData()=='python'
        view.run_action.trigger();wait(lambda:(first/marker).is_file() and not view.is_busy(),'positive local sentinel',45)
        assert (first/marker).read_text()=='local execution observed' and local_starts==['Run']
        view.open_file(target/'procedure.py');wait(lambda:view.current_editor().path==(target/'procedure.py') and view.debug_action.isEnabled(),'open the guarded file')
        assert not (target/marker).exists(); baseline=list(local_starts); before=rows();assert before
        note('positive_control',source_sha256=digest(target/'procedure.py'),identical_source_wrote_marker_in_control_directory=True,
             guarded_marker=marker,guarded_marker_exists=False,local_run_and_debug_enabled=True,public_observer_rows=before)
        relay=Relay(gateway);port=relay.server_address[1]
        with through_relay(gateway,port) as requests:
            view.output_tabs.setCurrentWidget(panel);wait(lambda:panel.connect_button.isVisible(),'server tab')
            picked=[]
            def choose():
                dialog=app.activeModalWidget()
                if isinstance(dialog,QFileDialog):
                    dialog.setDirectory(str(owner_config.parent))
                    def enter_filename():
                        entry=dialog.findChild(QLineEdit,'fileNameEdit')
                        assert entry is not None
                        entry.setFocus();entry.selectAll();QTest.keyClicks(entry,owner_config.name)
                        picked.append(True);QTest.keyClick(entry,Qt.Key_Return)
                    QTimer.singleShot(200,enter_filename)
                elif len(picked)<1:QTimer.singleShot(25,choose)
            QTimer.singleShot(25,choose);QTest.mouseClick(panel.connect_button,Qt.LeftButton)
            wait(lambda:not panel.busy and panel.state.get('health',{}).get('subject')=='alice','real authenticated owner snapshot')
            assert picked==[True] and panel.executions.topLevelItemCount()==len(before)
            panel.executions.setCurrentItem(panel.executions.topLevelItem(0)); original=panel.client
            choice=next(i for i in range(panel.procedures.count()) if panel.procedures.itemText(i)=='procedure-02');panel.procedures.setCurrentIndex(choice)
            state=controls();assert not state['local_run'] and not state['local_debug'] and state['server_reserve'] and state['server_client_attached']
            assert relay.connections>=4 and len(requests)>=4
            note('authenticated_server_panel',status=panel.status.text(),subject=panel.state['health']['subject'],catalog_entries=panel.procedures.count(),
                 actual_tls_connections=relay.connections,controls=state,selected_procedure='procedure-02',selected_remote_row=panel.selected()['id'])
            count=relay.connections;relay.stop();relay=None
            with socket.socket() as check:
                check.settimeout(1);assert check.connect_ex(('127.0.0.1',port))!=0
            assert rows()==before
            QTest.mouseClick(panel.reserve_button,Qt.LeftButton)
            wait(lambda:not panel.busy and '503 gateway_unavailable' in panel.status.text(),'real failed remote action')
            error=panel.status.text(); failed=controls()
            assert failed['server_client_attached'] and panel.client is original and not any(failed[k] for k in ('local_run','local_debug','busy_local','server_reserve','server_start_native','server_run','authenticated_state','panel_controller_sessions','has_controller_for_selection'))
            note('remote_action_after_relay_stopped',remote_action='Reserve',visible_error=error,relay_port_closed=True,controls=failed,
                 original_gateway_still_authenticated=True,unchanged_direct_observer_rows=True)
            # Refresh is a separate installed remote read; wait for its own worker completion.
            calls=len(requests);QTest.mouseClick(panel.refresh_button,Qt.LeftButton)
            wait(lambda:len(requests)>calls and not panel.busy,'failed refresh returned')
            assert panel.status.text()==error
            view.current_editor().setFocus();QTest.keyClick(view.current_editor(),Qt.Key_F5);QTest.keyClick(view.current_editor(),Qt.Key_F5,Qt.ShiftModifier)
            app.processEvents();view.run_script();run_message=view.statusBar().currentMessage();view.debug_script();debug_message=view.statusBar().currentMessage()
            assert 'Disconnect before using local Run' in run_message and 'Disconnect before using local Debug' in debug_message
            assert not view.is_busy() and local_starts==baseline and not (target/marker).exists()
            note('offline_read_and_local_entry_points',refresh_error=error,local_shortcuts=['F5','Shift+F5'],run_guard=run_message,debug_guard=debug_message,
                 guarded_source_exists=(target/'procedure.py').is_file(),guarded_marker_exists=False,local_controller_starts_after_connect=0)
            relay=Relay(gateway,port); view.output_tabs.setCurrentWidget(panel);QTest.mouseClick(panel.refresh_button,Qt.LeftButton)
            wait(lambda:not panel.busy and panel.state.get('health',{}).get('subject')=='alice','explicit refresh after relay restored')
            final=controls();assert panel.client is original and final['server_reserve'] and not final['local_run'] and not final['local_debug']
            assert rows()==before and local_starts==baseline and not (target/marker).exists() and relay.connections>=3
            report['status']='PASS';note('recovered_on_explicit_refresh',subject=panel.state['health']['subject'],status=panel.status.text(),controls=final,
                 independent_after=before,restored_connections=relay.connections,prior_live_connections=count,guarded_marker_exists=False,
                 local_controller_starts_after_connect=0,normal_file_chooser=True)
    except BaseException as exc:
        report['status']='FAIL';note('failure',error=str(exc),error_type=type(exc).__name__,last_panel_status=panel.status.text(),local_console=view.console.toPlainText()[-500:],controls=controls());raise
    finally:
        if relay:relay.stop()
        direct.forget();view.close();app.processEvents()


if __name__=='__main__':main()
