"""Drive installed native-launch widgets and collect a matched read-only worker observation."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import inspect
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QFileDialog, QLabel, QPushButton
from openbexi_ide.app import MainWindow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--connection-file", default="connection.json", choices=("connection.json", "ipv4.json"))
    parser.add_argument("--worker", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prompt", action="store_true", help="Answer the approved YES/NO native qualification procedure")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    fixture = json.loads((args.case / "case.json").read_text())
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    views = []
    report = {
        "passed": False, "python": sys.executable, "qt_platform": app.platformName(),
        "ide_version": importlib.metadata.version("openbexi-ide"),
        "ide_origin": str(Path(inspect.getfile(MainWindow)).resolve()),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixture_sha256": hashlib.sha256((args.case / "case.json").read_bytes()).hexdigest(),
        "worker": args.worker, "worker_image": fixture["worker_image"], "runtime_image": fixture["image"], "events": [],
        "file_picker": "Supplied the existing role-specific connection file; all other widget actions and TLS requests ran normally.",
        "connection_filename": args.connection_file,
    }

    def event(name, **fields):
        row = {"event": name, "time": datetime.now(timezone.utc).isoformat(), **fields}
        report["events"].append(row)
        with (output / "events.jsonl").open("a", encoding="utf-8") as journal:
            journal.write(json.dumps(row) + "\n")
        print(name, flush=True)

    def wait(condition, label, timeout=25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if condition():
                return
            QTest.qWait(30)
        raise AssertionError(f"Timed out {label}: " + repr([v.spell_server_panel.status.text() for v in views]))

    def connect(role):
        project = output / role
        project.mkdir()
        source = project / "ordinary.py"
        source.write_text("raise RuntimeError('Unexpected local interpreter launch')\n")
        view = MainWindow(project, QSettings(str(output / (role + ".ini")), QSettings.IniFormat))
        views.append(view)
        view.show()
        view.open_file(source)
        panel = view.spell_server_panel
        view.output_tabs.setCurrentWidget(panel)
        wait(lambda: panel.connect_button.isVisible() and panel.connect_button.isEnabled(), "opening Connect")
        private_path = (args.case / role / args.connection_file).resolve(strict=True)
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(private_path), "JSON (*.json)")) as chooser:
            QTest.mouseClick(panel.connect_button, Qt.LeftButton)
            chooser.assert_called_once()
        wait(lambda: not panel.busy and panel.state.get("health", {}).get("subject") == role, f"connecting {role}")
        assert not view.run_action.isEnabled() and not view.debug_action.isEnabled()
        return panel

    def logs():
        result = subprocess.run(["docker", "logs", args.worker], capture_output=True, timeout=6)
        result.check_returncode()
        rows = []
        for line in (result.stdout + result.stderr).splitlines():
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def observed(name):
        nonlocal next_check, observations
        if time.monotonic() >= next_check:
            observations = logs()
            next_check = time.monotonic() + 1
        return any(row.get("event") == name and row.get("execution_id") == report["execution_id"] for row in observations)

    def screenshot(view, name):
        target = output / (name + ".png")
        assert view.grab().save(str(target))
        report.setdefault("screenshots_sha256", {})[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()

    def answer_native_prompt(owner, observer):
        question = "Continue the qualification procedure?"
        wait(lambda: not owner.busy and owner.prompt_button.isVisible() and owner.prompt_button.isEnabled(),
             "waiting for the owner's native prompt", 48)
        QTest.mouseClick(observer.refresh_button, Qt.LeftButton)
        wait(lambda: not observer.busy and observer.executions.topLevelItemCount() == 1, "refreshing prompt observer")
        observer.executions.setCurrentItem(observer.executions.topLevelItem(0))
        observer_row = observer.selected()
        assert observer_row["id"] == report["execution_id"]
        assert "native_prompt_pending" not in observer_row and question not in json.dumps(observer_row)
        assert not observer.prompt_button.isVisible() and observer.prompt_dialog is None
        event("observer_filtered_pending_prompt", execution_id=observer_row["id"])
        wait(lambda: not owner.busy and owner.prompt_button.isEnabled(), "opening owner prompt")
        QTest.mouseClick(owner.prompt_button, Qt.LeftButton)
        wait(lambda: owner.prompt_dialog is not None and owner.prompt_dialog.isVisible(), "opening the native dialog")
        dialog = owner.prompt_dialog
        assert dialog.windowTitle() == "Native procedure prompt"
        assert any(question in label.text() for label in dialog.findChildren(QLabel) if label.isVisible())
        choices = next(widget for widget in dialog.findChildren(QComboBox) if widget.isVisible())
        send = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Send answer")
        assert choices.currentIndex() == -1 and not send.isEnabled()
        options = [choices.itemText(index) for index in range(choices.count())]
        normalized = tuple(option.strip().casefold() for option in options)
        assert normalized in {("y", "n"), ("yes", "no")}, options
        screenshot(dialog, "owner-native-prompt")
        event("owner_displayed_native_prompt", question=question, choices=options, send_requires_selection=True)
        # The native worker's workspace is tmpfs and vanishes on process exit.
        # Start the read-only marker observation before submitting the real reply.
        observe_marker = """
