"""Verify fresh Windows candidate installation against the two committed build manifests."""

import argparse
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from urllib.parse import unquote, urlsplit


def main():
    parser = argparse.ArgumentParser()
    for name in ("ide", "spell", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--dependencies", type=Path, help="Previously verified local dependency wheels")
    sources.add_argument("--online", action="store_true", help="Download dependencies directly from public PyPI")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).resolve()
    repo = here.parents[5]
    helpers = runpy.run_path(str(here.with_name("qualify_installed.py")))
    digest = helpers["digest"]
    desktop = repo / "scripts/distribution_desktop.py"
    targets = {}
    subjects = {}
    selected = ("ide", "spell_dss", "spell_host", "spell_server", "spell_shared")
    for folder in (args.ide.resolve(), args.spell.resolve()):
        manifest = json.loads((folder / "packages.json").read_text())
        subjects[manifest["repo"]] = {"commit": manifest["commit"], "manifest_sha256": digest(folder / "packages.json")}
        for name, expected in manifest["files"].items():
            if not name.endswith(".whl") or name.split("-", 1)[0] not in {"openbexi_" + s for s in selected}:
                continue
            wheel = folder / name
            if digest(wheel) != expected:
                raise ValueError("Invalid candidate wheel: " + name)
            targets[wheel] = expected
    assert len(targets) == 5 and set(subjects) == {"ide", "spell"}
    py = out / "venv/Scripts/python.exe"
    env = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        env.pop(name, None)
    if args.online:
        for name in list(env):
            if name.startswith("PIP_"):
                del env[name]
        env["PIP_CONFIG_FILE"] = os.devnull
    env.update(QT_QPA_PLATFORM="windows", PYTHONNOUSERSITE="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    report = {"scope": "Unpublished committed Windows candidate", "subjects": subjects,
              "artifacts": {p.name: sha for p, sha in targets.items()},
              "harnesses_sha256": {p.name: digest(p) for p in (here, desktop, here.with_name("qualify_installed.py"))},
              "commands": [], "passed": False}

    def run(label, command):
        argv = list(map(str, command))
        result = subprocess.run(argv, cwd=out, env=env, capture_output=True, timeout=190)
        log = out / (label + ".log")
        log.write_bytes(result.stdout + result.stderr)
        report["commands"].append({"label": label, "argv": argv, "exit_code": result.returncode, "log_sha256": digest(log)})
        result.check_returncode()
        return result.stdout.decode("utf-8")

    def origins(pip_report):
        data = json.loads(pip_report.read_text(encoding="utf-8"))
        packages = {}
        for row in data["install"]:
            origin = row["download_info"]
            url = urlsplit(origin["url"])
            if url.scheme == "file":
                continue  # Directly supplied product wheels are verified separately against packages.json.
            assert url.scheme == "https" and url.hostname == "files.pythonhosted.org"
            packages[row["metadata"]["name"]] = {
                "version": row["metadata"]["version"],
                "file": Path(unquote(url.path)).name,
                "origin": url.hostname,
                "sha256": origin["archive_info"]["hashes"]["sha256"],
            }
        return packages

    try:
        run("new-venv", [sys.executable, "-I", "-m", "venv", py.parents[1]])
        if args.online:
            index = ["--no-cache-dir", "--index-url", "https://pypi.org/simple"]
        else:
            index = ["--no-index", "--find-links", args.dependencies.resolve()]
        pip = [py, "-I", "-m", "pip", "install", *index]
        desktop_report = out / "pip-desktop.json"
        spell_report = out / "pip-spell.json"
        run("desktop-deps", [*pip, "--report", desktop_report, "--require-hashes", "--only-binary=:all:", "-r", repo / "requirements-windows-cp313.lock"])
        app = next(p for p in targets if p.name.startswith("openbexi_ide-"))
        run("install-ide", [*pip, str(app) + "[desktop]"])
        help_output = run("desktop-entry-point", [py.parent / "openbexi-ide.exe", "--help"])
        assert "--project" in help_output and "--file" in help_output
        inv = json.loads(run("before-spell", [py, "-I", "-c", helpers["INVENTORY"]]))
        report["before_spell"] = inv
        assert not any(inv["spell_modules"].values()) and inv["packages"]["openbexi-ide"] == "1.2.2"
        run("ordinary-python", [py, "-I", desktop, "--output", out / "desktop"])
        report["ordinary_python"] = json.loads((out / "desktop/result.json").read_text())
        assert report["ordinary_python"]["passed"] and report["ordinary_python"]["qt_platform"] == "windows"
        run("install-spell", [*pip, "--report", spell_report, "--only-binary=:all:", *[p for p in targets if p != app]])
        run("pip-check", [py, "-I", "-m", "pip", "check"])
        run("remote-entry-point", [py.parent / "openbexi-spell-client.exe", "--help"])
        run("native-host-entry-point", [py.parent / "openbexi-spell-host.exe", "--help"])
        report["after_spell"] = json.loads(run("after-spell", [py, "-I", "-c", helpers["INVENTORY"]]))
        report["verified_wheels"] = json.loads(run("verify-members", [py, "-I", "-c", helpers["VERIFY"], *targets]))
        if args.online:
            downloaded = {**origins(desktop_report), **origins(spell_report)}
            expected = {"pyside6-essentials", "shiboken6", "debugpy", "pygments", "grpcio", "protobuf", "typing-extensions"}
            assert {n.lower().replace("_", "-") for n in downloaded} == expected
            report["online_dependencies"] = downloaded
            report["online_dependency_lock_sha256"] = digest(repo / "requirements-windows-cp313.lock")
            report["pip_report_sha256"] = {p.name: digest(p) for p in (desktop_report, spell_report)}
        report["passed"] = True
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
