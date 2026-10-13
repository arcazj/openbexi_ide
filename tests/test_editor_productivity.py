"""Actual Qt keyboard workflows plus source-only resolution boundaries."""
from pathlib import Path
import threading
import time

import pytest
from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtTest import QTest

from openbexi_ide.editor import CodeEditor
from openbexi_ide.navigation import ProjectIndex, parse_module
from openbexi_ide.themes import THEMES


def wait_for(app, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(10)
    assert predicate(), "Editor operation did not finish"


@pytest.fixture
def editor(app, tmp_path):
    path = tmp_path / "main.py"
    path.write_text("pri", encoding="utf-8")
    view = CodeEditor(path, THEMES["light"])
    view.configure_project(tmp_path)
    view.resize(700, 400)
    view.show()
    view.setFocus()
    view.goto_location(1, 3)
    app.processEvents()
    yield view
    QThreadPool.globalInstance().waitForDone(5000)
    app.processEvents()
    view.document().setModified(False)
    view.close()
    view.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("key", [Qt.Key_Return, Qt.Key_Tab])
def test_ctrl_space_builtin_completion_keyboard_insert_and_undo(editor, app, key):
    QTest.keyClick(editor, Qt.Key_Space, Qt.ControlModifier)
    wait_for(app, lambda: editor.completer.popup().isVisible())
    assert editor.completer.popup().currentIndex().data() == "print"
    QTest.keyClick(editor, key)
    assert editor.toPlainText() == "print"
    assert not editor.completer.popup().isVisible()
    editor.undo()
    assert editor.toPlainText() == "pri"


def test_keyboard_selects_completion_and_escape_preserves_source(editor, app):
    editor.setPlainText("property_name = 1\npro")
    editor.goto_location(2, 3)
    QTest.keyClick(editor, Qt.Key_Space, Qt.ControlModifier)
    wait_for(app, lambda: editor.completer.popup().isVisible())
    popup = editor.completer.popup()
    assert popup.currentIndex().data() == "property"
    QTest.keyClick(popup, Qt.Key_Down)
    QTest.keyClick(popup, Qt.Key_Return)
    assert editor.toPlainText().endswith("property_name")
    editor.undo()
    QTest.keyClick(editor, Qt.Key_Space, Qt.ControlModifier)
    wait_for(app, lambda: editor.completer.popup().isVisible())
    QTest.keyClick(editor, Qt.Key_Escape)
    assert editor.toPlainText().endswith("pro")


def test_completion_replaces_whole_word_and_handles_astral_columns(editor, app):
    editor.setPlainText("label = '😀'; printxx")
    editor.goto_location(1, len("label = '😀'; pri"))
    QTest.keyClick(editor, Qt.Key_Space, Qt.ControlModifier)
    wait_for(app, lambda: editor.completer.popup().isVisible())
    QTest.keyClick(editor, Qt.Key_Tab)
    assert editor.toPlainText() == "label = '😀'; print"


def test_f12_resolves_project_import_and_unsaved_target_without_execution(editor, app, tmp_path):
    target = tmp_path / "tools.py"
    marker = tmp_path / "must-not-exist"
    target.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError('not imported')\n"
                      "def saved():\n    pass\n", encoding="utf-8")
    unsaved = "# unsaved change\n\ndef calculate(value):\n    return value * 2\n"
    editor.configure_project(tmp_path, lambda: {target: unsaved})
    editor.setPlainText("from tools import calculate as compute\ncompute(21)\n")
    editor.goto_location(2, 4)
    locations = []
    editor.navigation_requested.connect(lambda *args: locations.append(args))
    QTest.keyClick(editor, Qt.Key_F12)
    wait_for(app, lambda: bool(locations))
    assert locations == [(str(target.resolve()), 3, 4)]
    assert not marker.exists()
    assert "def saved" in target.read_text()


def test_local_shadowing_and_class_attribute_completion(editor, app):
    editor.setPlainText("class Greeter:\n    def welcome(self):\n        return 'hi'\n"
                       "greeter = Greeter()\ngreeter.we")
    editor.goto_location(5, 10)
    QTest.keyClick(editor, Qt.Key_Space, Qt.ControlModifier)
    wait_for(app, lambda: editor.completer.popup().isVisible())
    assert editor.completer.popup().currentIndex().data() == "welcome"
    QTest.keyClick(editor, Qt.Key_Return)
    assert editor.toPlainText().endswith("greeter.welcome")
    source = "value = 1\ndef f(value):\n    return value\n"
    index = ProjectIndex(editor.project, {editor.path: source})
    result = index.definition(editor.path, source, 3, 13)
    assert (result.line, result.kind) == (2, "parameter")


