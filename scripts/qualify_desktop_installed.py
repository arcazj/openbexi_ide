"""Exercise installed desktop/session/plugin wheels with two actual Qt clients.

Run with python -I scripts/qualify_desktop_installed.py --output .qualification/v0.2
No source path is inserted. A fresh loopback DSS and isolated procedure workers
are closed after the check; evidence stays in the selected output directory.
"""
import argparse
from importlib.metadata import version
import json
from pathlib import Path
import threading
import time
import uuid

from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import openbexi_ide.app as desktop_module
import openbexi_runtime
import openbexi_spell_plugin
from dss.local import create_servers
from openbexi_runtime.cli import request
from openbexi_runtime.session import Session
from openbexi_runtime.session_http import SessionServer


def wait(app, predicate):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError('Installed desktop condition did not arrive')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('.qualification/v0.2'))
    root = parser.parse_args().output.resolve()
    run = root / ('installed-desktop-' + uuid.uuid4().hex)
    project = run / 'project'
    project.mkdir(parents=True)
    (project / 'python.py').write_text(
        "import time\ndef live():\n    value=42\n    print('Python café 😀',flush=True)\n"
        "    while True:\n        time.sleep(0.02)\nlive()\n", encoding='utf-8')
    (project / 'spell.py').write_text(
        "from spell.lang import Display, GetTM, BuildTC, Send\n"
        "Display(str(GetTM('TM1')))\nSend(BuildTC('CMD1'))\nDisplay('SPELL complete')\n",
        encoding='utf-8')
    origins = {name: module.__file__ for name, module in (
        ('desktop', desktop_module), ('runtime', openbexi_runtime), ('plugin', openbexi_spell_plugin))}
    assert all('site-packages' in origin for origin in origins.values()), origins
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    runtime, tcp, api = create_servers(run / 'dss.sqlite', 0)
    for server in (tcp, api):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    session = Session(project, max_parallel=2, dss_url=f'http://127.0.0.1:{api.server_port}')
    server = SessionServer(('127.0.0.1', 0), session)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    views = []
    try:
        for name, role in (('Alice', 'developer'), ('Reader', 'monitor')):
            view = desktop_module.MainWindow(project, QSettings(str(run / (name + '.ini')), QSettings.IniFormat))
            views.append(view)
            view.resize(1440, 940)
            view.show()
            view.open_file(project / 'python.py')
            assert view.join_shared_session(user=name, url=session.worker_url, role=role,
                invite=session.monitor_invite if role == 'monitor' else session.developer_invite)
            wait(app, lambda: view.session_client.healthy)
            assert view.language.isVisible()
            view.output_tabs.setCurrentWidget(view.session_panel)
        owner, reader = views
        QTest.mouseClick(owner.session_panel.claim, Qt.LeftButton)
        wait(app, lambda: owner.session_client.can_control)
        owner.run_action.trigger()
        wait(app, lambda: 'Python café 😀' in reader.console.toPlainText())
        wait(app, lambda: reader.session_panel.stack.topLevelItemCount() > 0)
        assert reader.current_editor().isReadOnly() and not reader.run_action.isEnabled()
        assert not reader.session_panel.claim.isEnabled()
        owner.open_file(project / 'spell.py')
        owner.language.setCurrentIndex(1)
        wait(app, lambda: owner.run_action.isEnabled())
        owner.run_action.trigger()
        wait(app, lambda: len(session.procedures) == 2 and list(session.procedures.values())[1].status == 'COMPLETED')
        assert runtime.engine.state()['core']['commands_executed'] == 1
        wait(app, lambda: 'SPELL complete' in reader.console.toPlainText())
        captures = []
        for view, name in zip(views, ('controller', 'monitor')):
            path = root / ('installed-' + name + '.png')
            assert view.grab().save(str(path))
            captures.append(str(path))
        pid = next(iter(session.procedures.values())).process.pid
        QTest.mouseClick(owner.session_panel.release, Qt.LeftButton)
        wait(app, lambda: next(iter(session.procedures.values())).status == 'PAUSED')
        cli = request(session.worker_url, '/connect', {'name': 'CLI developer', 'invite': session.developer_invite})
        epoch = request(session.worker_url, '/claim', {}, cli['token'])['epoch']
        request(session.worker_url, '/resume', {'epoch': epoch, 'procedure': 'all'}, cli['token'])
        wait(app, lambda: next(iter(session.procedures.values())).status == 'RUNNING')
        assert next(iter(session.procedures.values())).process.pid == pid
        request(session.worker_url, '/stop', {'epoch': epoch, 'procedure': 'all'}, cli['token'])
        wait(app, lambda: next(iter(session.procedures.values())).status == 'CANCELLED')
        request(session.worker_url, '/disconnect', {}, cli['token'])
        result = {'version': version('openbexi-ide'), 'plugin_version': version('openbexi-spell-plugin'),
            'origins': origins, 'captures': captures, 'dss_commands_executed': 1, 'passed': True,
            'checks': ['two installed Qt clients and a CLI developer', 'visible Python/SPELL selector',
                'monitor read-only controls', 'live project stack', 'Unicode output',
                'parallel Python/SPELL with actual binary DSS command', 'pause and handoff preserve worker PID',
                'CLI takeover, resume and stop', 'graceful credential revocation']}
    finally:
        for view in views:
            view.close()
            wait(app, lambda: not view.session_client.active)
        assert not session.clients and session.controller is None
        session.close()
        for service in (server, api, tcp):
            service.shutdown()
            service.server_close()
        runtime.engine.close()
    (root / 'installed-desktop.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
