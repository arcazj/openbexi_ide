"""Real Qt desktops share debugpy through the authenticated session service."""
import time

import pytest
from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QInputDialog, QLineEdit

from openbexi_runtime.cli import request
from openbexi_ide.app import MainWindow
from test_durable_sessions import git, commit, durable
from test_shared_ui import shared, claim, procedure, wait


def variable(view, name):
    def search(parent):
        for index in range(parent.childCount()):
            child = parent.child(index)
            if child.text(0) == name:
                return child
            found = search(child)
            if found is not None:
                return found
    for index in range(view.variables.topLevelItemCount()):
        found = search(view.variables.topLevelItem(index))
        if found is not None:
            return found


def line(view):
    item = view.stack_list.currentItem()
    return item.data(Qt.UserRole).get('line') if item else None


def edit(app, view, name, value):
    wait(app, lambda: variable(view, name) is not None and view.session_client.can_control)
    sent = []
    timer = QTimer()
    timer.setInterval(10)
    def answer():
        dialog = app.activeModalWidget()
        if isinstance(dialog, QInputDialog):
            field = dialog.findChild(QLineEdit)
            field.setText(value)
            QTest.keyClick(field, Qt.Key_Return)
            sent.append(True)
            timer.stop()
    timer.timeout.connect(answer)
    timer.start()
    try:
        view.edit_variable(variable(view, name), 1)
        assert sent
    finally:
        timer.stop()


def test_shared_desktops_breakpoint_edit_step_cached_monitor_and_handoff(shared, app):
    session, _, desktop, project, _ = shared
    (project/'first.py').write_text('def add(value):\n    shifted=value+1\n    return shifted\n'
        'number=7\nresult=add(number)\nprint("Result",result,flush=True)\n'
        'label=input("Name: ")\nprint("Hello",label,flush=True)\n')
    calls = []
    original = session.debug_request
    def track(actor, *args, **kwargs):
        calls.append((actor['name'], args[2]))
        return original(actor, *args, **kwargs)
    session.debug_request = track
    alice, bob, reader = desktop('Alice'), desktop('Bob'), desktop('Reader', 'monitor')
    claim(app, alice)
    alice.current_editor().toggle_breakpoint(5)
    wait(app, lambda: alice.debug_action.isEnabled())
    alice.debug_action.trigger()
    try:
        wait(app, lambda: alice.shared_debug.paused and line(alice) == 5
             and variable(alice, 'number') is not None, 35)
    except AssertionError as error:
        states = [(p.status, p.reason, p.debug) for p in session.procedures.values()]
        raise AssertionError({'procedures': states, 'paused': alice.shared_debug.paused,
            'line': line(alice), 'healthy': alice.session_client.healthy,
            'can_control': alice.session_client.can_control,
            'console': alice.console.toPlainText()}) from error
    p = next(iter(session.procedures.values()))
    assert p.debug['all_threads_stopped'] and not p.has_token
    assert alice.current_editor().verified_breakpoints[5]
    wait(app, lambda: reader.shared_debug.paused and variable(reader, 'number') is not None
         and reader.source_view is not None, 15)
    assert reader.source_view.editor.isReadOnly()
    assert reader.source_view.editor.execution_line == 5
    assert not reader.current_editor().document().isModified()
    for action in (reader.debug_action, reader.continue_action, reader.over_action, reader.pause_action):
        assert not action.isEnabled()
    assert not reader.expression.isEnabled()
    reader.expression.setText('number=999')
    reader.evaluate_expression()
    assert not reader.shared_debug.control('continue')
    assert not any(name == 'Reader' for name, _ in calls)
    assert reader.source_view.editor.toPlainText() == (project/'first.py').read_text()
    alice.expression.setText('number + 1')
    wait(app, lambda: alice.expression.isEnabled())
    QTest.keyClick(alice.expression, Qt.Key_Return)
    wait(app, lambda: alice.eval_result.text() == '8', 15)
    edit(app, alice, 'number', '9')
    wait(app, lambda: variable(reader, 'number') is not None and variable(reader, 'number').text(1) == '9', 15)
    wait(app, lambda: alice.into_action.isEnabled())
    alice.into_action.trigger()
    wait(app, lambda: line(alice) == 2 and alice.out_action.isEnabled(), 15)
    alice.out_action.trigger()
    wait(app, lambda: line(alice) == 5 and alice.over_action.isEnabled(), 15)
    alice.over_action.trigger()
    wait(app, lambda: line(alice) == 6 and alice.session_panel.release.isEnabled(), 15)
    alice.session_panel.release.click()
    wait(app, lambda: bob.session_panel.claim.isEnabled())
    claim(app, bob)
    procedure(bob, p.id)
    wait(app, lambda: bob.continue_action.isEnabled() and not alice.continue_action.isEnabled(), 15)
    time.sleep(0.15)
    assert p.status == 'PAUSED'
    bob.continue_action.trigger()
    wait(app, lambda: 'Name:' in bob.console.toPlainText() and bob.input.isEnabled(), 15)
    bob.input.setText('visitor')
    QTest.keyClick(bob.input, Qt.Key_Return)
    wait(app, lambda: p.status == 'COMPLETED' and 'Hello visitor' in reader.console.toPlainText(), 15)
    assert 'Result 10' in reader.console.toPlainText()
    assert not any(name == 'Reader' for name, _ in calls)
    wait(app, lambda: not reader.stack_list.count() and not reader.variables.topLevelItemCount())


