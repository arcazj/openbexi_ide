"""OpenBEXI's standalone native Python workspace."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

from PySide6.QtCore import QDir, QSettings, QSize, Qt
from PySide6.QtGui import QAction, QColor, QFontDatabase, QIcon, QPainter, QPainterPath, QPen, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFileSystemModel,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QSizePolicy, QSplitter, QStackedWidget, QTabWidget, QToolBar,
    QTreeView, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from openbexi_runtime.launch import LaunchSpec, console_interpreter
from .controller import RunController
from .debugger import DebugController
from .editor import CodeEditor, FileConflictError
from .fonts import configure_fonts, fixed_font
from .themes import THEMES, apply_theme
from .session_client import SessionClient
from .session_panel import JoinDialog, SessionPanel


def icon(kind: str, color: str) -> QIcon:
    """Small vector-drawn icons stay crisp under native scaling."""
    pixmap = QPixmap(48, 48)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.7))
    path = QPainterPath()
    if kind == "folder":
        path.moveTo(3, 7); path.lineTo(9, 7); path.lineTo(11, 10); path.lineTo(21, 10)
        path.lineTo(19, 19); path.lineTo(3, 19); path.closeSubpath()
        painter.drawPath(path)
    elif kind == "run":
        path.moveTo(8, 5); path.lineTo(19, 12); path.lineTo(8, 19); path.closeSubpath()
        painter.setBrush(QColor(color)); painter.setPen(Qt.NoPen); painter.drawPath(path)
    elif kind == "stop":
        painter.setBrush(QColor(color)); painter.setPen(Qt.NoPen); painter.drawRoundedRect(6, 6, 12, 12, 2, 2)
    elif kind == "debug":
        painter.drawRoundedRect(8, 8, 8, 11, 3, 3)
        painter.drawArc(9, 4, 6, 7, 0, 180 * 16)
        for y in (10, 14, 18):
            painter.drawLine(4, y, 8, y); painter.drawLine(16, y, 20, y)
        painter.drawLine(12, 9, 12, 18)
    else:
        painter.drawEllipse(7, 7, 10, 10)
        for x1, y1, x2, y2 in [(12, 2, 12, 5), (12, 19, 12, 22), (2, 12, 5, 12),
                               (19, 12, 22, 12), (5, 5, 7, 7), (17, 17, 19, 19)]:
            painter.drawLine(x1, y1, x2, y2)
    painter.end()
    return QIcon(pixmap)


class ArgumentsDialog(QDialog):
    def __init__(self, arguments, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Script arguments")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("One argument per line. Spaces are kept as entered."))
        self.input = QPlainTextEdit("\n".join(arguments))
        self.input.setPlaceholderText("first value\nsecond value")
        layout.addWidget(self.input)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(400, 240)


class MainWindow(QMainWindow):
    def __init__(self, project=None, settings=None):
        super().__init__()
        self.settings = settings or QSettings("OpenBEXI", "PythonIDE")
        self.project: Path | None = None
        self.interpreter = console_interpreter(sys.executable)
        self.arguments: tuple[str, ...] = ()
        self.theme = self.settings.value("theme", "light")
        if self.theme not in THEMES:
            self.theme = "light"
        self.colors = apply_theme(QApplication.instance(), self.theme)
        self._stopping = False
        self._close_requested = False
        self.setWindowTitle("OpenBEXI IDE")
        self.resize(1280, 820)
        self.setMinimumSize(760, 520)
        self.run_controller = RunController(self)
        self.debug_controller = DebugController(self)
        self.session_client = SessionClient(self)
        self.session_client.output.connect(lambda event: self.append_output(event['text']))
        self.session_client.error.connect(self.report_error)
        self.run_controller.output.connect(self.append_output)
        self.run_controller.error.connect(self.report_error)
        self.run_controller.state_changed.connect(self.refresh_busy)
        self.run_controller.finished.connect(self.run_finished)
        self.run_controller.process.started.connect(self.refresh_busy)
        self.run_controller.interpreter_checked.connect(self.show_interpreter)
        self.debug_controller.output.connect(self.append_output)
        self.debug_controller.error.connect(self.report_error)
        self.debug_controller.state_changed.connect(self.refresh_busy)
        self.debug_controller.finished.connect(self.run_finished)
        self.debug_controller.interpreter_checked.connect(self.show_interpreter)
        self.debug_controller.stopped.connect(self.debug_stopped)
        self.debug_controller.continued.connect(self.debug_continued)
        self.debug_controller.stack_changed.connect(self.show_stack)
        self.debug_controller.threads_changed.connect(self.show_threads)
        self.debug_controller.breakpoints_verified.connect(self.show_verified_breakpoints)
        self.make_actions()
        self.make_workspace()
        self.session_client.changed.connect(self.shared_changed)
        self.make_toolbar()
        self.make_menus()
        self.position_label = QLabel("Development")
        self.position_label.setObjectName("muted")
        self.statusBar().addPermanentWidget(self.position_label)
        self.statusBar().showMessage("Open a folder to begin")
        remembered = project or self.settings.value("last_project", "")
        if remembered and Path(remembered).is_dir():
            self.open_project(Path(remembered))
        self.set_busy(False)

    def action(self, name, callback, shortcut=None):
        item = QAction(name, self)
        item.triggered.connect(callback)
        if shortcut:
            item.setShortcut(shortcut)
        return item

    def make_actions(self):
        self.open_action = self.action("Open Folder", self.choose_project, "Ctrl+O")
        self.run_action = self.action("Run", self.run_script, "F5")
        self.debug_action = self.action("Debug", self.debug_script, "Shift+F5")
        self.debug_action.setToolTip("Debug the current Python file (Shift+F5)")
        self.stop_action = self.action("Stop", self.stop_script, "Shift+F2")
        self.save_action = self.action("Save", self.save_current, "Ctrl+S")
        self.new_action = self.action("New Python File", self.new_file, "Ctrl+N")
        self.find_action = self.action("Find in File", self.show_find, "Ctrl+F")
        self.theme_action = self.action("Switch theme", self.toggle_theme)
        self.interpreter_action = self.action("Select Python Interpreter…", self.choose_interpreter)
        self.args_action = self.action("Script Arguments…", self.choose_arguments)
        self.eof_action = self.action("Close Script Input", self.close_input)
        self.join_action = self.action("Join Shared Session…", self.join_session)
        self.disconnect_action = self.action("Disconnect from Session", self.session_client.disconnect)
        self.continue_action = self.action("Continue", lambda: self.debug_controller.control("continue"), "F6")
        self.pause_action = self.action("Pause", lambda: self.debug_controller.control("pause"), "F7")
        self.over_action = self.action("Step Over", lambda: self.debug_controller.control("next"), "F10")
        self.into_action = self.action("Step Into", lambda: self.debug_controller.control("stepIn"), "F11")
        self.out_action = self.action("Step Out", lambda: self.debug_controller.control("stepOut"), "Shift+F11")

    def make_workspace(self):
        self.files = QFileSystemModel(self)
        self.files.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        self.tree = QTreeView()
        self.tree.setObjectName("projectTree")
        self.tree.setModel(self.files)
        self.tree.setHeaderHidden(True)
        for column in range(1, 4):
            self.tree.hideColumn(column)
        self.tree.doubleClicked.connect(self.open_tree_item)
        self.tree.setIndentation(16)
        project_panel = QWidget()
        project_layout = QVBoxLayout(project_panel)
        project_layout.setContentsMargins(8, 0, 8, 8)
        heading_row = QHBoxLayout()
        heading = QLabel("PROJECT"); heading.setObjectName("sectionLabel")
        heading_row.addWidget(heading)
        new_button = QPushButton("+"); new_button.setToolTip("New Python File (Ctrl+N)")
        new_button.setAccessibleName("New Python File")
        new_button.setFixedWidth(34); new_button.clicked.connect(self.new_file)
        heading_row.addStretch(); heading_row.addWidget(new_button)
        project_layout.addLayout(heading_row); project_layout.addWidget(self.tree)
        self.project_label = QLabel("No folder opened"); self.project_label.setObjectName("muted")
        self.project_label.setTextFormat(Qt.PlainText)
        self.project_label.setWordWrap(True)
        project_layout.addWidget(self.project_label)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True); self.tabs.setTabsClosable(True); self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.tab_changed)
        welcome = QWidget()
        welcome_layout = QVBoxLayout(welcome)
        welcome_layout.setAlignment(Qt.AlignCenter)
        title = QLabel("Your Python workspace"); title.setObjectName("welcomeTitle")
        subtitle = QLabel("Open a folder, choose a file, and start creating.")
        subtitle.setObjectName("muted")
        open_button = QPushButton("Open Folder"); open_button.clicked.connect(self.choose_project)
        for widget in (title, subtitle, open_button):
            welcome_layout.addWidget(widget, alignment=Qt.AlignCenter)
        self.editor_stack = QStackedWidget()
        self.editor_stack.addWidget(welcome); self.editor_stack.addWidget(self.tabs)
        self.find = QLineEdit(); self.find.setPlaceholderText("Find in this file · Enter for next match · Escape to close")
        self.find.returnPressed.connect(self.find_next); self.find.hide()
        editor_panel = QWidget(); editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.addWidget(self.editor_stack); editor_layout.addWidget(self.find)
        self.find.installEventFilter(self)

        self.console = QPlainTextEdit(); self.console.setObjectName("consoleOutput")
        self.console.setReadOnly(True); self.console.setMaximumBlockCount(5000)
        self.console.setFont(fixed_font())
        self.console.setPlaceholderText("Output appears here when you run a script.")
        self.input = QLineEdit(); self.input.setPlaceholderText("Send input to your running script…")
        self.input.returnPressed.connect(self.send_input)
        self.send_button = QPushButton("Send"); self.send_button.clicked.connect(self.send_input)
        input_row = QHBoxLayout(); input_row.addWidget(self.input); input_row.addWidget(self.send_button)
        console_panel = QWidget(); console_layout = QVBoxLayout(console_panel)
        console_layout.setContentsMargins(12, 8, 12, 10)
        console_layout.addWidget(self.console); console_layout.addLayout(input_row)
        self.debug_panel = QWidget(); debug_layout = QVBoxLayout(self.debug_panel)
        debug_layout.setContentsMargins(12, 6, 12, 8)
        controls = QHBoxLayout()
        for action in (self.continue_action, self.pause_action, self.over_action, self.into_action, self.out_action):
            button = QPushButton(action.text())
            button.setToolTip(action.shortcut().toString())
            button.clicked.connect(action.trigger)
            action.changed.connect(lambda a=action, b=button: b.setEnabled(a.isEnabled()))
            controls.addWidget(button)
        controls.addStretch()
        self.threads = QComboBox(); self.threads.setMinimumWidth(130)
        self.threads.setToolTip("Paused thread")
        self.threads.currentIndexChanged.connect(self.select_thread)
        controls.addWidget(self.threads)
        debug_layout.addLayout(controls)
        details = QSplitter(Qt.Horizontal)
        self.stack_list = QListWidget(); self.stack_list.setMinimumWidth(170)
        self.stack_list.currentItemChanged.connect(self.select_frame)
        self.variables = QTreeWidget(); self.variables.setHeaderLabels(["Name", "Value", "Type"])
        self.variables.setColumnWidth(0, 150); self.variables.setColumnWidth(1, 210)
        self.variables.itemExpanded.connect(self.expand_variable)
        details.addWidget(self.stack_list); details.addWidget(self.variables)
        details.setSizes([250, 650]); debug_layout.addWidget(details)
        self.expression = QLineEdit(); self.expression.setPlaceholderText("Evaluate a Python expression while paused")
        self.expression.returnPressed.connect(self.evaluate_expression)
        self.eval_result = QLabel("Set a breakpoint beside a line number, then choose Debug.")
        self.eval_result.setTextFormat(Qt.PlainText); self.eval_result.setObjectName("muted")
        debug_layout.addWidget(self.expression); debug_layout.addWidget(self.eval_result)
        self.frame_id = None
        self.output_tabs = QTabWidget(); self.output_tabs.setDocumentMode(True)
        self.output_tabs.addTab(console_panel, "Console"); self.output_tabs.addTab(self.debug_panel, "Debugger")
        self.session_panel = SessionPanel(self.session_client, self)
        self.session_panel.join_requested.connect(self.join_session)
        self.session_panel.open_project_requested.connect(lambda path: self.open_project(Path(path)))
        self.session_panel.frame_activated.connect(self.open_shared_frame)
        self.session_panel.selection_changed.connect(self.refresh_busy)
        self.output_tabs.addTab(self.session_panel, "Session")
        self.vertical = QSplitter(Qt.Vertical)
        self.vertical.addWidget(editor_panel); self.vertical.addWidget(self.output_tabs)
        self.vertical.setSizes([510, 225]); self.vertical.setCollapsible(0, False)
        self.horizontal = QSplitter(Qt.Horizontal)
        self.horizontal.addWidget(project_panel); self.horizontal.addWidget(self.vertical)
        self.horizontal.setSizes([235, 1045]); self.horizontal.setCollapsible(1, False)
        self.setCentralWidget(self.horizontal)

    def make_toolbar(self):
        toolbar = QToolBar("Workspace", self)
        toolbar.setMovable(False); toolbar.setIconSize(QSize(21, 21))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)
        for item in (self.open_action, self.run_action, self.debug_action, self.stop_action):
            toolbar.addAction(item)
        spacer = QWidget(); spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)
        self.language = QComboBox()
        self.language.addItem("Python", "python")
        self.language.addItem("SPELL plugin", "spell")
        self.language.setToolTip("Language for shared-session Run; plugins belong to the server interpreter")
        self.language_action = toolbar.addWidget(self.language)
        self.language_action.setVisible(False)
        self.session_button = QPushButton("Local workspace")
        self.session_button.clicked.connect(self.show_session)
        toolbar.addWidget(self.session_button)
        self.interpreter_button = QPushButton("Python 3.13")
        self.interpreter_button.clicked.connect(self.choose_interpreter)
        self.interpreter_button.setToolTip("Select the interpreter for this project")
        toolbar.addWidget(self.interpreter_button)
        toolbar.addAction(self.theme_action)
        toolbar.widgetForAction(self.theme_action).setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.toolbar = toolbar
        self.update_icons()

    def update_icons(self):
        for item, name, color in [(self.open_action, "folder", self.colors["muted"]),
                                  (self.run_action, "run", "#4d9568"),
                                  (self.debug_action, "debug", "#9e79c2"),
                                  (self.stop_action, "stop", "#cc6b73"),
                                  (self.theme_action, "theme", self.colors["muted"])]:
            item.setIcon(icon(name, color))

    def make_menus(self):
        file_menu = self.menuBar().addMenu("File")
        for action in (self.open_action, self.new_action, self.save_action):
            file_menu.addAction(action)
        file_menu.addSeparator(); file_menu.addAction(self.action("Close", self.close, "Alt+F4"))
        run_menu = self.menuBar().addMenu("Run")
        for action in (self.run_action, self.debug_action, self.stop_action):
            run_menu.addAction(action)
        run_menu.addSeparator()
        for action in (self.continue_action, self.pause_action, self.over_action, self.into_action, self.out_action):
            run_menu.addAction(action)
        run_menu.addSeparator()
        for action in (self.interpreter_action, self.args_action, self.eof_action):
            run_menu.addAction(action)
        view_menu = self.menuBar().addMenu("View")
        view_menu.addAction(self.find_action); view_menu.addAction(self.theme_action)
        session_menu = self.menuBar().addMenu("Session")
        session_menu.addAction(self.join_action)
        session_menu.addAction(self.disconnect_action)
        self.session_actions = {}
        for name in ('claim', 'release', 'pause', 'resume', 'stop'):
            button = getattr(self.session_panel, name)
            item = self.action(button.text(), button.click)
            self.session_actions[name] = item
            session_menu.addAction(item)

    def show_session(self):
        self.output_tabs.setCurrentWidget(self.session_panel)
        if not self.session_client.active:
            self.join_session()

    def join_session(self):
        if self.is_busy() or self.session_client.active:
            return
        dialog = JoinDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.join_shared_session(**dialog.values())

    def join_shared_session(self, **values):
        if self.is_busy():
            self.report_error('Stop the local Run/Debug before joining a shared session')
            return False
        if self.session_client.join(**values):
            self.console.clear()
            self.output_tabs.setCurrentWidget(self.session_panel)
            self.vertical.setSizes([max(200, self.vertical.height()-360), 360])
            return True
        return False

    def shared_changed(self):
        self.language_action.setVisible(self.session_client.active)
        role = self.session_client.identity.get('role')
        label = ('Control' if self.session_client.can_control else 'Monitor' if role == 'monitor' else 'Shared session')
        self.session_button.setText(label if self.session_client.active else 'Local workspace')
        self.update_position()
        self.refresh_busy()
        if self._close_requested and not self.session_client.active and not self.is_busy():
            self.close()

    def open_shared_frame(self, frame):
        path = Path(frame['file']).resolve()
        if self.project and path.is_relative_to(self.project):
            editor = self.open_file(path)
            if editor:
                editor.show_execution_line(frame['line'])

    def shared_project_matches(self):
        remote = self.session_client.snapshot.get('project')
        return bool(self.project and remote and self.project == Path(remote).resolve())

    def current_editor(self):
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, CodeEditor) else None

    def choose_project(self):
        folder = QFileDialog.getExistingDirectory(self, "Open project folder", str(self.project or Path.home()))
        if folder:
            self.open_project(Path(folder))

    def open_project(self, folder: Path):
        folder = folder.resolve()
        if not folder.is_dir():
            self.report_error("Choose an existing folder"); return False
        if self.is_busy():
            self.report_error("Stop the script before changing projects"); return False
        if not self.confirm_unsaved():
            return False
        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0); widget.deleteLater()
        self.editor_stack.setCurrentIndex(0)
        self.project = folder
        self.arguments = ()
        self.files.setRootPath(str(folder))
        self.tree.setRootIndex(self.files.index(str(folder)))
        self.project_label.setText(folder.name); self.project_label.setToolTip(str(folder))
        self.setWindowTitle(f"{folder.name} — OpenBEXI IDE")
        self.settings.setValue("last_project", str(folder))
        self.interpreter = console_interpreter(sys.executable)
        for relative in (".venv/Scripts/python.exe", ".venv/bin/python"):
            candidate = folder / relative
            if candidate.is_file():
                self.interpreter = candidate.resolve(); break
        key = "interpreter/" + hashlib.sha256(str(folder).encode()).hexdigest()
        remembered = self.settings.value(key, "")
        if remembered and Path(remembered).is_file():
            self.interpreter = Path(remembered)
        self.interpreter_button.setToolTip(str(self.interpreter))
        self.statusBar().showMessage("Choose a Python file from the project")
        self.set_busy(False)
        return True

    def open_tree_item(self, index):
        path = Path(self.files.filePath(index))
        if path.is_file():
            self.open_file(path)

    def open_file(self, path: Path):
        path = path.resolve()
        if self.project is None or not path.is_relative_to(self.project):
            self.report_error("Open the folder containing this file first"); return None
        for index in range(self.tabs.count()):
            if self.tabs.widget(index).path == path:
                self.tabs.setCurrentIndex(index); return self.tabs.widget(index)
        try:
            editor = CodeEditor(path, self.colors)
        except (OSError, ValueError, UnicodeError, SyntaxError) as error:
            self.report_error(str(error)); return None
        editor.document().modificationChanged.connect(lambda _modified: self.update_tab(editor))
        editor.breakpoints_changed.connect(lambda: self.update_breakpoints(editor))
        editor.cursorPositionChanged.connect(self.update_position)
        index = self.tabs.addTab(editor, path.name)
        self.tabs.setTabToolTip(index, str(path))
        self.tabs.setCurrentIndex(index); self.editor_stack.setCurrentIndex(1)
        editor.setFocus(); self.refresh_busy()
        return editor

    def update_tab(self, editor):
        index = self.tabs.indexOf(editor)
        if index >= 0:
            self.tabs.setTabText(index, editor.path.name + (" •" if editor.document().isModified() else ""))

    def tab_changed(self, _index):
        self.update_position()
        if hasattr(self, "input"):
            self.refresh_busy()

    def update_position(self):
        if not hasattr(self, "position_label"):
            return
        editor = self.current_editor()
        if editor:
            cursor = editor.textCursor()
            mode = 'Monitoring' if self.session_client.active and self.session_client.identity.get('role') == 'monitor' else 'Development'
            self.position_label.setText(f"{mode}    Ln {cursor.blockNumber()+1}, Col {cursor.positionInBlock()+1}")
        else:
            self.position_label.setText("Development")

    def save_editor(self, editor):
        if self.session_client.active and self.session_client.identity.get('role') == 'monitor':
            self.report_error('Monitoring connections cannot save project changes')
            return False
        try:
            editor.save()
            self.statusBar().showMessage(f"Saved {editor.path.name}", 4000)
            return True
        except FileConflictError as error:
            choice = QMessageBox.warning(self, "File changed outside the IDE", str(error),
                                         QMessageBox.Save | QMessageBox.Cancel, QMessageBox.Cancel)
            if choice == QMessageBox.Save:
                try:
                    editor.save(force=True); return True
                except OSError as save_error:
                    self.report_error(str(save_error))
        except (OSError, UnicodeError) as error:
            self.report_error(str(error))
        return False

    def save_current(self):
        editor = self.current_editor()
        return self.save_editor(editor) if editor else False

    def confirm_unsaved(self, editors=None):
        for editor in editors or [self.tabs.widget(i) for i in range(self.tabs.count())]:
            if editor.document().isModified():
                choice = QMessageBox.question(self, "Save changes?", f"Save changes to {editor.path.name}?",
                    QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
                if choice == QMessageBox.Cancel or (choice == QMessageBox.Save and not self.save_editor(editor)):
                    return False
        return True

    def close_tab(self, index):
        editor = self.tabs.widget(index)
        if self.is_busy() or not self.confirm_unsaved([editor]):
            return
        self.tabs.removeTab(index); editor.deleteLater()
        if not self.tabs.count():
            self.editor_stack.setCurrentIndex(0)

    def new_file(self):
        if self.session_client.active and self.session_client.identity.get('role') == 'monitor':
            return
        if not self.project or self.is_busy():
            self.statusBar().showMessage("Open a project folder first", 4000); return
        filename, _ = QFileDialog.getSaveFileName(self, "New Python file", str(self.project / "main.py"), "Python (*.py)")
        if filename:
            path = Path(filename).resolve()
            if not path.is_relative_to(self.project):
                self.report_error("Create the file inside the opened project"); return
            try:
                # Never truncate an existing file selected in the new-file dialog.
                path.touch(exist_ok=False)
            except OSError as error:
                self.report_error(str(error)); return
            self.open_file(path)

    def choose_interpreter(self):
        if self.is_busy():
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Select CPython 3.13 interpreter", str(self.interpreter.parent))
        if filename:
            self.interpreter = console_interpreter(filename)
            self.interpreter_button.setToolTip(str(self.interpreter))
            if self.project:
                key = "interpreter/" + hashlib.sha256(str(self.project).encode()).hexdigest()
                self.settings.setValue(key, str(self.interpreter))
            self.statusBar().showMessage("Interpreter is checked when you run a script", 5000)

    def choose_arguments(self):
        dialog = ArgumentsDialog(self.arguments, self)
        if dialog.exec() == QDialog.Accepted:
            self.arguments = tuple(dialog.input.toPlainText().splitlines())

    def run_script(self):
        editor = self.current_editor()
        if not editor or not self.project or self.is_busy():
            return
        if self.session_client.active:
            if not self.session_client.can_control or not self.shared_project_matches():
                self.report_error('Open the session folder and claim control before Run')
                return
            for index in range(self.tabs.count()):
                other = self.tabs.widget(index)
                if other.document().isModified() and not self.save_editor(other):
                    return
            self.output_tabs.setCurrentWidget(self.session_panel)
            self.session_client.command('run', script=str(editor.path.relative_to(self.project)),
                                        arguments=list(self.arguments), language=self.language.currentData())
            return
        for index in range(self.tabs.count()):
            other = self.tabs.widget(index)
            if other.document().isModified() and not self.save_editor(other):
                return
        self.console.clear(); self.output_tabs.setCurrentIndex(0)
        self.append_output(f"Running {editor.path.name}\n\n")
        self._stopping = False
        try:
            self.run_controller.start(LaunchSpec(self.project, editor.path, self.interpreter, self.arguments))
        except (OSError, ValueError, RuntimeError) as error:
            self.report_error(str(error)); self.set_busy(False)

    def debug_script(self):
        if self.session_client.active:
            self.report_error('Shared sessions expose read-only live stacks. Disconnect to use local Debug.')
            return
        editor = self.current_editor()
        if not editor or not self.project or self.is_busy():
            return
        for index in range(self.tabs.count()):
            other = self.tabs.widget(index)
            if other.document().isModified() and not self.save_editor(other):
                return
        self.console.clear(); self.stack_list.clear(); self.variables.clear()
        self.frame_id = None; self._stopping = False
        self.output_tabs.setCurrentIndex(0)
        self.append_output(f"Debugging {editor.path.name}\n\n")
        breakpoints = {self.tabs.widget(i).path: self.tabs.widget(i).breakpoints for i in range(self.tabs.count())}
        try:
            self.debug_controller.start(LaunchSpec(self.project, editor.path, self.interpreter, self.arguments), breakpoints)
        except (OSError, ValueError, RuntimeError) as error:
            self.report_error(str(error)); self.refresh_busy()

    def stop_script(self):
        if self.session_client.active and not self.is_busy():
            self.session_panel.control('stop')
            return
        self._stopping = True
        self.statusBar().showMessage("Stopping script…")
        self.run_controller.stop()
        self.debug_controller.stop()

    def is_busy(self):
        return self.run_controller.running or self.debug_controller.running

    def refresh_busy(self, *_):
        self.set_busy(self.is_busy())

    def show_interpreter(self, info):
        version = ".".join(str(part) for part in info["version"])
        self.interpreter_button.setText(f"Python {version}")
        self.interpreter_button.setToolTip(info["executable"])

    def set_busy(self, busy):
        editor = self.current_editor()
        self.run_action.setEnabled(not busy and bool(editor) and editor.path.suffix == ".py")
        self.debug_action.setEnabled(not busy and bool(editor) and editor.path.suffix == ".py")
        self.stop_action.setEnabled(busy)
        self.open_action.setEnabled(not busy)
        self.new_action.setEnabled(not busy and self.project is not None)
        self.save_action.setEnabled(not busy and bool(editor))
        self.interpreter_action.setEnabled(not busy)
        self.interpreter_button.setEnabled(not busy)
        self.args_action.setEnabled(not busy)
        self.eof_action.setEnabled(busy)
        if hasattr(self, "input"):
            input_ready = any(process.state() == process.ProcessState.Running
                              for process in (self.run_controller.process, self.debug_controller.terminal))
            self.input.setEnabled(input_ready)
        paused = self.debug_controller.running and self.debug_controller.paused
        for action in (self.continue_action, self.over_action, self.into_action, self.out_action):
            action.setEnabled(paused)
        self.pause_action.setEnabled(self.debug_controller.running and not paused)
        self.threads.setEnabled(paused); self.expression.setEnabled(paused)
        for index in range(self.tabs.count()):
            self.tabs.widget(index).setReadOnly(busy)
        if busy:
            self.statusBar().showMessage("Debugging · local development" if self.debug_controller.running
                                         else "Running · local development")
        self.join_action.setEnabled(not busy and not self.session_client.active)
        self.disconnect_action.setEnabled(self.session_client.active and self.session_client.state != 'leaving')
        self.session_button.setEnabled(not busy)
        if self.session_client.active:
            client = self.session_client
            monitor = client.identity.get('role') == 'monitor' or client.state != 'joined'
            self.run_action.setEnabled(client.can_control and self.shared_project_matches() and bool(editor) and editor.path.suffix == '.py')
            self.debug_action.setEnabled(False)
            self.stop_action.setEnabled(self.session_panel.stop.isEnabled())
            self.save_action.setEnabled(not monitor and bool(editor))
            self.new_action.setEnabled(not monitor and self.project is not None)
            self.interpreter_action.setEnabled(False)
            self.interpreter_button.setEnabled(False)
            self.language.setEnabled(client.can_control)
            self.args_action.setEnabled(client.can_control)
            selected = self.session_panel.selected or {}
            input_ready = client.can_control and selected.get('status') in {'RUNNING', 'PAUSING'} and not selected.get('input_closed')
            self.input.setEnabled(bool(input_ready))
            self.eof_action.setEnabled(bool(input_ready))
            active_paths = {p['script'] for p in client.snapshot.get('procedures', [])
                            if p['status'] not in {'COMPLETED', 'FAILED', 'CANCELLED'}}
            for index in range(self.tabs.count()):
                tab = self.tabs.widget(index)
                logical = str(tab.path.relative_to(self.project)) if self.project else ''
                tab.setReadOnly(monitor or logical in active_paths or logical.replace('\\', '/') in active_paths)
        self.send_button.setEnabled(self.input.isEnabled())
        for name, action in self.session_actions.items():
            action.setEnabled(getattr(self.session_panel, name).isEnabled())

    def append_output(self, content):
        cursor = self.console.textCursor(); cursor.movePosition(QTextCursor.End)
        cursor.insertText(content); self.console.setTextCursor(cursor); self.console.ensureCursorVisible()
        if self.console.document().characterCount() > 500_000:
            cursor = QTextCursor(self.console.document())
            cursor.setPosition(0)
            cursor.setPosition(self.console.document().characterCount() - 400_000, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()

    def run_finished(self, code):
        message = "Stopped" if self._stopping else f"Finished · exit {code}"
        self.append_output(f"\n{message}\n"); self.statusBar().showMessage(message)
        self.frame_id = None
        for index in range(self.tabs.count()):
            self.tabs.widget(index).show_execution_line(None)
        self.refresh_busy()
        if self._close_requested:
            self.close()

    def report_error(self, message):
        self.append_output(f"\n{message}\n"); self.output_tabs.setCurrentIndex(0)
        self.statusBar().showMessage(message, 10000)

    def send_input(self):
        if self.input.isEnabled():
            if self.session_client.active:
                selected = self.session_panel.selected
                if selected and self.session_client.command('input', procedure=selected['id'], text=self.input.text()):
                    self.input.clear()
                return
            controller = self.debug_controller if self.debug_controller.running else self.run_controller
            controller.send_input(self.input.text()); self.input.clear()

    def close_input(self):
        if self.session_client.active:
            selected = self.session_panel.selected
            if selected:
                self.session_client.command('input', procedure=selected['id'], text=None)
            return
        controller = self.debug_controller if self.debug_controller.running else self.run_controller
        controller.close_input()

    def debug_stopped(self, body):
        self.output_tabs.setCurrentIndex(1)
        if self.vertical.sizes()[-1] < 320:
            self.vertical.setSizes([max(200, self.vertical.height() - 320), 320])
        self.eval_result.setText(f"Paused · {body.get('reason', 'breakpoint')}")
        self.refresh_busy()
        self.statusBar().showMessage("Paused · local development")

    def debug_continued(self):
        self.frame_id = None; self.stack_list.clear(); self.variables.clear()
        for index in range(self.tabs.count()):
            self.tabs.widget(index).show_execution_line(None)
        self.eval_result.setText("Running · use Pause to inspect the current thread")
        self.refresh_busy()

    def show_threads(self, threads):
        self.threads.blockSignals(True); self.threads.clear()
        for thread in threads:
            self.threads.addItem(thread.get("name", str(thread["id"])), thread["id"])
        index = self.threads.findData(self.debug_controller.thread_id)
        if index >= 0: self.threads.setCurrentIndex(index)
        self.threads.blockSignals(False)

    def select_thread(self, _index):
        thread_id = self.threads.currentData()
        if thread_id is not None:
            self.debug_controller.select_thread(thread_id)

    def show_stack(self, frames):
        self.stack_list.clear()
        for frame in frames:
            source = frame.get("source", {})
            filename = Path(source.get("path", "unknown")).name
            item = QListWidgetItem(f"{frame.get('name', '<frame>')} · {filename}:{frame.get('line', '?')}")
            item.setData(Qt.UserRole, frame); item.setToolTip(source.get("path", ""))
            self.stack_list.addItem(item)
        if frames: self.stack_list.setCurrentRow(0)

    def select_frame(self, item, _previous):
        if not item or not self.debug_controller.paused:
            return
        frame = item.data(Qt.UserRole); self.frame_id = frame["id"]
        self.debug_controller.view_generation += 1
        path = frame.get("source", {}).get("path")
        if path and self.project and Path(path).resolve().is_relative_to(self.project):
            editor = self.open_file(Path(path))
            if editor: editor.show_execution_line(frame.get("line"))
        self.variables.clear()
        self.debug_controller.view_request("scopes", {"frameId": self.frame_id}, self.show_scopes)

    def show_scopes(self, body):
        self.variables.clear()
        for scope in body.get("scopes", []):
            item = QTreeWidgetItem([scope["name"], "", ""])
            item.setData(0, Qt.UserRole, scope.get("variablesReference", 0))
            self.variables.addTopLevelItem(item)
            if scope.get("variablesReference"):
                item.addChild(QTreeWidgetItem(["Loading…"]))
                if scope["name"] == "Locals": item.setExpanded(True)

    def expand_variable(self, item):
        reference = item.data(0, Qt.UserRole)
        if not reference or not self.debug_controller.paused:
            return
        # A request belongs to a particular stopped view; stale replies are
        # rejected by the controller before touching a cleared tree item.
        def received(body):
            item.takeChildren()
            for variable in body.get("variables", [])[:100]:
                child = QTreeWidgetItem([variable["name"], variable.get("value", "")[:4000], variable.get("type", "")])
                child.setData(0, Qt.UserRole, variable.get("variablesReference", 0))
                if variable.get("variablesReference"): child.addChild(QTreeWidgetItem(["Expand to inspect"]))
                item.addChild(child)
        self.debug_controller.view_request("variables", {"variablesReference": reference, "start": 0, "count": 100}, received)

    def evaluate_expression(self):
        if self.frame_id is not None and self.debug_controller.paused and self.expression.text():
            self.debug_controller.view_request("evaluate", {"frameId": self.frame_id,
                "expression": self.expression.text(), "context": "watch"},
                lambda body: self.eval_result.setText(body.get("result", "")[:4000]))

    def update_breakpoints(self, editor):
        editor.verified_breakpoints.clear()
        if self.debug_controller.running:
            self.debug_controller.set_breakpoints(editor.path, editor.breakpoints)

    def show_verified_breakpoints(self, result):
        for index in range(self.tabs.count()):
            editor = self.tabs.widget(index)
            if editor.path == Path(result["path"]).resolve():
                for breakpoint in result["breakpoints"]:
                    if "line" in breakpoint:
                        editor.verified_breakpoints[breakpoint["line"]] = breakpoint.get("verified", False)
                    if not breakpoint.get("verified"):
                        self.append_output(f"Breakpoint: {breakpoint.get('message', 'This line is not executable')}\n")
                editor.gutter.update()

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.colors = apply_theme(QApplication.instance(), self.theme)
        self.settings.setValue("theme", self.theme)
        for index in range(self.tabs.count()):
            self.tabs.widget(index).set_colors(self.colors)
        self.update_icons()

    def show_find(self):
        self.find.show(); self.find.setFocus(); self.find.selectAll()

    def find_next(self):
        editor = self.current_editor()
        if editor and self.find.text() and not editor.find(self.find.text()):
            cursor = editor.textCursor(); cursor.movePosition(QTextCursor.Start); editor.setTextCursor(cursor)
            editor.find(self.find.text())

    def eventFilter(self, watched, event):
        if watched is self.find and event.type() == event.Type.KeyPress and event.key() == Qt.Key_Escape:
            self.find.hide()
            if self.current_editor(): self.current_editor().setFocus()
            return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event):
        if not self._close_requested and not self.confirm_unsaved():
            event.ignore(); return
        if self.is_busy():
            self._close_requested = True
            self.stop_script(); event.ignore(); return
        if self.session_client.active:
            self._close_requested = True
            self.setEnabled(False)
            self.session_client.disconnect()
            event.ignore(); return
        self.settings.sync()
        event.accept()


def main(argv=None):
    parser = argparse.ArgumentParser(description="OpenBEXI standalone Python desktop IDE")
    parser.add_argument("--project", type=Path, help="Project folder to open")
    parser.add_argument("--file", type=Path, help="File inside the project to edit")
    parser.add_argument("--theme", choices=THEMES, help="Light or dark theme")
    parser.add_argument('--session-info', type=Path, help='Private session invitation JSON')
    parser.add_argument('--user', default='Developer', help='Shared-session display name')
    parser.add_argument('--role', choices=('developer', 'monitor'), default='developer')
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("OpenBEXI IDE")
    app.setStyle("Fusion")
    configure_fonts(app)
    window = MainWindow(args.project)
    if args.theme and window.theme != args.theme:
        window.toggle_theme()
    if args.file:
        window.open_file(args.file)
    window.show()
    if args.session_info:
        window.join_shared_session(user=args.user, role=args.role, invite_file=args.session_info)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
