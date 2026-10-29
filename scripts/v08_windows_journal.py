"""Immediate phase journal for the unchanged Windows IDE source suite."""

import json
import os
from pathlib import Path
import time


def record(row):
    path = Path(".qualification/windows/phases.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(dict(time_ns=time.time_ns(), **row)) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def pytest_collection_finish(session):
    record(dict(event="collection", nodeids=[item.nodeid for item in session.items]))


def pytest_runtest_logreport(report):
    record(
        dict(
            event="phase",
            nodeid=report.nodeid,
            phase=report.when,
            outcome=report.outcome,
            duration=report.duration,
            details=str(report.longrepr) if report.failed or report.skipped else None,
        )
    )


def pytest_sessionfinish(session, exitstatus):
    record(dict(event="finish", exitstatus=int(exitstatus)))
