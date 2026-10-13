"""Manage optional runtime wheels without blocking the desktop event loop."""
import json
import configparser
from pathlib import Path
import re
import zipfile

from PySide6.QtCore import QProcess, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QVBoxLayout,
)

from openbexi_runtime.launch import console_interpreter
from openbexi_runtime.plugin_inventory import GROUPS, PROTECTED, normalized
from .controller import OwnedProcess, process_environment


def validate_plugin_wheel(path):
    """Require a runtime entry point and protect the IDE/interpreter packages."""
    from email.parser import BytesParser
    path = Path(path).resolve(strict=True)
    if path.suffix.lower() != '.whl' or path.stat().st_size > 250_000_000:
        raise ValueError('Choose a plugin wheel smaller than 250 MB')
    with zipfile.ZipFile(path) as archive:
        metadata_files = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
        if len(metadata_files) != 1 or archive.getinfo(metadata_files[0]).file_size > 1_000_000:
            raise ValueError('The wheel must describe exactly one package')
        metadata = BytesParser().parsebytes(archive.read(metadata_files[0]))
        name = metadata.get('Name', '')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name) or normalized(name) in PROTECTED:
            raise ValueError('This package cannot be installed as an optional runtime plugin')
        entries = metadata_files[0].removesuffix('METADATA') + 'entry_points.txt'
        if entries not in archive.namelist() or archive.getinfo(entries).file_size > 1_000_000:
            raise ValueError('The wheel does not declare an OpenBEXI runtime plugin')
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(archive.read(entries).decode('utf-8'))
        if not any(config.has_section(group) and config.items(group) for group in GROUPS):
            raise ValueError('The wheel does not declare an OpenBEXI runtime plugin')
    return path


