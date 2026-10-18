"""Qualify real shared debugging using the installed private Windows interpreter."""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
import threading
import time
import traceback

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit

import openbexi_ide
from openbexi_ide.app import MainWindow
from openbexi_runtime.session import Session
from openbexi_runtime.session_http import SessionServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evidence = args.output.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    project = evidence/'project with spaces'
    project.mkdir()
    source = ('def add(value):\n    shifted=value+1\n    return shifted\n'
              'number=7\nresult=add(number)\nprint("Result",result,flush=True)\n'
              'label=input("Name: ")\nprint("Hello",label,flush=True)\n')
    (project/'main.py').write_text(source, encoding='utf-8', newline='\n')
    app = QApplication.instance() or QApplication([])
    # Cold interpreter/Qt/debugpy startup uses the service's production default.
    # Renewals under a deliberately short lease are stressed after startup.
    session = Session(project, interpreter=Path(sys.executable))
    server = SessionServer(('127.0.0.1', 0), session)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    windows = []
    report = {'passed':False, 'version':version('openbexi-ide'), 'module_origin':openbexi_ide.__file__,
              'interpreter':sys.executable, 'checks':[],
              'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'startup_lease_seconds':session.lease_seconds, 'stress_lease_seconds':1.2,
              'scope':'Installed private interpreter; real Qt/debugpy/HTTP peers offscreen'}
    assert Path(openbexi_ide.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())

    def wait(predicate, timeout=15):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            app.processEvents()
            if predicate():
                return
            time.sleep(0.01)
        raise AssertionError('Installed shared-debug condition did not arrive')

    def current_line(view):
        item = view.stack_list.currentItem()
        return item.data(Qt.UserRole)['line'] if item else None

    def variable(view, name):
        def children(parent):
            for index in range(parent.childCount()):
                child = parent.child(index)
                if child.text(0) == name:
                    return child
                found = children(child)
                if found is not None:
                    return found
        for index in range(view.variables.topLevelItemCount()):
            found = children(view.variables.topLevelItem(index))
            if found is not None:
                return found

    try:
        for name, role, invite in [('Alice','developer',session.developer_invite),
                                   ('Bob','developer',session.developer_invite),
                                   ('Reader','monitor',session.monitor_invite)]:
            view = MainWindow(project, QSettings(str(evidence/(name+'.ini')), QSettings.IniFormat))
            windows.append(view)
            view.show()
            view.open_file(project/'main.py')
            assert view.join_shared_session(user=name, role=role, url=session.worker_url, invite=invite)
            wait(lambda: view.session_client.healthy)
        alice, bob, reader = windows
        alice.session_panel.claim.click()
        wait(lambda: alice.session_client.can_control)
        alice.current_editor().toggle_breakpoint(5)
        wait(lambda: alice.debug_action.isEnabled())
        alice.debug_action.trigger()
        wait(lambda: current_line(alice)==5 and variable(reader,'number') is not None, 40)
        assert variable(reader,'number').text(1)=='7'
        wait(lambda: reader.source_view is not None)
        assert reader.source_view.editor.isReadOnly() and reader.source_view.editor.toPlainText()==source
        assert not reader.expression.isEnabled() and not reader.continue_action.isEnabled()
        report['checks'].append('Installed shared breakpoint, cached monitor variables and read-only source copy')
        # Release the original fence before configuring the isolated test
        # service's stress lease. A new claim advertises 1.2 seconds through the
        # real HTTP response; no client clock or renewal state is patched.
        wait(alice.session_panel.release.isEnabled)
        alice.session_panel.release.click()
        wait(lambda: session.controller is None and alice.session_panel.claim.isEnabled())
        with session.lock:
            session.lease_seconds = report['stress_lease_seconds']
        alice.session_panel.claim.click()
        wait(lambda: alice.session_client.can_control and alice.expression.isEnabled())
        assert alice.session_client._lease_seconds == report['stress_lease_seconds']
        assert next(iter(session.procedures.values())).status == 'PAUSED'
        wait(lambda: alice.expression.isEnabled())
        alice.expression.setText('__import__("time").sleep(1.6) or number+1')
        QTest.keyClick(alice.expression, Qt.Key_Return)
        wait(lambda: alice.eval_result.text()=='8' and alice.session_client.can_control)
        assert session.controller==alice.session_client.identity['client']
        report['checks'].append('Real 1.6-second evaluation retains explicitly reclaimed 1.2-second controller lease')
        wait(lambda: variable(alice,'number') is not None and alice.session_client.can_control)
        answered = []
        timer = QTimer()
        def answer():
            dialog = app.activeModalWidget()
            if isinstance(dialog,QInputDialog):
                field = dialog.findChild(QLineEdit)
                field.setText('9')
                QTest.keyClick(field,Qt.Key_Return)
                answered.append(True)
                timer.stop()
        timer.timeout.connect(answer)
        timer.start(10)
        alice.edit_variable(variable(alice,'number'),1)
        timer.stop()
        assert answered
        wait(lambda: variable(reader,'number') is not None and variable(reader,'number').text(1)=='9')
        for action, expected in [(alice.into_action,2),(alice.out_action,5),(alice.over_action,6)]:
            wait(action.isEnabled)
            action.trigger()
            wait(lambda: current_line(alice)==expected)
        report['checks'].append('Actual variable-edit dialog, Step Into/Out/Over and monitor cache updates')
        wait(alice.session_panel.release.isEnabled)
        alice.session_panel.release.click()
        wait(bob.session_panel.claim.isEnabled)
        bob.session_panel.claim.click()
        wait(lambda: bob.continue_action.isEnabled() and not alice.continue_action.isEnabled())
        assert next(iter(session.procedures.values())).status=='PAUSED'
        bob.continue_action.trigger()
        wait(lambda: bob.input.isEnabled() and 'Name:' in bob.console.toPlainText())
        bob.input.setText('installed visitor')
        QTest.keyClick(bob.input,Qt.Key_Return)
        wait(lambda: 'Hello installed visitor' in reader.console.toPlainText())
        wait(lambda: next(iter(session.procedures.values())).status=='COMPLETED')
        assert 'Result 10' in reader.console.toPlainText()
        report['checks'].append('Fenced two-controller handoff, explicit Continue, input and completed shared output')
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        report['procedures'] = [{'status':p.status, 'reason':p.reason, 'error':p.error,
                                 'debug':p.debug} for p in session.procedures.values()]
        report['clients'] = [{'state':v.session_client.state, 'healthy':v.session_client.healthy,
                             'epoch':v.session_client.epoch,
                             'console':v.console.toPlainText()} for v in windows]
    finally:
        for view in windows:
            (evidence/(view.session_client.identity.get('role','local')+'-'+str(windows.index(view))+'.txt')).write_text(
                view.console.toPlainText(),encoding='utf-8')
            view.close()
            wait(lambda: not view.session_client.active)
        session.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        (evidence/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
        print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    sys.exit(main())