def test_symbols_search_keyboard_and_read_only_navigation(editor, app, tmp_path):
    target = tmp_path / "utilities.py"
    target.write_text("class Utility:\n    def transform(self):\n        return 42\n", encoding="utf-8")
    locations = []
    editor.navigation_requested.connect(lambda *args: locations.append(args))
    editor.setReadOnly(True)
    QTest.keyClick(editor, Qt.Key_O, Qt.ControlModifier | Qt.ShiftModifier)
    wait_for(app, lambda: editor.symbol_dialog is not None)
    dialog = editor.symbol_dialog
    QTest.keyClicks(dialog.search, "transform utilities")
    assert dialog.results.count() == 1
    QTest.keyClick(dialog.search, Qt.Key_Return)
    wait_for(app, lambda: bool(locations))
    assert locations[0] == (str(target.resolve()), 2, 8)
    assert editor.toPlainText() == "pri"


def test_read_only_blocks_pending_and_open_completion_insertion(editor, app):
    editor.request_completion()
    editor.setReadOnly(True)
    wait_for(app, lambda: not editor._analysis_jobs)
    assert not editor.completer.popup().isVisible()
    editor._insert_completion("print")
    assert editor.toPlainText() == "pri"
    editor.setReadOnly(False)
    editor.request_completion()
    wait_for(app, lambda: editor.completer.popup().isVisible())
    editor.setReadOnly(True)
    assert not editor.completer.popup().isVisible()
    editor._insert_completion("print")
    QTest.keyClick(editor, Qt.Key_Space, Qt.ControlModifier)
    assert not editor._analysis_jobs
    assert editor.toPlainText() == "pri"


def test_analysis_runs_off_gui_thread_and_discards_stale_result(editor, app, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = ProjectIndex.complete
    worker_threads = []

    def delayed(index, *args):
        worker_threads.append(threading.get_ident())
        entered.set()
        assert release.wait(5)
        return original(index, *args)

    monkeypatch.setattr(ProjectIndex, "complete", delayed)
    try:
        editor.request_completion()
        wait_for(app, entered.is_set)
        QTest.keyClicks(editor, "nt")
        assert editor.toPlainText() == "print"
        assert worker_threads == [worker_threads[0]]
        assert worker_threads[0] != threading.get_ident()
    finally:
        release.set()
    wait_for(app, lambda: not editor._analysis_jobs)
    assert not editor.completer.popup().isVisible()


def test_relative_src_package_and_unknown_definition(tmp_path):
    package = tmp_path / "src" / "package"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "helpers.py").write_text("def calculate():\n    pass\n")
    main = package / "main.py"
    source = "from .helpers import calculate\ncalculate()\n"
    index = ProjectIndex(tmp_path, {main: source})
    result = index.definition(main, source, 2, 4)
    assert result.path == package / "helpers.py"
    assert index.definition(main, "unknown", 1, 4) is None


