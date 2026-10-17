"""Procedure presentation preserves runtime provenance and prompt ownership."""
from PySide6.QtCore import QObject, QSettings, Qt, Signal

from openbexi_ide.procedure_workspace import ProcedureRun, ProcedureWorkspace
from openbexi_runtime.launch import LaunchSpec


class Controller(QObject):
    procedure_event = Signal(object)
    prompt_answered = Signal(str, str)
    output = Signal(str)
    finished = Signal(int)

    def __init__(self):
        super().__init__()
        self.answers = []
        self.stopped = False

    def answer_prompt(self, identifier, text):
        self.answers.append((identifier, text))
        return True

    def stop(self):
        self.stopped = True


def test_native_results_use_snapshot_and_do_not_invent_success(tmp_path):
    script = tmp_path / 'main.py'
    run = ProcedureRun(tmp_path, script, 'Run')
    source = {'path': str(script)}
    run.apply(dict(kind='source', source=source, text='first\nsecond\n', offset=0, rootProcedureId='main#0'))
    run.apply(dict(kind='line', source=source, line=2, current=True))
    assert run.current[script] == 2
    assert run.results[script][2]['status'] == 'Reached'
    run.apply(dict(kind='line', source=source, line=2, status='FAILED', item='TEMP', value='300', timestamp='native-time'))
    run.apply(dict(kind='line', source=source, line=2, current=True))
    assert run.results[script][2]['status'] == 'FAILED'
    assert run.results[script][2]['timestamp'] == 'native-time'
    run.apply(dict(kind='line', source={'path': str(tmp_path.parent / 'other.py')}, line=2, current=True))
    assert list(run.results) == [script]
    run.apply(dict(kind='source', source=source, text='wrong chunk', offset=99))
    assert run.sources[script] == 'first\nsecond\n'
    run.apply(dict(kind='status', procedureId='main#0', status='WAITING'))
    run.apply(dict(kind='prompt', procedureId='child#0', promptId='child-prompt', text='Child?'))
    run.apply(dict(kind='status', procedureId='main#0', status='WAITING'))
    assert run.prompt['promptId'] == 'child-prompt'
    run.apply(dict(kind='status', procedureId='child#0', status='RUNNING'))
    assert run.status == 'WAITING' and run.prompt is None
    child = tmp_path / 'child.py'
    run.apply(dict(kind='source', source={'path': str(child)}, text='child code\n', offset=0))
    run.apply(dict(kind='line', source={'path': str(child)}, line=1, current=True))
    assert run.current_path == child and run.current[script] == 2


def test_prompt_reset_commit_rejection_expiry_and_history(app, tmp_path):
    script = tmp_path / 'main.py'; script.write_text('first\nsecond\n')
    controller = Controller(); view = ProcedureWorkspace(controller)
    view.begin(LaunchSpec(tmp_path, script), 'Run')
    first = view.active_run
    prompt = dict(kind='prompt', promptId='a', procedureId='main#0', text='Continue?',
                  choices=[dict(label='Yes', value='0'), dict(label='No', value='1')])
    controller.procedure_event.emit(prompt)
    view.submit(); assert not controller.answers
    view.choices.buttons()[0].click(); view.reset.click()
    assert view.choices.checkedButton() is None
    view.choices.buttons()[1].click(); view.commit.click(); view.submit()
    assert controller.answers == [('a', '1')]
    assert not view.commit.isEnabled()
    controller.prompt_answered.emit('a', 'Native validation rejected this answer')
    assert view.commit.isEnabled() and 'rejected' in view.prompt_message.text()
    controller.procedure_event.emit(dict(kind='promptClosed', promptId='a'))
    view.refresh(); view.submit()
    assert not view.prompt_panel.isVisible() and len(controller.answers) == 1
    # A late reply must not clear the next native prompt.
    controller.procedure_event.emit(dict(prompt, promptId='b'))
    controller.prompt_answered.emit('a', '')
    assert view.active_run.prompt['promptId'] == 'b'
    controller.output.emit('retained output')
    controller.finished.emit(0)
    script.write_text('changed\n')
    view.begin(LaunchSpec(tmp_path, script), 'Debug')
    view.history.setCurrentItem(view.history.topLevelItem(1))
    assert view.selected is first and view.model.lines == ['first', 'second']
    assert view.output.toPlainText() == 'retained output'
    assert first.status == 'Finished (0)' and not first.active
    view.submit(); assert len(controller.answers) == 1
    view.history.setCurrentItem(view.history.topLevelItem(0))
    controller.procedure_event.emit(dict(kind='prompt', promptId='c', inputType='number', text='Number?'))
    view.answer_field.setText('not a number'); view.submit()
    assert 'valid number' in view.prompt_message.text()
    view.answer_field.setText('1.25'); view.submit()
    assert controller.answers[-1] == ('c', '1.25')
    view.stop_selected(); assert controller.stopped
    controller.finished.emit(130); assert view.selected.status == 'Aborted'
    view.close()


def test_run_uses_backend_workspace_without_changing_python_launch(app, tmp_path, monkeypatch):
    from openbexi_ide.app import MainWindow
    monkeypatch.setattr(MainWindow, 'discover_backends', lambda self: None)
    view = MainWindow(tmp_path, QSettings(str(tmp_path / 'prefs.ini'), QSettings.IniFormat))
    view.backend_choices = [dict(id='fixture', label='Fixture', procedureWorkspace=True, sourceModules=['fixture'])]
    view.populate_backends()
    script = tmp_path / 'main.py'; script.write_text('import fixture\n')
    view.open_file(script)
    calls = []
    monkeypatch.setattr(view.debug_controller, 'start', lambda spec, **kw: calls.append((spec.language, kw)))
    view.run_script()
    assert calls == [('fixture', {'no_debug': True})]
    assert view.procedure_workspace.active_run.mode == 'Run'
    view.procedure_workspace.finish(0)
    python = tmp_path / 'hello.py'; python.write_text("print('hello')\n")
    view.open_file(python)
    monkeypatch.setattr(view.run_controller, 'start', lambda spec: calls.append(spec.language))
    view.run_script()
    assert calls[-1] == 'python'
    view.close()
