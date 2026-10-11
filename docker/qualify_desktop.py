"""Check the launcher on its own X11 display, without touching the user's windows."""
import argparse
import json
import os
from pathlib import Path
import runpy
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=True)
    assert not Path('/tmp/.X11-unix/X99').exists(), 'Qualification display is already in use'
    os.environ['DISPLAY'] = ':99'
    os.environ['QT_QPA_PLATFORM'] = 'xcb'
    with (output / 'launcher-display.log').open('wb') as log:
        display = subprocess.Popen(['Xvfb', ':99', '-screen', '0', '1600x1000x24',
                                    '-nolisten', 'tcp', '-ac', '-s', '0'], stdout=log, stderr=subprocess.STDOUT)
    manager = desktop = None
    try:
        deadline = time.monotonic() + 10
        while not Path('/tmp/.X11-unix/X99').exists():
            assert display.poll() is None and time.monotonic() < deadline
            time.sleep(0.05)
        manager = subprocess.Popen(['openbox', '--config-file', '/opt/test-lab/openbox.xml'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        desktop = runpy.run_path('/opt/test-lab/desktop.py')['Desktop']()
        desktop.show()

        def wait(predicate):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                app.processEvents()
                if predicate():
                    return
                QTest.qWait(25)
            raise AssertionError('Launcher condition did not arrive')

        def windows():
            return subprocess.check_output(['xwininfo', '-root', '-tree'], text=True)

        def background_visible():
            frame = app.primaryScreen().grabWindow(0).toImage()
            return not frame.isNull() and frame.pixelColor(10, 10).name() == '#e9edf3'

        wait(lambda: 'OpenBEXI Test Desktop' in windows() and background_visible())
        assert app.primaryScreen().grabWindow(0).save(str(output / 'launcher.png'))
        desktop.close()
        app.processEvents()
        assert desktop.isVisible(), 'The desktop must survive its own close request'

        # Real button -> installed CLI launcher -> independent Qt IDE process.
        QTest.mouseClick(desktop.buttons['alice'], Qt.MouseButton.LeftButton)
        wait(lambda: 'demo — OpenBEXI IDE' in windows())
        view, child = desktop.child_processes[-1]
        assert view == 'alice' and child.poll() is None
        child.terminate()
        child.wait(timeout=5)
        wait(lambda: not desktop.child_processes and 'demo — OpenBEXI IDE' not in windows())
        wait(background_visible)
        assert desktop.isVisible()
        assert app.primaryScreen().grabWindow(0).save(str(output / 'launcher-after-ide-exit.png'))

        QTest.mouseClick(desktop.buttons['local'], Qt.MouseButton.LeftButton)
        wait(lambda: 'demo — OpenBEXI IDE' in windows())
        result = {'passed': True, 'platform': app.platformName(),
                  'checks': ['visible X11 desktop background and launch buttons',
                             'desktop survives close request', 'Alice button starts real installed IDE',
                             'desktop remains visible after IDE process exits',
                             'Python button reopens a real installed IDE']}
        (output / 'launcher-check.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
    finally:
        if desktop is not None:
            for _, child in desktop.child_processes:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=5)
            desktop.hide()
        if manager is not None:
            manager.terminate()
            manager.wait(timeout=5)
        display.terminate()
        display.wait(timeout=5)


if __name__ == '__main__':
    main()