def test_shared_native_debug_is_unavailable_and_monitor_source_is_bounded(shared, app):
    session, _, desktop, project, _ = shared
    alice, reader = desktop('Alice'), desktop('Reader', 'monitor')
    claim(app, alice)
    alice.language.setCurrentIndex(alice.language.findData('spell'))
    assert not alice.debug_action.isEnabled()
    alice.debug_script()
    assert 'unavailable' in alice.console.toPlainText().lower()
    assert not session.procedures
    alice.language.setCurrentIndex(alice.language.findData('python'))
    alice.debug_action.trigger()
    wait(app, lambda: bool(session.procedures) and alice.shared_debug.paused, 35)
    p = next(iter(session.procedures.values()))
    for name in ('../outside.py', str(project/'first.py')):
        with pytest.raises(ValueError, match='relative|inside'):
            request(session.worker_url, '/source', {'procedure':p.id,'path':name}, reader.session_client.identity['token'])
    (project/'oversized.py').write_bytes(b'#' * 2_000_001)
    with pytest.raises(ValueError, match='2 MB'):
        request(session.worker_url, '/source', {'procedure':p.id,'path':'oversized.py'}, reader.session_client.identity['token'])
    token = reader.session_client.identity['token']
    source = request(session.worker_url, '/source', {'procedure':p.id,'path':'first.py'}, token)
    assert source['text'] == (project/'first.py').read_bytes().decode('utf-8')
    assert not source['captured']
    alice.stop_action.trigger()
    wait(app, lambda: p.status == 'CANCELLED', 15)


def test_keep_control_renews_while_real_evaluation_blocks_transport(shared, app):
    session, _, desktop, project, _ = shared
    (project/'first.py').write_text('number=7\nprint(number)\n')
    alice, reader = desktop('Alice'), desktop('Reader', 'monitor')
    claim(app, alice)
    alice.current_editor().toggle_breakpoint(2)
    alice.debug_action.trigger()
    wait(app, lambda: line(alice) == 2 and alice.expression.isEnabled(), 35)
    epoch = alice.session_client.epoch
    alice.expression.setText('__import__("time").sleep(1.6) or number')
    QTest.keyClick(alice.expression, Qt.Key_Return)
    wait(app, lambda: next(iter(session.procedures.values())).debug['state'] == 'evaluating', 10)
    assert next(iter(session.procedures.values())).has_token
    assert not alice.expression.isEnabled() and not alice.continue_action.isEnabled()
    wait(app, lambda: alice.eval_result.text() == '7' and alice.session_client.can_control, 15)
    assert session.controller == alice.session_client.identity['client']
    assert session.epoch == epoch
    assert not reader.expression.isEnabled()
    wait(app, lambda: alice.continue_action.isEnabled())
    alice.continue_action.trigger()
    wait(app, lambda: next(iter(session.procedures.values())).status == 'COMPLETED', 15)


def test_monitor_reads_captured_dependency_after_worktree_change_and_rejects_tampering(tmp_path, app):
    project = tmp_path/'captured project'
    project.mkdir()
    git(project, 'init', '-q')
    original = 'from dependency import value\nnumber=7\nprint(value)\n'
    (project/'main.py').write_text(original, newline='\n')
    dependency = "# coding: latin-1\nvalue='capturé'\n"
    (project/'dependency.py').write_bytes(dependency.encode('latin-1'))
    commit(project)
    windows = []
    with durable(project, tmp_path/'authority') as (session, url):
        try:
            for name, role, invite in [('Alice','developer',session.developer_invite), ('Reader','monitor',session.monitor_invite)]:
                view = MainWindow(project, QSettings(str(tmp_path/(name+'.ini')), QSettings.IniFormat))
                windows.append(view)
                view.show()
                view.open_file(project/'main.py')
                assert view.join_shared_session(user=name, role=role, url=url, invite=invite)
                wait(app, lambda: view.session_client.healthy)
            alice, reader = windows
            claim(app, alice)
            alice.current_editor().toggle_breakpoint(3)
            alice.debug_action.trigger()
            wait(app, lambda: line(alice) == 3 and reader.source_view is not None, 35)
            p = next(iter(session.procedures.values()))
            (project/'main.py').write_text('raise RuntimeError("changed live source")\n')
            (project/'dependency.py').write_text('value="changed live dependency"\n')
            assert reader.source_view.windowTitle().startswith('Captured source')
            assert reader.source_view.editor.toPlainText() == original
            body = {'procedure':p.id, 'path':'dependency.py'}
            source = request(url, '/source', body, reader.session_client.identity['token'])
            assert source['captured'] and source['text'] == dependency
            assert source['capture_sha256'] == p.capture_digest
            target = p.spec.project/'dependency.py'
            saved = target.read_bytes()
            target.write_bytes(saved+b'# tamper\n')
            with pytest.raises(ValueError, match='bytes differ'):
                request(url, '/source', body, reader.session_client.identity['token'])
            target.write_bytes(saved)
            assert request(url, '/source', body, reader.session_client.identity['token'])['text'] == dependency
        finally:
            for view in windows:
                view.close()
                wait(app, lambda: not view.session_client.active)
