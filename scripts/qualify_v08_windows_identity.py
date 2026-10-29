"""Bind the Windows diagnostic to original dev7 source and actual installed bytes."""

import base64
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "b1472b4d5a515b9082db139fb8e16b63677a052e"
ALLOWED = {
    ".github/workflows/v08-windows-source.yml",
    "scripts/v08_windows_journal.py",
    "scripts/qualify_v08_windows_identity.py",
}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main():
    result = dict(
        stage=sys.argv[1],
        full_v08_qualified=False,
        scope="Windows source suite; original Docker/Linux exclusions retained",
        native_spell_executed=False,
        installed_joint_recovery=False,
        platform=platform.platform(),
        python=sys.version,
        executable=sys.executable,
        pid=os.getpid(),
        run_id=os.environ.get("GITHUB_RUN_ID"),
        run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT"),
        passed=False,
    )
    try:
        assert sys.platform == "win32" and sys.version_info[:2] == (3, 13)
        assert git("merge-base", REFERENCE, "HEAD") == REFERENCE
        assert (
            set(git("diff", "--name-only", REFERENCE, "HEAD").splitlines()) <= ALLOWED
        )
        assert not git("status", "--porcelain", "--untracked-files=no")
        result.update(
            commit=git("rev-parse", "HEAD"), tree=git("rev-parse", "HEAD^{tree}")
        )
        result["source_sha256"] = {}
        for name in git("ls-tree", "-r", "--name-only", REFERENCE).splitlines():
            if name.startswith(("src/", "tests/")) or name in (
                "pyproject.toml",
                "README.md",
            ):
                expected = subprocess.check_output(
                    ["git", "show", REFERENCE + ":" + name], cwd=ROOT
                )
                actual = (ROOT / name).read_bytes()
                # Windows checkout representations are compared to Git's own
                # configured checkout conversion, without rewriting input files.
                checkout = subprocess.check_output(
                    ["git", "cat-file", "--filters", REFERENCE + ":" + name], cwd=ROOT
                )
                assert actual == checkout, name
                result["source_sha256"][name] = dict(
                    git_sha256=hashlib.sha256(expected).hexdigest(),
                    checkout_sha256=hashlib.sha256(actual).hexdigest(),
                )
        if sys.argv[1].startswith("after"):
            result["installed_record_payloads"] = {}
            for name in ("PySide6-Essentials", "shiboken6", "openbexi-ide"):
                distribution = metadata.distribution(name)
                count = 0
                for entry in distribution.files or ():
                    if entry.hash:
                        raw = distribution.locate_file(entry).read_bytes()
                        assert entry.hash.mode == "sha256", str(entry)
                        observed = (
                            base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
                            .rstrip(b"=")
                            .decode()
                        )
                        assert observed == entry.hash.value, str(entry)
                        count += 1
                assert count > 0, name
                result["installed_record_payloads"][name] = dict(
                    version=distribution.version, verified=count
                )
        result["passed"] = True
    except Exception as error:
        result["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        path = ROOT / ".qualification/windows" / (sys.argv[1] + "-identity.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
