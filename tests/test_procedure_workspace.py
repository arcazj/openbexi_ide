"""Procedure presentation preserves runtime provenance and prompt ownership."""
from PySide6.QtCore import QObject, QSettings, Qt, Signal

from openbexi_ide.procedure_workspace import ProcedureRun, ProcedureWorkspace
from openbexi_runtime.launch import LaunchSpec
from openbexi_ide.procedure_workspace import CodeResultsModel
from openbexi_runtime.procedure_colors import CURRENT_LINE


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


def test_code_rows_stay_white_and_cursor_follows_only_the_current_source(tmp_path):
    script, child = tmp_path / 'main.py', tmp_path / 'child.py'
    run = ProcedureRun(tmp_path, script, 'Run')
    for path, content in ((script, 'first\nsecond\nthird\n'), (child, 'child\n')):
        run.apply(dict(kind='source', source={'path': str(path)}, text=content, offset=0))
    model = CodeResultsModel()
    model.display(run, script)
    color = lambda row, column: model.data(model.index(row, column), Qt.BackgroundRole).name()
    run.apply(dict(kind='line', source={'path': str(script)}, line=1, current=True))
    assert color(0, 1) == CURRENT_LINE
    run.apply(dict(kind='line', source={'path': str(script)}, line=2, current=True))
    assert color(0, 1) == '#ffffff' and color(1, 1) == CURRENT_LINE
    for status, expected in (('SUCCESS', '#00ff00'), ('FAILED', '#ff0000'), ('WARNING', '#ffd166')):
        run.apply(dict(kind='line', source={'path': str(script)}, line=2, status=status))
        assert color(1, 5) == expected and color(1, 1) == CURRENT_LINE
        assert model.data(model.index(1, 1), Qt.ForegroundRole).name() == '#000000'
    run.apply(dict(kind='line', source={'path': str(child)}, line=1, current=True))
    assert all(color(row, 1) == '#ffffff' for row in range(3))
    model.display(run, child)
    assert color(0, 1) == CURRENT_LINE
    # Native completion can precede the adapter's final export/exit acknowledgement.
    for status in ('FINISHED', 'ERROR', 'ABORTED'):
        run.status = status
        assert color(0, 1) == '#ffffff'
    run.active = False
    run.status = 'RUNNING'
    assert color(0, 1) == '#ffffff'
    model.display(run, script)
    assert color(1, 5) == '#ffd166'


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
    # A native abort can acknowledge clean process shutdown with exit code zero.
    controller.finished.emit(0); assert view.selected.status == 'Aborted'
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


def test_spell_layout_hides_python_panels_and_restores_previous_layout(app, tmp_path, monkeypatch):
    from openbexi_ide.app import MainWindow
    monkeypatch.setattr(MainWindow, 'discover_backends', lambda self: None)
    view = MainWindow(tmp_path, QSettings(str(tmp_path / 'prefs.ini'), QSettings.IniFormat))
    view.backend_choices = [dict(id='spell', label='SPELL', procedureWorkspace=True, sourceModules=['spell'])]
    view.populate_backends(); view.show(); app.processEvents()
    script = tmp_path / 'main.py'; script.write_text('import spell\n')
    view.open_file(script)
    assert view.editor_panel.isHidden() and not view.output_tabs.isTabVisible(0)
    assert not view.output_tabs.isTabVisible(1)
    view.procedure_workspace.begin(LaunchSpec(tmp_path, script, language='spell'), 'Run')
    assert view.project_panel.isHidden()
    assert view.output_tabs.currentWidget() is view.procedure_workspace
    view.report_error('Native validation error')
    assert view.output_tabs.currentWidget() is view.procedure_workspace
    view.procedure_workspace.finish(0)
    view.language.setCurrentIndex(view.language.findData('python')); app.processEvents()
    assert not view.editor_panel.isHidden() and not view.project_panel.isHidden()
    assert view.output_tabs.isTabVisible(0) and view.output_tabs.isTabVisible(1)
    view.close()
