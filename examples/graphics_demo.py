"""An animated dashboard with signal history, distribution and a phase portrait.

Requires PySide6-Essentials in the selected interpreter. No SPELL or server.
The optional stdin JSON commands are used by test_menu.py for start/update/close.
"""
import argparse
import json
import os
import queue
import sys
import threading

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


"""Reusable widgets for the animated graphics_demo.py example."""
from collections import deque
import math
import statistics

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
)


class Samples:
    def __init__(self):
        self.values, self.reference = deque(maxlen=120), deque(maxlen=120)
        self.ticks, self.amplitude = 0, 35

    def add(self, value=None):
        if value is None:
            value = 50 + self.amplitude * math.sin(self.ticks / 9) + 5 * math.sin(self.ticks / 2)
        try:
            value = float(value)
        except (TypeError, ValueError, OverflowError):
            return False
        if not math.isfinite(value):
            return False
        self.values.append(max(0, min(100, value)))
        self.reference.append(50 + 25 * math.cos(self.ticks / 12))
        self.ticks += 1
        return True

    def reset(self):
        self.values.clear()
        self.reference.clear()
        self.ticks = 0
        for _ in range(30):
            self.add()


class Plot(QWidget):
    def __init__(self, samples, kind):
        super().__init__()
        self.samples, self.kind = samples, kind
        self.show_reference = True
        self.setMinimumSize(280, 180)
        self.setAccessibleName(kind)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor('#ffffff'))
        painter.setPen(QColor('#24364b'))
        painter.drawText(16, 24, self.kind)
        rect = QRectF(self.rect()).adjusted(42, 42, -20, -28)
        values, reference = list(self.samples.values), list(self.samples.reference)
        if not values:
            return
        bins = [0] * 10
        for value in values:
            bins[min(9, int(value // 10))] += 1
        maximum = max(bins) if self.kind == 'Distribution' else 100
        painter.setPen(QPen(QColor('#e5ebf1'), 1))
        for level in range(5):
            y = rect.bottom() - rect.height() * level / 4
            painter.setPen(QPen(QColor('#e5ebf1'), 1))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.setPen(QColor('#64748b'))
            painter.drawText(QRectF(2, y - 9, 32, 18), Qt.AlignRight, f'{maximum * level / 4:g}')
        if self.kind == 'Signal history':
            self.line(painter, rect, values, '#2563eb', fill=True)
            if self.show_reference:
                self.line(painter, rect, reference, '#d97706')
            caption = f'Last {len(values)} samples · blue signal / amber reference'
        elif self.kind == 'Distribution':
            width = rect.width() / 10
            for index, count in enumerate(bins):
                height = rect.height() * count / maximum
                painter.fillRect(QRectF(rect.left() + index * width + 2,
                    rect.bottom() - height, width - 4, height), QColor('#0d9488'))
            caption = 'Value bins 0–100 · vertical axis is sample count'
        else:
            for index, (x, y) in enumerate(zip(values, reference)):
                color = QColor('#7c3aed')
                color.setAlpha(35 + int(210 * (index + 1) / len(values)))
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                point = QPointF(rect.left() + rect.width() * x / 100,
                                rect.bottom() - rect.height() * y / 100)
                painter.drawEllipse(point, 3.5, 3.5)
            caption = 'Signal → · reference ↑ · brighter points are newer'
        painter.setPen(QColor('#64748b'))
        painter.drawText(42, self.height() - 7,
                         painter.fontMetrics().elidedText(caption, Qt.ElideRight, int(rect.width())))

    @staticmethod
    def line(painter, rect, values, color, fill=False):
        path = QPainterPath()
        for index, value in enumerate(values):
            point = QPointF(rect.left() + rect.width() * index / max(1, len(values) - 1),
                            rect.bottom() - rect.height() * value / 100)
            if index:
                path.lineTo(point)
            else:
                path.moveTo(point)
        if fill:
            area = QPainterPath(path)
            area.lineTo(rect.right(), rect.bottom())
            area.lineTo(rect.left(), rect.bottom())
            area.closeSubpath()
            shade = QColor(color)
            shade.setAlpha(22)
            painter.fillPath(area, shade)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(color), 2.5))
        painter.drawPath(path)


class Dashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Local sample statistics')
        self.setStyleSheet('QWidget {font: 13px "DejaVu Sans"; background: #f1f5f9; color: #24364b;}'
            'QPushButton {border: 1px solid #cbd5e1; border-radius: 6px; padding: 8px 14px; background: white;}'
            'QPushButton:checked {background: #dbeafe; border-color: #2563eb;}'
            'QLabel#headline {font-size: 22px; font-weight: bold;}'
            'QLabel#summary {background: white; padding: 12px; border-radius: 6px;}')
        self.samples = Samples()
        self.samples.reset()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        title = QLabel('Signal laboratory'); title.setObjectName('headline')
        layout.addWidget(title)
        layout.addWidget(QLabel('Explore two generated signals. Changes update every chart and statistic.'))
        self.summary = QLabel(); self.summary.setObjectName('summary')
        layout.addWidget(self.summary)
        grid = QGridLayout()
        self.plots = [Plot(self.samples, kind) for kind in ('Signal history', 'Distribution', 'Phase portrait')]
        grid.addWidget(self.plots[0], 0, 0, 1, 2)
        grid.addWidget(self.plots[1], 1, 0)
        grid.addWidget(self.plots[2], 1, 1)
        layout.addLayout(grid, 1)
        controls = QHBoxLayout()
        self.play = QPushButton('Pause'); self.play.setCheckable(True); self.play.setChecked(True)
        self.play.toggled.connect(self.set_playing)
        self.add_button = QPushButton('Add point'); self.add_button.clicked.connect(lambda: self.advance())
        self.reset_button = QPushButton('Reset'); self.reset_button.clicked.connect(self.reset)
        self.reference = QCheckBox('Reference line'); self.reference.setChecked(True)
        self.reference.toggled.connect(self.toggle_reference)
        self.close_button = QPushButton('Close'); self.close_button.clicked.connect(self.close)
        for widget in (self.play, self.add_button, self.reset_button, self.reference):
            controls.addWidget(widget)
        controls.addStretch(); controls.addWidget(self.close_button)
        layout.addLayout(controls)
        sliders = QHBoxLayout()
        self.speed = QSlider(Qt.Horizontal); self.speed.setRange(1, 20); self.speed.setValue(5)
        self.speed.setAccessibleName('Samples per second')
        self.speed_label = QLabel('5 samples/s'); self.speed.valueChanged.connect(self.change_speed)
        self.amplitude = QSlider(Qt.Horizontal); self.amplitude.setRange(0, 45); self.amplitude.setValue(35)
        self.amplitude.setAccessibleName('Signal amplitude')
        self.amplitude_label = QLabel('Amplitude 35'); self.amplitude.valueChanged.connect(self.change_amplitude)
        for widget in (self.speed_label, self.speed, self.amplitude_label, self.amplitude):
            sliders.addWidget(widget)
        layout.addLayout(sliders)
        self.timer = QTimer(self); self.timer.timeout.connect(self.advance); self.timer.start(200)
        self.refresh(); self.resize(900, 720)

    def refresh(self):
        values = self.samples.values
        self.summary.setText(f'Current {values[-1]:5.1f}     Mean {statistics.fmean(values):5.1f}     '
            f'Min {min(values):5.1f}     Max {max(values):5.1f}     σ {statistics.pstdev(values):4.1f}     '
            f'Generated {self.samples.ticks}')
        for plot in self.plots:
            plot.update()

    def advance(self, value=None):
        if self.samples.add(value):
            self.refresh()

    def reset(self):
        self.samples.reset(); self.refresh()

    def set_playing(self, playing):
        self.play.setText('Pause' if playing else 'Resume')
        self.timer.start() if playing else self.timer.stop()

    def change_speed(self, value):
        self.speed_label.setText(f'{value} samples/s'); self.timer.setInterval(round(1000 / value))

    def change_amplitude(self, value):
        self.samples.amplitude = value; self.amplitude_label.setText(f'Amplitude {value}')

    def toggle_reference(self, visible):
        self.plots[0].show_reference = visible; self.plots[0].update()

    def command(self, command):
        if not isinstance(command, dict):
            return
        action = command.get('action')
        if action == 'close':
            self.close()
        elif action == 'add':
            self.advance(command.get('value', 50))
        elif action == 'reset':
            self.reset()
        elif action in ('pause', 'resume'):
            self.play.setChecked(action == 'resume')

    def closeEvent(self, event):
        self.timer.stop()
        if hasattr(self, 'command_timer'):
            self.command_timer.stop()
        event.accept()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--close-after", type=int, help="Close automatically after this many milliseconds")
    parser.add_argument("--commands", action="store_true", help="Accept menu commands on stdin")
    args = parser.parse_args()
    app = QApplication([])
    window = Dashboard()
    if args.commands:
        commands = queue.Queue(maxsize=256)
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
        timer = window.command_timer = QTimer(window)
        def poll():
            for _ in range(20):
                try: command = commands.get_nowait()
                except queue.Empty: break
                window.command(command)
        timer.timeout.connect(poll); timer.start(50)
    if args.close_after is not None: QTimer.singleShot(max(1, args.close_after), window.close)
    window.show()
    print("Statistics window opened", flush=True)
    result = app.exec()
    print("Statistics window closed", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
