"""Resolve an actual two-author Git conflict in the installed Windows IDE."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from importlib.metadata import version

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest
from openbexi_ide.app import MainWindow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    out = parser.parse_args().output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ["QT_QPA_PLATFORM"] = "windows"
    app = QApplication.instance() or QApplication([])
    assert app.platformName() == "windows"
    origin, alice, bob = (out / path for path in ("origin.git", "alice", "bob"))
    report = {"passed": False, "ide": version("openbexi-ide"), "qt": app.platformName(),
              "method": "Two installed IDE editor windows, two local clones and a private bare Git remote.",
              "commands": [], "screenshots": {}}

    def git(where, *args, ok=True):
        run = subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false",
                              "-C", str(where), *map(str, args)], capture_output=True, timeout=10)
        report["commands"].append({"cwd": where.name, "git": list(map(str, args)), "rc": run.returncode})
        if ok:
            run.check_returncode()
        return run.returncode, run.stdout.decode("utf-8").strip()

    def window(project, owner):
        widget = MainWindow(project, QSettings(str(out / (owner + ".ini")), QSettings.IniFormat))
        widget.show()
        app.processEvents()
        editor = widget.open_file(project / "procedure.py")
        assert editor.isVisible() and "Development" in widget.position_label.text()
        return widget, editor

    def write(editor, text):
        editor.selectAll()
        editor.insertPlainText(text)
        assert editor.document().isModified()

    def screenshot(widget, filename):
        dest = out / filename
        assert widget.grab().save(str(dest))
        report["screenshots"][filename] = hashlib.sha256(dest.read_bytes()).hexdigest()

    def choose(title, button, capture=None):
        observations = []
        def answer():
            box = app.activeModalWidget()
            if isinstance(box, QMessageBox):
                observations.append((box.windowTitle(), box.standardButton(box.defaultButton()).name))
                if capture:
                    screenshot(box, capture)
                selected = box.button(button)
                if selected:
                    QTest.mouseClick(selected, Qt.LeftButton)
                else:
                    box.reject()
        QTimer.singleShot(60, answer)
        return observations

    def save(window):
        assert window.save_action.isEnabled()
        window.save_action.trigger()
        app.processEvents()

    try:
        git(out, "init", "--bare", "--initial-branch=main", origin)
        git(out, "clone", origin, alice)
        git(alice, "config", "user.name", "Alice")
        git(alice, "config", "user.email", "alice@example.invalid")
        (alice / "procedure.py").write_bytes(b"steps = ['baseline']\n")
        git(alice, "add", "procedure.py")
        git(alice, "commit", "-m", "Baseline procedure")
        git(alice, "push", "-u", "origin", "main")
        git(out, "clone", origin, bob)
        git(bob, "config", "user.name", "Bob")
        git(bob, "config", "user.email", "bob@example.invalid")
        wa, ea = window(alice, "Alice")
        wb, eb = window(bob, "Bob")
        write(ea, "steps = ['alice-check']\n")
        save(wa)
        write(eb, "steps = ['bob-check']\n")
        save(wb)
        for project, message in ((alice, "Alice procedure check"), (bob, "Bob procedure check")):
            git(project, "add", "procedure.py")
            git(project, "commit", "-m", message)
        git(alice, "push")
        assert git(bob, "push", ok=False)[0] != 0
        git(bob, "fetch", "origin")
        assert git(bob, "merge", "--no-edit", "origin/main", ok=False)[0] == 1
        assert len(git(bob, "ls-files", "-u", "--", "procedure.py")[1].splitlines()) == 3
        conflict = (bob / "procedure.py").read_bytes()
        assert b"<<<<<<< HEAD" in conflict and b">>>>>>> origin/main" in conflict
        write(eb, "steps = ['unsaved-old-buffer']\n")
        events = choose("File changed outside the IDE", QMessageBox.Cancel, "stale-save.png")
        save(wb)
        assert events == [("File changed outside the IDE", "Cancel")]
        assert (bob / "procedure.py").read_bytes() == conflict
        discard = choose("Save changes?", QMessageBox.Discard)
        wb.close_tab(wb.tabs.indexOf(eb))
        assert discard and discard[0][0] == "Save changes?"
        merged = wb.open_file(bob / "procedure.py")
        assert all(marker in merged.toPlainText() for marker in ("<<<<<<<", "alice-check", "bob-check", ">>>>>>>"))
        screenshot(wb, "conflict-in-editor.png")
        resolved = "steps = ['alice-check', 'bob-check']\n"
        write(merged, resolved)
        save(wb)
        assert (bob / "procedure.py").read_text() == resolved
        git(bob, "add", "procedure.py")
        git(bob, "commit", "-m", "Resolve procedure conflict with both authors' checks")
        git(bob, "push")
        git(alice, "pull", "--ff-only")
        wa.close_tab(wa.tabs.indexOf(ea))
        assert wa.open_file(alice / "procedure.py").toPlainText() == resolved
        screenshot(wa, "converged-ide.png")
        heads = [git(repo, "rev-parse", "HEAD")[1] for repo in (alice, bob, origin)]
        assert len(set(heads)) == 1
        assert len(git(bob, "rev-list", "--parents", "-n", "1", "HEAD")[1].split()) == 3
        assert all(not git(repo, "status", "--porcelain", "--untracked-files=no")[1] for repo in (alice, bob))
        report.update(passed=True, final_commit=heads[0], merge_parents=2, stages_at_conflict=3,
                      stale_save_default="Cancel", final_content_sha256=hashlib.sha256(resolved.encode()).hexdigest(),
                      git_version=git(out, "--version")[1], interpreter=sys.executable)
        wa.close()
        wb.close()
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