class PluginManager(QDialog):
    plugins_changed = Signal()

    def __init__(self, interpreter, parent=None):
        super().__init__(parent)
        self.interpreter = console_interpreter(interpreter)
        self.operation = None
        self.inventory_bytes = bytearray()
        self.setWindowTitle('Runtime plugins')
        self.resize(640, 420)
        layout = QVBoxLayout(self)
        explanation = QLabel('Plugins run in the selected Python interpreter. Install their required dependencies before adding a local wheel.')
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        interpreter_label = QLabel(str(self.interpreter))
        interpreter_label.setTextFormat(Qt.PlainText)
        interpreter_label.setWordWrap(True)
        layout.addWidget(interpreter_label)
        self.packages = QListWidget()
        self.packages.currentItemChanged.connect(self.refresh_controls)
        layout.addWidget(self.packages)
        self.status = QLabel('Reading installed plugins…')
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(1000)
        self.output.setMaximumHeight(120)
        layout.addWidget(self.output)
        buttons = QHBoxLayout()
        self.install_button = QPushButton('Install wheel…')
        self.install_button.clicked.connect(self.choose_wheel)
        self.remove_button = QPushButton('Remove selected')
        self.remove_button.clicked.connect(self.remove_selected)
        self.refresh_button = QPushButton('Refresh')
        self.refresh_button.clicked.connect(self.refresh)
        self.close_button = QPushButton('Close')
        self.close_button.clicked.connect(self.reject)
        for button in (self.install_button, self.remove_button, self.refresh_button, self.close_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.process = OwnedProcess(self)
        self.process.setProcessEnvironment(process_environment())
        self.process.readyReadStandardOutput.connect(self.read_stdout)
        self.process.readyReadStandardError.connect(self.read_stderr)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.process.ownership_error.connect(self.fail)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.timed_out)
        QTimer.singleShot(0, self.refresh)

    def refresh_controls(self, *_):
        busy = self.operation is not None
        item = self.packages.currentItem()
        removable = bool(item and item.data(Qt.UserRole).get('removable'))
        self.install_button.setEnabled(not busy)
        self.remove_button.setEnabled(not busy and removable)
        self.refresh_button.setEnabled(not busy)
        self.packages.setEnabled(not busy)

    def start(self, operation, arguments):
        if self.operation is not None:
            return False
        self.operation = operation
        self.inventory_bytes.clear()
        self.status.setText('Reading installed plugins…' if operation == 'inventory' else 'Updating runtime plugins…')
        self.refresh_controls()
        self.timeout.start(10000 if operation == 'inventory' else 120000)
        self.process.start(str(self.interpreter), ['-I', '-B', '-X', 'utf8', *arguments])
        return True

    def refresh(self):
        probe = Path(__file__).resolve().parents[1] / 'openbexi_runtime/plugin_inventory.py'
        return self.start('inventory', [str(probe)])

    def choose_wheel(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Install a runtime plugin', '', 'Python wheels (*.whl)')
        if path:
            self.install_wheel(path)

    def install_wheel(self, path):
        try:
            wheel = validate_plugin_wheel(path)
        except (OSError, ValueError, zipfile.BadZipFile, KeyError, configparser.Error) as error:
            self.fail(str(error))
            return False
        return self.start('install', ['-m', 'pip', 'install', '--no-index', '--no-deps',
                                    '--disable-pip-version-check', '--no-input', str(wheel)])

    def remove_selected(self):
        item = self.packages.currentItem()
        if not item:
            return False
        package = item.data(Qt.UserRole)
        name = package['name']
        if (not package.get('removable') or normalized(name) in PROTECTED
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name)):
            return False
        return self.start('remove', ['-m', 'pip', 'uninstall', '--yes',
                                   '--disable-pip-version-check', '--no-input', name])

    def read_stdout(self):
        raw = bytes(self.process.readAllStandardOutput())
        if self.operation == 'inventory':
            self.inventory_bytes.extend(raw)
            if len(self.inventory_bytes) > 1_000_000:
                self.fail('Plugin inventory exceeds its display limit')
                self.process.kill_tree()
        else:
            self.output.insertPlainText(raw.decode('utf-8', 'replace'))

    def read_stderr(self):
        self.output.insertPlainText(bytes(self.process.readAllStandardError()).decode('utf-8', 'replace'))

    def process_finished(self, code, status):
        self.timeout.stop()
        self.read_stdout()
        self.read_stderr()
        operation, self.operation = self.operation, None
        if status != QProcess.NormalExit or code:
            self.fail('Plugin operation failed. Details are shown below.')
        elif operation == 'inventory':
            try:
                packages = json.loads(self.inventory_bytes)
                if not isinstance(packages, list):
                    raise ValueError('Invalid plugin package list')
                self.packages.clear()
                for package in packages:
                    name, version = package['name'], package['version']
                    if not isinstance(name, str) or not isinstance(version, str):
                        raise ValueError('Invalid plugin package metadata')
                    item = QListWidgetItem(name + ' ' + version)
                    item.setData(Qt.UserRole, package)
                    item.setToolTip(', '.join(entry['id'] for entry in package['backends']))
                    self.packages.addItem(item)
                self.status.setText('No runtime plugins installed.' if not packages else 'Select a package to remove it, or install a local wheel.')
            except (ValueError, KeyError, TypeError) as error:
                self.fail('Could not read installed plugins: ' + str(error))
        elif operation in ('install', 'remove'):
            self.plugins_changed.emit()
            self.refresh()
        self.refresh_controls()

    def process_error(self, error):
        if error == QProcess.FailedToStart:
            self.timeout.stop()
            self.operation = None
            self.fail('Could not start the selected Python interpreter')
            self.refresh_controls()

    def timed_out(self):
        self.fail('Plugin operation timed out')
        self.process.kill_tree()

    def fail(self, message):
        self.status.setText(message)

    def reject(self):
        self.timeout.stop()
        self.process.kill_tree()
        super().reject()

    def closeEvent(self, event):
        self.timeout.stop()
        self.process.kill_tree()
        event.accept()
