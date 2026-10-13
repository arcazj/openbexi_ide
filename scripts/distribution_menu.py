"""Exercise packaged menu input through installed Qt Run and Debug controls."""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import sys
import time
import traceback

from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import openbexi_ide
from openbexi_ide.app import MainWindow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--examples', required=True, type=Path)
    args = parser.parse_args()
    evidence = args.output.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    app = QApplication.instance() or QApplication([])
    assert Path(openbexi_ide.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    report = {'passed':False, 'version':version('openbexi-ide'), 'origin':openbexi_ide.__file__,
              'interpreter':sys.executable, 'checks':[],
              'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'examples':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in args.examples.glob('*.py')},
              'qt_platform':app.platformName(),
              'scope':f'Actual installed Qt controls using {app.platformName()}; copied packaged examples; no live noVNC claim'}
    try:
        for mode in ('Run', 'Debug'):
            project = evidence / (mode + ' examples with spaces')
            shutil.copytree(args.examples, project)
            view = MainWindow(project, QSettings(str(evidence/(mode+'.ini')), QSettings.IniFormat))
            view.show()

            def wait(predicate, timeout=60):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    app.processEvents()
                    if predicate():
                        return
                    time.sleep(.01)
                raise AssertionError(view.console.toPlainText())

            def send(value, button):
                # A graphics child can own the desktop focus. Direct QTest
                # events bypass the window manager's real click activation.
                # Model returning to the IDE before entering the next answer.
                view.raise_()
                view.activateWindow()
                wait(view.isActiveWindow)
                assert view.input.isEnabled() and view.send_button.isEnabled()
                previous = view.console.toPlainText().count('Choose: ')
                view.input.setText(value)
                if button:
                    QTest.mouseClick(view.send_button, Qt.LeftButton)
                else:
                    QTest.keyClick(view.input, Qt.Key_Return)
                assert not view.input.text() and view.input.hasFocus()
                return previous

            def menu(previous):
                wait(lambda: view.console.toPlainText().count('Choose: ') > previous)

            try:
                view.open_file(project/'test_menu.py')
                (view.run_action if mode=='Run' else view.debug_action).trigger()
                wait(lambda: 'Choose: ' in view.console.toPlainText())
                view.raise_()
                view.activateWindow()
                wait(view.isActiveWindow)
                view.console.setFocus()
                QTest.keyClicks(view.console, '2')
                assert view.input.text() == '2'
                previous = view.console.toPlainText().count('Choose: ')
                QTest.keyClick(view.input, Qt.Key_Return)
                menu(previous)
                assert 'stdlib-import-sweep' in view.console.toPlainText()
                previous = send('3', True)
                wait(lambda: 'Topic name: ' in view.console.toPlainText())
                send('types', False)
                menu(previous)
                previous = send('4', True)
                wait(lambda: 'Statistics window opened' in view.console.toPlainText())
                menu(previous)
                previous = send('5', False)
                wait(lambda: 'Value (0' in view.console.toPlainText())
                send('42', True)
                menu(previous)
                menu(send('6', False))
                assert 'Statistics window closed' in view.console.toPlainText()
                menu(send('1', True))
                assert '39 topic(s)' in view.console.toPlainText()
                assert view.console.toPlainText().count('Qualification exit: 0') == 3
                menu(send('7', False))
                assert '15 chapters passed' in view.console.toPlainText()
                assert 'Python in depth exit: 0' in view.console.toPlainText()
                send('0', True)
                wait(lambda: not view.is_busy())
                assert 'exit 0' in view.console.toPlainText()
                report['checks'].append(f'{mode}: console typing, Send/Return, menu 1–7, nested prompts, graphics close and exit')
            finally:
                (evidence/(mode+'-console.txt')).write_text(view.console.toPlainText(),encoding='utf-8')
                view.stop_script()
                wait(lambda: not view.is_busy())
                view.close()
                app.processEvents()
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    (evidence/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