import hashlib, json, time
from pathlib import Path
marker = Path('/workspace/approved-procedure-completed')
expected = b'Operator confirmed the qualification prompt'
deadline = time.monotonic() + 55
print("watching", flush=True)
while time.monotonic() < deadline:
    if marker.is_file() and marker.read_bytes() == expected:
        print(json.dumps(dict(path=str(marker), bytes=len(expected), sha256=hashlib.sha256(expected).hexdigest())), flush=True)
        break
    time.sleep(0.02)
else:
    raise RuntimeError('Native prompt marker did not appear')
"""
        with subprocess.Popen(
            ["docker", "exec", args.worker, "python", "-I", "-c", observe_marker],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ) as watcher:
            with ThreadPoolExecutor(max_workers=1) as reader:
                ready = reader.submit(watcher.stdout.readline)
                wait(ready.done, "starting the read-only worker marker observation", 10)
                assert ready.result().strip() == b"watching"
            QTest.keyClick(choices, Qt.Key_Home)
            assert choices.currentIndex() == 0 and send.isEnabled()
            QTest.mouseClick(send, Qt.LeftButton)
            event("owner_sent_native_answer", selected_index=0)
            wait(lambda: watcher.poll() is not None, "reading the executing procedure's marker", 65)
            raw, error = watcher.communicate(timeout=2)
            assert watcher.returncode == 0, error.decode(errors="replace")
            event("verified_native_post_answer_marker", **json.loads(raw))

    def verify_prompt_receipt():
        inspect_prompt = """
import json, sqlite3, sys
execution = sys.argv[1]
with sqlite3.connect('file:/state/context.sqlite3?mode=ro', uri=True) as db:
    db.row_factory = sqlite3.Row
    sql = ("SELECT p.prompt_id, p.state AS prompt_state, p.outcome, r.owner, r.action, "
           "r.state AS reply_state, r.diagnostic FROM native_prompts p "
           "JOIN native_prompt_replies r USING (execution_id, prompt_id) WHERE p.execution_id=?")
    matches = db.execute(sql, (execution,)).fetchall()
    assert len(matches) == 1
    receipt = dict(matches[0])
    assert receipt["prompt_state"] == "CLOSED" and receipt["outcome"] == "ANSWER_SELECTED"
    assert receipt["owner"] == "alice" and receipt["action"] == "ANSWER"
    assert receipt["reply_state"] == "CONSUMED_UNPROVEN"
    print(json.dumps(receipt))