def test_dotted_namespace_import_and_reexports_are_source_only(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    helper = package / "helpers.py"
    helper.write_text("def calculate():\n    pass\n")
    main = tmp_path / "main.py"
    source = "import package.helpers\npackage.helpers.calculate()\n"
    index = ProjectIndex(tmp_path, {main: source})
    result = index.definition(main, source, 2, 20)
    assert (result.path, result.line) == (helper, 1)
    (package / "__init__.py").write_text("from .helpers import calculate as exported\n")
    source = "from package import exported\nexported()\n"
    index = ProjectIndex(tmp_path, {main: source})
    result = index.definition(main, source, 2, 4)
    assert result.path == helper


def test_cyclic_imports_and_aliases_finish_without_execution(tmp_path):
    first, second = tmp_path / "first.py", tmp_path / "second.py"
    first.write_text("from second import function\nx = y\ny = x\n")
    second.write_text("from first import function\n")
    source = "from first import function\nfunction()\n"
    main = tmp_path / "main.py"
    index = ProjectIndex(tmp_path, {main: source})
    assert index.definition(main, source, 2, 3) is not None
    assert index.complete(first, "x.", 1, 2) == []


def test_incomplete_buffer_recovery_and_project_bounds(tmp_path):
    main = tmp_path / "main.py"
    source = "def available():\n    pass\navailable.\n"
    index = ProjectIndex(tmp_path, {main: source})
    assert any(symbol.name == "available" for symbol in index.symbols())
    assert index.load(tmp_path.parent / "outside.py") is None
    ignored = tmp_path / ".venv"
    ignored.mkdir()
    (ignored / "library.py").write_text("def ignored(): pass\n")
    assert not any(symbol.name == "ignored" for symbol in index.symbols())
    assert parse_module(main, "\0").symbols == []


def test_shortcut_burst_coalesces_work(editor, app, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = ProjectIndex.complete
    calls = []

    def delayed(index, *args):
        calls.append(1)
        entered.set()
        assert release.wait(5)
        return original(index, *args)

    monkeypatch.setattr(ProjectIndex, "complete", delayed)
    try:
        editor.request_completion()
        wait_for(app, entered.is_set)
        for _ in range(25):
            QTest.keyClick(editor, Qt.Key_Space, Qt.ControlModifier)
        assert len(editor._analysis_jobs) == 1
        assert editor._queued_analysis is not None
    finally:
        release.set()
    wait_for(app, lambda: not editor._analysis_jobs and editor._queued_analysis is None)
    assert len(calls) == 2


def test_closing_editor_during_analysis_does_not_open_late_popup(editor, app, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = ProjectIndex.complete

    def delayed(index, *args):
        entered.set()
        assert release.wait(5)
        return original(index, *args)

    monkeypatch.setattr(ProjectIndex, "complete", delayed)
    try:
        editor.request_completion()
        wait_for(app, entered.is_set)
        editor.close()
        assert not editor.isVisible()
    finally:
        release.set()
    wait_for(app, lambda: not editor._analysis_jobs)
    assert not editor.completer.popup().isVisible()


def test_project_escape_symlink_is_not_indexed(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "private.py"
    outside.write_text("def private_definition(): pass\n")
    linked = project / "linked.py"
    try:
        linked.symlink_to(outside)
    except OSError:
        pytest.skip("This account cannot create symlinks")
    main = project / "main.py"
    source = "from linked import private_definition\nprivate_definition()\n"
    index = ProjectIndex(project, {main: source})
    assert index.definition(main, source, 2, 5) is None
    assert not any(symbol.name == "private_definition" and symbol.path == outside
                   for symbol in index.symbols())


def test_project_size_limits_are_reported_and_analysis_recovers(tmp_path, monkeypatch):
    import openbexi_ide.navigation as navigation
    first, second = tmp_path / "first.py", tmp_path / "second.py"
    first.write_text("def first_function(): pass\n")
    second.write_text("def second_function(): pass\n")
    monkeypatch.setattr(navigation, "MAX_FILES", 1)
    limited = ProjectIndex(tmp_path)
    assert len(limited.symbols()) == 1
    assert limited.limited
    monkeypatch.setattr(navigation, "MAX_FILES", 2000)
    fresh = ProjectIndex(tmp_path)
    assert {symbol.name for symbol in fresh.symbols()} == {"first_function", "second_function"}
    assert not fresh.limited


def test_main_window_shortcuts_follow_unsaved_definition_and_preserve_tabs(app, tmp_path):
    from PySide6.QtCore import QSettings
    from openbexi_ide.app import MainWindow
    target = tmp_path / "helpers.py"
    target.write_text("def saved(): pass\n")
    main = tmp_path / "main.py"
    main.write_text("from helpers import calculate\ncalculate()\npri")
    window = MainWindow(tmp_path, QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    window.show()
    try:
        helper_editor = window.open_file(target)
        helper_editor.selectAll()
        helper_editor.insertPlainText("# unsaved\n\ndef calculate():\n    return 42\n")
        source_editor = window.open_file(main)
        source_editor.goto_location(3, 3)
        app.processEvents()
        QTest.keyClick(source_editor, Qt.Key_Space, Qt.ControlModifier)
        wait_for(app, lambda: source_editor.completer.popup().isVisible())
        QTest.keyClick(source_editor, Qt.Key_Return)
        assert source_editor.toPlainText().endswith("print")
        source_editor.goto_location(2, 4)
        QTest.keyClick(source_editor, Qt.Key_F12)
        wait_for(app, lambda: window.current_editor() is helper_editor)
        assert helper_editor.textCursor().blockNumber() == 2
        assert helper_editor.textCursor().positionInBlock() == 4
        assert helper_editor.document().isModified()
        assert target.read_text() == "def saved(): pass\n"
        assert window.tabs.count() == 2
    finally:
        for index in range(window.tabs.count()):
            window.tabs.widget(index).document().setModified(False)
        window.close()
        app.processEvents()
