"""Drive the shipped interactive menu through real Run/Debug stdin widgets."""
from pathlib import Path
import shutil
import time

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest

from openbexi_ide.app import MainWindow


@pytest.mark.parametrize('debug', [False, True], ids=['run', 'debug'])
def test_menu_send_and_return_all_options(app, tmp_path, debug):
    project = tmp_path / 'examples with spaces'
    shutil.copytree(Path(__file__).resolve().parents[1] / 'examples', project)
    view = MainWindow(project, QSettings(str(tmp_path/'preferences.ini'), QSettings.IniFormat))
    view.show()

    def wait(predicate, timeout=45):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            time.sleep(.01)
        raise AssertionError(view.console.toPlainText())

    def send(value, *, button):
        assert view.input.isEnabled() and view.send_button.isEnabled()
        before = view.console.toPlainText().count('Choose: ')
        view.input.setText(value)
        if button:
            QTest.mouseClick(view.send_button, Qt.LeftButton)
        else:
            QTest.keyClick(view.input, Qt.Key_Return)
        assert not view.input.text()
        return before

    def menu_after(before):
        wait(lambda: view.console.toPlainText().count('Choose: ') > before)

    try:
        view.open_file(project/'test_python_support/python_menu.py')
        (view.debug_action if debug else view.run_action).trigger()
        wait(lambda: 'Choose: ' in view.console.toPlainText())
        view.console.setFocus()
        QTest.keyClicks(view.console, '2')
        assert view.input.text() == '2', 'Typing at the visible prompt must reach stdin'
        menu_after(send('2', button=True))
        assert view.input.hasFocus(), 'Send must leave the next answer ready to type'
        assert 'stdlib-import-sweep' in view.console.toPlainText()
        before = send('3', button=False)
        wait(lambda: 'Topic name: ' in view.console.toPlainText())
        send('types', button=True)
        menu_after(before)
        assert 'Qualification exit: 0' in view.console.toPlainText()
        before = send('4', button=False)
        wait(lambda: 'Statistics window opened' in view.console.toPlainText())
        menu_after(before)
        before = send('5', button=True)
        wait(lambda: 'Value (0' in view.console.toPlainText())
        send('42', button=False)
        menu_after(before)
        menu_after(send('6', button=True))
        assert 'Statistics window closed' in view.console.toPlainText()
        menu_after(send('1', button=False))
        assert '39 topic(s)' in view.console.toPlainText()
        assert view.console.toPlainText().count('Qualification exit: 0') == 3
        menu_after(send('7', button=True))
        assert '15 chapters passed' in view.console.toPlainText()
        assert 'Python in depth exit: 0' in view.console.toPlainText()
        send('0', button=False)
        wait(lambda: not view.is_busy())
        assert 'exit 0' in view.console.toPlainText()
    finally:
        view.stop_script()
        wait(lambda: not view.is_busy())
        view.close()
        app.processEvents()
