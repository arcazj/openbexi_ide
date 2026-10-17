"""Launch the installed IDE and passively record browser-delivered Qt events.

There are no QtTest calls, event injections, action triggers, scroll setters or
input setters. Initial project/file selection is fixture setup only.
"""
import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import sys
import time

from PySide6.QtCore import QObject,QEvent,QSettings,QTimer
from PySide6.QtWidgets import QApplication
import openbexi_ide
from openbexi_ide.app import MainWindow


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--project',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    app=QApplication([])
    window=MainWindow(args.project,QSettings(str(args.output/'settings.ini'),QSettings.IniFormat))
    menu_path = args.project/'test_python_support/python_menu.py'
    window.open_file(menu_path if menu_path.is_file() else args.project/'test_menu.py')
    window.show()
    events=[]
    types={QEvent.Type.Wheel,QEvent.Type.KeyPress,QEvent.Type.MouseButtonPress,QEvent.Type.Close}
    class Observer(QObject):
        def eventFilter(self,target,event):
            if event.type() in types:
                item=dict(time_ns=time.time_ns(),type=event.type().name,target=type(target).__name__,
                    spontaneous=event.spontaneous())
                if event.type()==QEvent.Type.Wheel:item['angle_delta']=[event.angleDelta().x(),event.angleDelta().y()]
                if event.type()==QEvent.Type.KeyPress:item.update(key=event.key(),text=event.text())
                events.append(item)
            return False
    observer=Observer();app.installEventFilter(observer)
    def rectangle(widget):
        point=widget.mapToGlobal(widget.rect().topLeft());r=widget.rect()
        return [point.x(),point.y(),r.width(),r.height()]
    def snapshot(closed=False):
        try:
            scroll=window.console.verticalScrollBar()
            frame=window.frameGeometry()
            toolbars=window.findChildren(__import__('PySide6.QtWidgets',fromlist=['QToolBar']).QToolBar)
            buttons={}
            for name in ('run','debug','stop'):
                for toolbar in toolbars:
                    widget=toolbar.widgetForAction(getattr(window,name+'_action'))
                    if widget is not None:buttons[name]=rectangle(widget)
            data=dict(time_ns=time.time_ns(),closed=closed,visible=window.isVisible(),busy=window.is_busy(),
                console=window.console.toPlainText(),scroll=dict(value=scroll.value(),maximum=scroll.maximum(),
                    first_visible=window.console.firstVisibleBlock().text()),
                frame=[frame.x(),frame.y(),frame.width(),frame.height()],
                geometry={'console':rectangle(window.console.viewport()),'input':rectangle(window.input),
                    'send':rectangle(window.send_button),**buttons},
                input=window.input.text(),input_enabled=window.input.isEnabled(),
                input_focused=window.input.hasFocus(),events=events)
            target=args.output/'state.json';temporary=args.output/'state-next.json'
            temporary.write_text(json.dumps(data,indent=2)+'\n');temporary.replace(target)
        except RuntimeError:
            pass
    origin=Path(openbexi_ide.__file__).resolve()
    assert origin.is_relative_to(Path(sys.prefix).resolve())
    (args.output/'provenance.json').write_text(json.dumps(dict(version=metadata.version('openbexi-ide'),
        origin=str(origin),python=sys.version,qt_platform=app.platformName(),
        installed_sources={p.relative_to(origin.parent).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in origin.parent.rglob('*.py')},
        examples={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.project.glob('*.py')},
        observer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Read-only event filter and state observation; interaction arrives from the actual noVNC browser'),indent=2)+'\n')
    timer=QTimer();timer.setInterval(100);timer.timeout.connect(snapshot);timer.start()
    app.aboutToQuit.connect(lambda:snapshot(True))
    snapshot()
    return app.exec()


if __name__=='__main__':raise SystemExit(main())
