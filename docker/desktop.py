"""Persistent launch surface underneath the test IDE windows."""
import os
from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget


VIEWS = (
    ('local', 'Python IDE', 'Local Run, Debug and graphics'),
    ('alice', 'SPELL / DSS — Alice', 'Shared developer; open dss_demo.py'),
    ('monitor', 'Read-only monitor', 'Watch shared output and live stacks'),
    ('bob', 'Shared developer — Bob', 'Test controller handoff and queues'),
    ('durable', 'Durable Python', 'Committed sources and persistent sessions'),
    ('durable-monitor', 'Durable monitor', 'Read-only view of the durable session'),
    ('terminal', 'Terminal', 'CLI commands and project files'),
)


class Desktop(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnBottomHint)
        self.setAttribute(Qt.WidgetAttribute.WA_X11NetWmWindowTypeDesktop)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setWindowTitle('OpenBEXI Test Desktop')
        self.setObjectName('desktop')
        self.child_processes = []
        self.setStyleSheet('''
            QWidget#desktop { background: #e9edf3; color: #182b45; }
            QLabel { color: #182b45; font-family: "DejaVu Sans"; }
            QLabel#heading { font-size: 32px; font-weight: bold; }
            QLabel#subtitle { font-size: 16px; }
            QPushButton { background: white; color: #182b45; border: 1px solid #becada;
                          border-radius: 10px; padding: 20px; text-align: left;
                          font-family: "DejaVu Sans"; font-size: 16px; }
            QPushButton:hover { background: #dcecff; border-color: #4982bf; }
            QPushButton:focus { border: 2px solid #286fbc; }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 50, 60, 50)
        layout.addStretch()
        heading = QLabel('OpenBEXI IDE')
        heading.setObjectName('heading')
        layout.addWidget(heading)
        subtitle = QLabel('Choose a window to start testing. You can return here after closing an IDE.')
        subtitle.setObjectName('subtitle')
        layout.addWidget(subtitle)
        layout.addSpacing(24)
        grid = QGridLayout()
        grid.setSpacing(16)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.buttons = {}
        for index, (view, title, description) in enumerate(VIEWS):
            button = QPushButton(title + '\n' + description)
            button.setMinimumHeight(100)
            button.clicked.connect(lambda _checked=False, selected=view: self.launch(selected))
            grid.addWidget(button, index // 3, index % 3)
            self.buttons[view] = button
            action = QAction(title, self)
            action.triggered.connect(lambda _checked=False, selected=view: self.launch(selected))
            self.addAction(action)
        layout.addLayout(grid)
        layout.addSpacing(20)
        self.status = QLabel('SPELL test: open Alice, claim control, open dss_demo.py, choose SPELL plugin, then Run.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.reap)
        self.timer.start()
        screen = QApplication.primaryScreen()
        self.setGeometry(screen.geometry())
        screen.geometryChanged.connect(self.setGeometry)

    def launch(self, view):
        try:
            log_directory = Path('/workspace/logs')
            log_directory.mkdir(parents=True, exist_ok=True)
            with (log_directory / ('ide-' + view + '.log')).open('ab', buffering=0) as log:
                process = subprocess.Popen(['openbexi-lab', view], stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=True)
            self.child_processes.append((view, process))
            self.status.setText('Opening ' + dict((v, title) for v, title, _ in VIEWS)[view] + '…')
        except OSError as error:
            self.status.setText('Could not open the window: ' + str(error))

    def reap(self):
        for view, process in list(self.child_processes):
            code = process.poll()
            if code is not None:
                self.child_processes.remove((view, process))
                self.status.setText('Window closed. Choose a window to continue testing.' if code == 0
                                    else f'Window exited ({code}). Details: /workspace/logs/ide-{view}.log')

    def closeEvent(self, event):
        # This is the desktop, not one of the independently closable IDEs.
        event.ignore()


def main():
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    desktop = Desktop()
    desktop.show()
    QTimer.singleShot(0, lambda: Path('/tmp/openbexi-desktop.pid').write_text(str(os.getpid())))
    if '--no-initial-ide' not in sys.argv:
        QTimer.singleShot(0, lambda: desktop.launch('local'))
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
