"""Independently compare offline Context checkpoints from the active state-volume failure."""

import argparse
import json
from pathlib import Path
import runpy


VERIFY = """
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

def read_archive(name, expected):
    directory = Path("/archive") / name
    manifest = (directory / "manifest.json").read_bytes()
    manifest_digest = hashlib.sha256(manifest).hexdigest()
    assert manifest_digest == expected
    spec = json.loads(manifest)
    path = directory / "context.sqlite3"
    with path.open("rb") as source:
        assert hashlib.file_digest(source, "sha256").hexdigest() == spec["database_sha256"]
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        events = db.execute("SELECT sequence,type,body FROM events ORDER BY sequence").fetchall()
        holds = db.execute("SELECT procedure_id,execution_id FROM reservations ORDER BY procedure_id").fetchall()
        spent = db.execute("SELECT slot,incarnation,spent FROM workers ORDER BY slot").fetchall()
        executions = db.execute("SELECT id,lifecycle,control_state FROM executions ORDER BY id").fetchall()
        assert len(events) == spec["audit_events"] and events[-1][0] == spec["last_sequence"]
        digest = hashlib.sha256()
        for row in events:
            digest.update(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode() + b"\\n")
        assert digest.hexdigest() == spec["audit_sha256"]
        return events, holds, spent, executions, {
            "manifest_sha256": manifest_digest,
            "database_sha256": spec["database_sha256"],
            "audit_sha256": spec["audit_sha256"],
            "incarnation": spec["incarnation"],
            "integrity": "ok",
        }
    finally:
        db.close()

old_events, old_holds, old_spent, old_execs, old = read_archive("before-enospc", sys.argv[1])
new_events, new_holds, new_spent, new_execs, new = read_archive("recovered-from-enospc", sys.argv[2])
assert old_events == new_events[:len(old_events)] and old["incarnation"] != new["incarnation"]
assert old_holds == new_holds and len(old_holds) == 2
assert set(old_spent).issubset(new_spent) and sum(row[2] for row in new_spent) == 1
added_workers = sorted(set(new_spent).difference(old_spent))
assert added_workers == [("recovery-slot", "incarnation-after-fence", 0)]
assert {row[1] for row in old_execs} == {"RESERVED", "STARTING"}
assert {row[0] for row in old_execs} == {row[0] for row in new_execs} == {row[1] for row in new_holds}
assert all(state == control == "RECOVERY_REQUIRED" for _, state, control in new_execs)
assert sum(event[1] == "CONTROL_CONNECTION_OPENED" for event in new_events) == 1
print(json.dumps({
    "before": old, "after": new, "identical_original_event_rows": len(old_events),
    "appended_event_types": [row[1] for row in new_events[len(old_events):]],
    "identical_reservations": new_holds, "preserved_worker_incarnations": old_spent,
    "added_worker_incarnations": added_workers,
    "session_open_audit_rows": 1, "recovered_executions": new_execs,
}))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    args = parser.parse_args()
    fixture_tools = runpy.run_path(str(Path(__file__).with_name("compose_fixture.py")))
    fixture = fixture_tools["Fixture"](args.case)
    receipt = json.loads((args.probe / "result.json").read_text())
    assert receipt["passed"] and receipt["cleanup"]["temporary_state_filesystem_removed"]
    first_pin = receipt["active"]["hot_checkpoint"]["manifest_sha256"]
    final_pin = receipt["recovered"]["durable_checkpoint"]["manifest_sha256"]
    result = fixture.helper(
        ["-I", "-c", VERIFY, first_pin, final_pin],
        volumes=fixture.bind("archive", "/archive", readonly=True),
    )
    verified = json.loads(result.stdout)
    (args.probe / "archives.json").write_text(json.dumps(verified, indent=2) + "\n")
    print(json.dumps(verified))


if __name__ == "__main__":
    main()
