from pathlib import Path
import runpy

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from openbexi_runtime.launch import LaunchSpec
from test_runtime import capture


EXAMPLES = Path(__file__).resolve().parents[1] / 'examples/test_python_support'


def test_python_in_depth_runs_all_chapters_and_streams():
    code, stdout, stderr = capture(LaunchSpec(EXAMPLES, EXAMPLES / 'test_Python_in_deep.py',
        arguments=('--stream', '3', '--delay', '0')), timeout=30)
    assert code == 0, stderr + stdout
    assert '15 chapters passed' in stdout and stdout.count('  PASS') == 15
    assert 'Live output 000003/000003' in stdout


def test_graphics_controls_animation_invalid_input_and_close(app):
    dashboard = runpy.run_path(str(EXAMPLES / 'graphics_demo.py'))['Dashboard']()
    dashboard.show()
    app.processEvents()
    try:
        QTest.mouseClick(dashboard.play, Qt.LeftButton)
        assert not dashboard.timer.isActive()
        previous = dashboard.samples.ticks
        QTest.qWait(250)
        assert dashboard.samples.ticks == previous
        QTest.mouseClick(dashboard.add_button, Qt.LeftButton)
        assert dashboard.samples.ticks == previous + 1
        for invalid in ('bad', float('nan'), float('inf'), {}, []):
            dashboard.command({'action': 'add', 'value': invalid})
        assert dashboard.samples.ticks == previous + 1
        dashboard.command({'action': 'add', 'value': 110})
        assert dashboard.samples.values[-1] == 100
        dashboard.command({'action': 'add', 'value': -10})
        assert dashboard.samples.values[-1] == 0
        for _ in range(150):
            dashboard.advance()
        assert len(dashboard.samples.values) == 120 and len(set(dashboard.samples.values)) > 100
        dashboard.speed.setValue(20)
        dashboard.amplitude.setValue(0)
        assert dashboard.timer.interval() == 50 and dashboard.samples.amplitude == 0
        QTest.mouseClick(dashboard.reference, Qt.LeftButton)
        assert not dashboard.plots[0].show_reference
        QTest.mouseClick(dashboard.reset_button, Qt.LeftButton)
        assert dashboard.samples.ticks == 30 and len(dashboard.samples.values) == 30
        dashboard.command({'action': 'resume'})
        assert dashboard.timer.isActive()
        QTest.qWait(125)
        assert dashboard.samples.ticks > 30
        app.processEvents()
        assert not dashboard.grab().isNull()
        QTest.mouseClick(dashboard.close_button, Qt.LeftButton)
        assert not dashboard.isVisible() and not dashboard.timer.isActive()
    finally:
        dashboard.close()
