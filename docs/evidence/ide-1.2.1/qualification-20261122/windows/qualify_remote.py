"""Exercise the installed Windows panel against a disposable, certificate-authenticated Linux gateway."""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog

from openbexi_ide.app import MainWindow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clients", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    app = QApplication([])
    source = output / "ordinary.py"
    marker = output / "local-runs.txt"
    source.write_text("from pathlib import Path\nwith Path(__file__).with_name('local-runs.txt').open('a') as log:\n    log.write('one\\n')\n")
    assert Path(importlib.metadata.distribution("openbexi-ide").locate_file("")).resolve().is_relative_to(Path(sys.prefix).resolve())
    report = {"version": importlib.metadata.version("openbexi-ide"), "qt_platform": app.platformName(),
              "connection_file_selection": "The file chooser returned the fixture's private path. Connect, TLS, authorization and all other widget actions ran normally.",
              "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "identities": {}, "passed": False}
    view = MainWindow(output, QSettings(str(output / "settings.ini"), QSettings.IniFormat))
    view.show()
    view.open_file(source)
    panel = view.spell_server_panel

    def wait(condition):
        end = time.monotonic() + 12
        while time.monotonic() < end:
            app.processEvents()
            if condition():
                return
            QTest.qWait(15)
        raise AssertionError("Windows panel timed out; " + panel.status.text())

    try:
        for principal, expected in (("alice", ["A", "B"]), ("bob", ["B"]), ("observer", ["A"])):
            view.output_tabs.setCurrentWidget(panel)

            wait(lambda: panel.connect_button.isVisible() and panel.connect_button.isEnabled())
            path = (args.clients / principal / "windows-client.json").resolve(strict=True)
            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "JSON (*.json)")) as chooser:
                QTest.mouseClick(panel.connect_button, Qt.LeftButton)
                chooser.assert_called_once()
            wait(lambda: not panel.busy and panel.state.get("health", {}).get("subject") == principal)
            contexts = [panel.context.itemText(i) for i in range(panel.context.count())]
            assert contexts == expected
            assert panel.state["health"]["runtime_enabled"] is False
            assert not view.run_action.isEnabled() and not view.debug_action.isEnabled()
            view.run_script()
            view.debug_script()
            assert "Disconnect before using local Run" in view.console.toPlainText()
            assert "Disconnect before using local Debug" in view.console.toPlainText()
            assert not view.run_controller.running and not view.debug_controller.running and not marker.exists()
            report["identities"][principal] = {
                "visible_contexts": contexts, "selected_context": panel.context.currentText(),
                "permissions": sorted(panel.state["health"]["permissions"]),
                "remote_runtime_enabled": False, "disabled_local_actions": True, "direct_local_calls_rejected": True,
            }
            if principal == "alice":
                procedure = panel.procedures.currentData()
                assert procedure["procedure_id"] == "windows-demo" and panel.reserve_button.isEnabled()
                QTest.mouseClick(panel.reserve_button, Qt.LeftButton)
                wait(lambda: not panel.busy and panel.executions.topLevelItemCount() == 1)
                execution = panel.executions.topLevelItem(0).data(0, Qt.UserRole)
                assert execution["lifecycle"] == "RESERVED" and execution["owner"] == principal
                report["reservation"] = {
                    "execution_id": execution["id"], "procedure_id": procedure["procedure_id"],
                    "source_revision": procedure["source_revision"], "source_sha256": procedure["source_sha256"],
                    "lifecycle": execution["lifecycle"], "owner": principal,
                    "native_start_action_available": hasattr(panel, "launch_button"),
                }
            if principal == "observer":
                assert not any(button.isEnabled() for button in (
                    panel.reserve_button, panel.claim_button, panel.accept_button, panel.reject_button, panel.rebind_button,
                ))
                report["identities"][principal]["mutation_controls_disabled"] = True
            QTest.mouseClick(panel.disconnect_button, Qt.LeftButton)
            wait(lambda: not panel.busy and panel.client is None and view.run_action.isEnabled())
        view.run_action.trigger()
        wait(lambda: marker.exists() and not view.run_controller.running)
        assert marker.read_text().splitlines() == ["one"]
        report["explicit_disconnect_restored_local_run"] = True
        report["passed"] = True
    finally:
        view.close()
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
