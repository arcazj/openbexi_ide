"""A plain Python statistics window, with update, reset and close controls.

Requires PySide6-Essentials in the selected interpreter. No SPELL or server.
The optional stdin JSON commands are used by test_menu.py for start/update/close.
"""
import argparse
import json
import math
import os
import queue
import sys
import threading

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class Chart(QWidget):
    def __init__(self):
        super().__init__()
        self.values = [50.0]
        self.setMinimumSize(420, 200)

    def add_value(self, value):
        if math.isfinite(float(value)):
            self.values = [*self.values, max(0, min(100, float(value)))][-60:]
            self.update()

    def paintEvent(self, _event):
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(24, 16, -24, -24)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        painter.setPen(QPen(QColor("#e6e8ed"), 1))
        for level in range(5):
            y = rect.bottom() - rect.height() * level / 4
            painter.drawLine(rect.left(), round(y), rect.right(), round(y))
        path = QPainterPath()
        for index, value in enumerate(self.values):
            x = rect.left() + rect.width() * index / max(1, len(self.values) - 1)
            y = rect.bottom() - rect.height() * value / 100
            if index: path.lineTo(x, y)
            else: path.moveTo(x, y)
        painter.setPen(QPen(QColor("#3976dd"), 2.5)); painter.drawPath(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--close-after", type=int, help="Close automatically after this many milliseconds")
    parser.add_argument("--commands", action="store_true", help="Accept menu commands on stdin")
    args = parser.parse_args()
    app = QApplication([])
    window = QWidget(); window.setWindowTitle("Local sample statistics")
    window.setStyleSheet("QWidget {font: 13px 'Segoe UI'; background: #f5f5f7; color: #292b31;}"
        "QPushButton {border: 1px solid #dedfe5; border-radius: 6px; padding: 8px 16px; background: white;}")
    layout = QVBoxLayout(window)
    layout.addWidget(QLabel("Sample statistics · generated locally"))
    chart = Chart(); layout.addWidget(chart)
    buttons = QHBoxLayout()
    add = QPushButton("Add point"); reset = QPushButton("Reset"); close = QPushButton("Close")
    add.clicked.connect(lambda: chart.add_value(50 + 40 * math.sin(len(chart.values) / 3)))
    reset.clicked.connect(lambda: (setattr(chart, "values", [50.0]), chart.update()))
    close.clicked.connect(window.close)
    for button in (add, reset, close): buttons.addWidget(button)
    layout.addLayout(buttons)
    if args.commands:
        commands = queue.SimpleQueue()
        def read_commands():
            pending = b""
            while True:
                try: chunk = os.read(sys.stdin.fileno(), 4096)
                except OSError: return
                if not chunk: commands.put({"action": "close"}); return
                pending = (pending + chunk)[-16384:]
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    try: commands.put(json.loads(line))
                    except ValueError: pass
        threading.Thread(target=read_commands, daemon=True).start()
        timer = QTimer(window)
        def poll():
            for _ in range(20):
                if commands.empty(): break
                command = commands.get()
                if not isinstance(command, dict): continue
                if command.get("action") == "close": window.close()
                elif command.get("action") == "add": chart.add_value(command.get("value", 50))
        timer.timeout.connect(poll); timer.start(50)
    if args.close_after is not None: QTimer.singleShot(max(1, args.close_after), window.close)
    window.resize(620, 330); window.show()
    print("Statistics window opened", flush=True)
    result = app.exec()
    print("Statistics window closed", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
