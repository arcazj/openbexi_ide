"""Actual Qt clients talking to the real HTTP session and isolated Python workers."""
from contextlib import contextmanager
import json
from pathlib import Path
import threading
import time

import pytest
from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtTest import QTest

from openbexi_ide.app import MainWindow
from openbexi_runtime.cli import request
from openbexi_runtime.session import Session, SessionError, TERMINAL
from openbexi_runtime.session_http import Handler, SessionServer


def wait(app, predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        # QTest.qWait holds the Python GIL in this Windows binding. The real
        # HTTP fixture and desktop transport need Python threads to progress.
        time.sleep(0.01)
    raise AssertionError('Shared desktop condition did not arrive')


@pytest.fixture
def shared(app, tmp_path):
    project = tmp_path/'shared project'
    project.mkdir()
    for name in ('first.py', 'second.py'):
        (project/name).write_text("import time\ndef live():\n    value=21\n    print('shared café 😀',flush=True)\n    while True:\n        time.sleep(0.02)\nlive()\n", encoding='utf-8')
    session = Session(project, lease_seconds=1.2)
    server = SessionServer(('127.0.0.1', 0), session)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    windows = []
    invite = tmp_path/'invitations.json'
    invite.write_text(json.dumps({'url': session.worker_url, 'developer_invite': session.developer_invite,
                                  'monitor_invite': session.monitor_invite}), encoding='utf-8')

    def desktop(name, role='developer'):
        view = MainWindow(project, QSettings(str(tmp_path/(name+'.ini')), QSettings.IniFormat))
        windows.append(view)
        view.show()
        view.open_file(project/'first.py')
        assert view.join_shared_session(user=name, invite_file=invite, role=role)
        wait(app, lambda: view.session_client.healthy)
        assert view.language.isVisible()
        assert view.language_action.isVisible()
        return view

    yield session, server, desktop, project, invite
    for view in windows:
        for index in range(view.tabs.count()):
            view.tabs.widget(index).document().setModified(False)
        view.close()
        wait(app, lambda: not view.session_client.active)
        if view.session_client._thread:
            view.session_client._thread.join(timeout=1)
            assert not view.session_client._thread.is_alive()
    session.close()
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def claim(app, view):
    QTest.mouseClick(view.session_panel.claim, Qt.LeftButton)
    wait(app, lambda: view.session_client.can_control)


def procedure(view, identifier):
    for index in range(view.session_panel.procedures.topLevelItemCount()):
        item = view.session_panel.procedures.topLevelItem(index)
        if item.data(0, Qt.UserRole)['id'] == identifier:
            view.session_panel.procedures.setCurrentItem(item)
            return item
    raise AssertionError('Procedure is not visible')


def test_two_desktops_and_cli_monitor_real_stack_input_and_fenced_handoff(shared, app):
    session, server, desktop, project, _ = shared
    (project/'input.py').write_text("def blocked():\n    value=21\n    name=input('Name: ')\n    print('Hello',name,flush=True)\nblocked()\n", encoding='utf-8')
    developer = desktop('Alice')
    reader = desktop('Reader', 'monitor')
    cli = request(session.worker_url, '/connect', {'name':'CLI developer', 'invite':session.developer_invite})
    epoch = request(session.worker_url, '/claim', {}, cli['token'])['epoch']
    identifier = request(session.worker_url, '/run', {'epoch':epoch, 'script':'input.py'}, cli['token'])['id']
    wait(app, lambda: 'Name:' in reader.console.toPlainText()
         and reader.session_panel.stack.topLevelItemCount() > 0
         and reader.session_panel.locals.topLevelItemCount() > 0)
    assert reader.current_editor().isReadOnly()
    for action in (reader.run_action, reader.debug_action, reader.stop_action, reader.save_action, reader.eof_action):
        assert not action.isEnabled()
    assert not reader.input.isEnabled()
    assert not reader.session_client.command('claim')
    assert not reader.save_current()
    assert not developer.session_panel.claim.isEnabled()
    request(session.worker_url, '/release', {'epoch':epoch}, cli['token'])
    wait(app, lambda: developer.session_panel.claim.isEnabled())
    claim(app, developer)
    procedure(developer, identifier)
    wait(app, lambda: developer.input.isEnabled())
    developer.input.setText('café 😀')
    QTest.keyClick(developer.input, Qt.Key_Return)
    wait(app, lambda: session.procedures[identifier].status == 'PAUSED')
    wait(app, lambda: developer.session_panel.resume.isEnabled())
    QTest.mouseClick(developer.session_panel.resume, Qt.LeftButton)
    wait(app, lambda: 'Hello café 😀' in reader.console.toPlainText())
    wait(app, lambda: session.procedures[identifier].status == 'COMPLETED')
    assert not reader.debug_controller.running and not reader.run_controller.running
    with pytest.raises(ValueError, match='controller token'):
        request(session.worker_url, '/stop', {'epoch':epoch,'procedure':identifier}, cli['token'])


def test_serial_queue_pause_handoff_and_live_parallel_configuration(shared, app):
    session, _, desktop, project, _ = shared
    alice, bob = desktop('Alice'), desktop('Bob')
    claim(app, alice)
    alice.run_action.trigger()
    wait(app, lambda: len(session.procedures) == 1 and next(iter(session.procedures.values())).status == 'RUNNING')
    alice.open_file(project/'second.py')
    wait(app, lambda: alice.run_action.isEnabled())
    alice.run_action.trigger()
    wait(app, lambda: len(session.procedures) == 2)
    identifiers = list(session.procedures)
    wait(app, lambda: session.procedures[identifiers[1]].reason == 'WAITING_TOKEN')
    assert session.procedures[identifiers[1]].process is None
    alice.session_panel.scope.setCurrentIndex(1)
    wait(app, lambda: alice.session_panel.pause.isEnabled())
    QTest.mouseClick(alice.session_panel.pause, Qt.LeftButton)
    wait(app, lambda: all(p.status == 'PAUSED' for p in session.procedures.values()))
    # Native state can arrive before the desktop finishes its pause request.
    # Exercise the enabled control, as an operator would, after UI acknowledgement.
    wait(app, lambda: alice.session_panel.release.isEnabled())
    QTest.mouseClick(alice.session_panel.release, Qt.LeftButton)
    wait(app, lambda: bob.session_panel.claim.isEnabled())
    claim(app, bob)
    assert not alice.run_action.isEnabled()
    bob.session_panel.scope.setCurrentIndex(1)
    wait(app, lambda: bob.session_panel.resume.isEnabled())
    QTest.mouseClick(bob.session_panel.resume, Qt.LeftButton)
    wait(app, lambda: session.procedures[identifiers[0]].status == 'RUNNING')
    wait(app, lambda: bob.session_panel.apply_slots.isEnabled())
    bob.session_panel.slots.setValue(2)
    QTest.mouseClick(bob.session_panel.apply_slots, Qt.LeftButton)
    wait(app, lambda: session.max_parallel == 2 and all(p.status == 'RUNNING' for p in session.procedures.values()))
    wait(app, lambda: bob.session_panel.apply_slots.isEnabled())
    bob.session_panel.slots.setValue(1)
    QTest.mouseClick(bob.session_panel.apply_slots, Qt.LeftButton)
    wait(app, lambda: 'Pause or finish' in bob.console.toPlainText())
    assert session.max_parallel == 2
    wait(app, lambda: bob.session_panel.pause.isEnabled())
    QTest.mouseClick(bob.session_panel.pause, Qt.LeftButton)
    wait(app, lambda: all(p.status == 'PAUSED' for p in session.procedures.values()))
    wait(app, lambda: bob.session_panel.apply_slots.isEnabled())
    bob.session_panel.slots.setValue(1)
    QTest.mouseClick(bob.session_panel.apply_slots, Qt.LeftButton)
    wait(app, lambda: session.max_parallel == 1)
    wait(app, lambda: bob.session_panel.resume.isEnabled())
    QTest.mouseClick(bob.session_panel.resume, Qt.LeftButton)
    wait(app, lambda: sum(p.has_token for p in session.procedures.values()) == 1)
    wait(app, lambda: bob.session_panel.stop.isEnabled())
    QTest.mouseClick(bob.session_panel.stop, Qt.LeftButton)
    wait(app, lambda: all(p.status in TERMINAL for p in session.procedures.values()))


def test_closing_controller_desktop_pauses_session_and_preserves_live_worker(shared, app):
    session, _, desktop, _, _ = shared
    alice, bob = desktop('Alice'), desktop('Bob')
    claim(app, alice)
    alice.run_action.trigger()
    wait(app, lambda: bool(session.procedures) and next(iter(session.procedures.values())).status == 'RUNNING')
    running = next(iter(session.procedures.values()))
    pid = running.worker_pid
    alice.close()
    wait(app, lambda: not alice.isVisible() and running.status == 'PAUSED')
    assert session.controller is None
    assert all(member['name'] != 'Alice' for member in session.clients.values())
    wait(app, lambda: bob.session_panel.claim.isEnabled())
    claim(app, bob)
    wait(app, lambda: bob.session_panel.resume.isEnabled())
    QTest.mouseClick(bob.session_panel.resume, Qt.LeftButton)
    wait(app, lambda: running.status == 'RUNNING')
    assert running.worker_pid == pid


def test_monitor_invitation_cannot_silently_become_developer(shared, app):
    session, _, _, project, _ = shared
    view = MainWindow(project)
    try:
        assert view.join_shared_session(user='Reader', url=session.worker_url, invite=session.developer_invite, role='monitor')
        wait(app, lambda: not view.session_client.active)
        assert not session.clients
        assert 'Invitation role does not match' in view.console.toPlainText()
    finally:
        view.close()


def test_http_is_off_the_ui_thread_and_cancelled_join_revokes_credential(shared, app):
    session, server, _, project, _ = shared
    began = threading.Event()

    class Delayed(Handler):
        def do_POST(self):
            if self.path == '/connect':
                began.set()
                time.sleep(0.4)
            super().do_POST()

    server.RequestHandlerClass = Delayed
    view = MainWindow(project)
    ticks = []
    timer = QTimer()
    timer.setInterval(20)
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start()
    try:
        assert view.join_shared_session(user='Cancelled', url=session.worker_url, invite=session.developer_invite)
        wait(app, began.is_set)
        QTest.qWait(80)
        view.session_client.disconnect()
        wait(app, lambda: not view.session_client.active)
        assert len(ticks) >= 8
        assert not session.clients
        assert view.join_shared_session(user='Rejoined', url=session.worker_url, invite=session.developer_invite)
        wait(app, lambda: view.session_client.healthy)
        assert len(session.clients) == 1
    finally:
        timer.stop()
        view.close()
        wait(app, lambda: not view.session_client.active)


def test_connection_failure_disables_controls_and_never_auto_claims(shared, app):
    session, server, desktop, _, _ = shared
    unavailable = threading.Event()

    class Failing(Handler):
        def do_GET(self):
            if unavailable.is_set() and self.path.startswith('/session'):
                self.reply(503, {'error':'Fixture unavailable'})
            else:
                super().do_GET()

    server.RequestHandlerClass = Failing
    view = desktop('Alice')
    claim(app, view)
    view.run_action.trigger()
    wait(app, lambda: bool(session.procedures) and next(iter(session.procedures.values())).status == 'RUNNING')
    running = next(iter(session.procedures.values()))
    unavailable.set()
    wait(app, lambda: not view.session_client.healthy)
    assert not view.run_action.isEnabled()
    assert not view.stop_action.isEnabled()
    wait(app, lambda: running.status == 'PAUSED')
    unavailable.clear()
    wait(app, lambda: view.session_client.healthy)
    assert view.session_client.epoch is None
    assert session.controller is None
    assert not view.run_action.isEnabled()
    claim(app, view)
    assert running.status == 'PAUSED'


def test_revoked_client_cannot_reacquire_control_after_authenticated_disconnect(shared):
    session, _, _, _, _ = shared
    joined = request(session.worker_url, '/connect', {'name':'CLI', 'invite':session.developer_invite})
    actor = session.authenticate(joined['token'])
    request(session.worker_url, '/disconnect', {}, joined['token'])
    with pytest.raises(SessionError, match='revoked'):
        session.claim(actor)
    with pytest.raises(ValueError, match='credential'):
        request(session.worker_url, '/claim', {}, joined['token'])


def test_desktop_python_and_spell_share_slots_with_actual_binary_dss(shared, app, tmp_path):
    pytest.importorskip('openbexi_spell_plugin')
    from dss.local import create_servers

    session, _, desktop, project, _ = shared
    runtime, tcp, api = create_servers(tmp_path/'desktop-dss.sqlite', 0)
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (tcp, api)]
    for thread in threads:
        thread.start()
    session.dss_url = f'http://127.0.0.1:{api.server_port}'
    (project/'spell_demo.py').write_text("from spell.lang import Display,GetTM,BuildTC,Send\n"
        "Display('DESKTOP SPELL START')\nDisplay(str(GetTM('TM1')))\nSend(BuildTC('CMD1'))\n"
        "Display('DESKTOP SPELL COMPLETE')\n", encoding='utf-8')
    try:
        owner, reader = desktop('Alice'), desktop('Reader', 'monitor')
        claim(app, owner)
        owner.session_panel.slots.setValue(2)
        QTest.mouseClick(owner.session_panel.apply_slots, Qt.LeftButton)
        wait(app, lambda: session.max_parallel == 2 and owner.run_action.isEnabled())
        owner.run_action.trigger()
        wait(app, lambda: bool(session.procedures) and next(iter(session.procedures.values())).status == 'RUNNING')
        owner.open_file(project/'spell_demo.py')
        owner.language.setCurrentIndex(1)
        wait(app, lambda: owner.run_action.isEnabled())
        owner.run_action.trigger()
        wait(app, lambda: 'DESKTOP SPELL COMPLETE' in reader.console.toPlainText())
        wait(app, lambda: list(session.procedures.values())[-1].status == 'COMPLETED')
        assert runtime.engine.state()['core']['commands_executed'] == 1
        assert [p.status for p in session.procedures.values()] == ['RUNNING', 'COMPLETED']
        wait(app, lambda: reader.session_panel.procedures.topLevelItemCount() == 2)
        spell_id = list(session.procedures)[1]
        procedure(reader, spell_id)
        assert 'DESKTOP SPELL COMPLETE' in reader.session_panel.output.toPlainText()
        assert reader.session_panel.members.topLevelItemCount() == 2
        folder = Path(__file__).resolve().parents[1]/'.qualification/v0.2/desktop-ui'
        folder.mkdir(parents=True, exist_ok=True)
        for window, name in ((owner, 'controller'), (reader, 'monitor')):
            window.output_tabs.setCurrentWidget(window.session_panel)
            window.resize(1440, 940)
            app.processEvents()
            assert window.grab().save(str(folder/(name+'.png')))
    finally:
        for server in (api, tcp):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)
        runtime.engine.close()