"""
        receipt = subprocess.check_output(
            ["docker", "exec", fixture["prefix"] + "-context", "python", "-I", "-c",
             inspect_prompt, report["execution_id"]],
            timeout=8,
        )
        event("verified_durable_prompt_and_reply", **json.loads(receipt))

    next_check, observations = 0, []
    try:
        assert app.platformName() == "windows"
        assert Path(report["ide_origin"]).is_relative_to(Path(sys.prefix).resolve())
        alice = connect("alice")
        observer = connect("observer")
        assert not observer.launch_button.isEnabled() and not observer.reserve_button.isEnabled()
        event("roles_connected", context=alice.context.currentText(), subject="alice", observer="observer")
        procedure = alice.procedures.currentData()
        assert procedure["source_sha256"] == fixture["source_sha256"] and procedure["source_revision"] == fixture["revision"]
        assert alice.reserve_button.isEnabled()
        QTest.mouseClick(alice.reserve_button, Qt.LeftButton)
        wait(lambda: not alice.busy and alice.executions.topLevelItemCount() == 1, "reserving native source")
        row = alice.executions.topLevelItem(0)
        alice.executions.setCurrentItem(row)
        reservation = row.data(0, Qt.UserRole)
        assert reservation["lifecycle"] == "RESERVED" and alice.launch_button.isEnabled()
        report["execution_id"] = reservation["id"]
        event("reserved", execution_id=reservation["id"], source_sha256=procedure["source_sha256"], revision=procedure["source_revision"])
        screenshot(views[0], "reserved")
        QTest.mouseClick(alice.launch_button, Qt.LeftButton)
        event("start_native_clicked")
        wait(lambda: observed("native-ready"), "waiting for native-ready", 100)
        ready = next(row for row in observations if row.get("event") == "native-ready" and row.get("execution_id") == report["execution_id"])
        assert ready["native_status"] == "PAUSED" and ready["namespace_pid"] > 0
        event("native_ready", execution_id=ready["execution_id"], status=ready["native_status"], namespace_pid=ready["namespace_pid"])
        wait(lambda: not alice.busy and alice.command_buttons["CMD_RUN"].isEnabled(), "enabling Run")
        QTest.mouseClick(alice.command_buttons["CMD_RUN"], Qt.LeftButton)
        event("run_continue_clicked")
        if args.prompt:
            answer_native_prompt(alice, observer)
        wait(lambda: observed("native-finished"), "waiting for native procedure completion", 100)
        finished = next(r for r in observations if r.get("event") == "native-finished" and r.get("execution_id") == report["execution_id"])
        assert finished["native_status"] == "FINISHED" and finished["native_lifecycle_receipts_settled"]
        event("native_finished", execution_id=finished["execution_id"], native_status=finished["native_status"],
              lifecycle_receipts_settled=finished["native_lifecycle_receipts_settled"], hold_retained=finished["hold_retained"])
        wait(lambda: not alice.busy and alice.executions.topLevelItem(0).data(0, Qt.UserRole).get("native_root_result") == "FINISHED",
             "displaying the owner terminal observation", 38)
        QTest.mouseClick(observer.refresh_button, Qt.LeftButton)
        wait(lambda: not observer.busy and observer.executions.topLevelItemCount() == 1, "refreshing observer")
        for panel, view, role in ((alice, views[0], "owner"), (observer, views[1], "observer")):
            row = panel.executions.topLevelItem(0)
            panel.executions.setCurrentItem(row)
            observed_row = row.data(0, Qt.UserRole)
            assert observed_row["id"] == report["execution_id"] and observed_row["native_root_result"] == "FINISHED"
            column = next(i for i in range(panel.executions.columnCount()) if panel.executions.headerItem().text(i) == "Native result")
            assert row.text(column) == "FINISHED" and not panel.executions.isColumnHidden(column)
            assert not panel.launch_button.isEnabled() and not any(b.isEnabled() for b in panel.command_buttons.values())
            screenshot(view, role + "-finished")
            event(role + "_displayed_result", execution_id=observed_row["id"], lifecycle=observed_row["lifecycle"],
                  native_root_result=row.text(column), native_controls_disabled=True)
        if args.prompt:
            verify_prompt_receipt()
        report["passed"] = True
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        report["worker_event_names"] = [row["event"] for row in observations if isinstance(row.get("event"), str)]
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        for view in reversed(views):
            view.close()
        app.processEvents()


if __name__ == "__main__":
    main()
