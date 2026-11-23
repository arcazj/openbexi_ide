"""Reproduce the published Windows baseline in a new directory, outside either checkout."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import urllib.request
import zipfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "OpenBEXI-qualification"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def release(repo, tag, wheel_count, destination):
    base = f"https://api.github.com/repos/arcazj/{repo}/releases/tags/{tag}"
    info = json.loads(download(base))
    by_name = {asset["name"]: asset for asset in info["assets"]}
    checksums = download(by_name["SHA256SUMS.txt"]["browser_download_url"])
    (destination / f"{repo}-SHA256SUMS.txt").write_bytes(checksums)
    listed = {line.split()[1].lstrip("*"): line.split()[0] for line in checksums.decode().splitlines() if line.strip()}
    artifacts = {}
    for name, asset in sorted(by_name.items()):
        if not name.endswith(".whl"):
            continue
        path = destination / name
        path.write_bytes(download(asset["browser_download_url"]))
        sha = digest(path)
        if sha != listed[name] or "sha256:" + sha != asset["digest"] or path.stat().st_size != asset["size"]:
            raise RuntimeError("Release wheel integrity failed for " + name)
        artifacts[name] = {"bytes": asset["size"], "sha256": sha, "asset_id": asset["id"]}
    if len(artifacts) != wheel_count:
        raise RuntimeError(f"Expected {wheel_count} wheels for {tag}, found {list(artifacts)}")
    return {"tag": tag, "release_id": info["id"], "url": info["html_url"], "wheel_assets": artifacts,
            "checksum_file_sha256": hashlib.sha256(checksums).hexdigest(), "asset_names": sorted(by_name)}


INVENTORY = """from importlib import metadata, util
import json, os, platform, sys
print(json.dumps({"python":sys.version, "python_path":sys.executable, "platform":platform.platform(),
    "prefix":sys.prefix, "base_prefix":sys.base_prefix, "sys_path":sys.path,
    "spell_modules":{k:util.find_spec(k) is not None for k in
        ["openbexi_spell_plugin","openbexi_spell_host","openbexi_spell_shared","openbexi_spell_server","openbexi_spell_dss","spell","dss"]},
    "packages":{d.metadata["Name"]:d.version for d in metadata.distributions()}}))
"""


VERIFY = """from email.parser import BytesParser
import importlib.metadata as md,json,pathlib,sys,zipfile
installed={}
for name in sys.argv[1:]:
    wheel=pathlib.Path(name)
    with zipfile.ZipFile(wheel) as z:
        for entry in z.namelist():
            if entry.endswith(".dist-info/METADATA"):
                distribution=md.distribution(BytesParser().parsebytes(z.read(entry))["Name"])
                break
        else:
            raise ValueError("Missing metadata")
        counts=0
        for entry in z.namelist():
            if entry.endswith("/") or entry.endswith(".dist-info/RECORD"):
                continue
            file=pathlib.Path(distribution.locate_file(entry)).resolve()
            assert file.is_relative_to(pathlib.Path(sys.prefix).resolve()) and file.read_bytes()==z.read(entry),entry
            counts+=1
        installed[wheel.name]={"members_verified_except_regenerated_RECORD":counts,"version":distribution.version,
            "direct_url":json.loads(distribution.read_text("direct_url.json"))}
print(json.dumps(installed))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ide-repo", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    repo = args.ide_repo.resolve()
    if root.is_relative_to(repo):
        raise ValueError("Place the clean environment outside the IDE checkout")
    wheels = root / "wheels"
    wheels.mkdir()
    python = root / "venv" / "Scripts" / "python.exe"
    env = os.environ.copy()
    for name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        env.pop(name, None)
    env["QT_QPA_PLATFORM"] = "windows"
    env["PYTHONNOUSERSITE"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    report = {"platform": platform.platform(), "base_executable": sys.executable, "commands": [],
              "scope": "Windows clean virtual environment on existing workstation. Published RC1 baseline.", "passed": False}

    def run(label, command, *, timeout=240):
        argv = [str(arg) for arg in command]
        row = {"label": label, "argv": argv}
        report["commands"].append(row)
        result = subprocess.run(argv, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        log = root / (label + ".log")
        log.write_bytes(result.stdout)
        row.update(exit_code=result.returncode, log_sha256=digest(log))
        if result.returncode:
            raise RuntimeError(f"{label} returned {result.returncode}; see {log}")
        return result.stdout.decode("utf-8", errors="replace")

    try:
        report["ide"] = release("openbexi_ide", "v1.2.1", 1, wheels)
        report["spell"] = release("openbexi_spell_plugin", "v0.8-rc1", 4, wheels)
        ide = wheels / next(iter(report["ide"]["wheel_assets"]))
        plugins = [wheels / name for name in report["spell"]["wheel_assets"]]
        lock = repo / "requirements-windows-cp313.lock"
        harness = repo / "scripts/distribution_desktop.py"
        report["inputs"] = {str(path): digest(path) for path in (Path(__file__), lock, harness)}
        report["git"] = {name: run("identity-" + name, ["git", "-C", repo, "rev-parse", ref]).strip()
                         for name, ref in (("ide_wheel_commit", "v1.2.1^{}"), ("ide_harness_checkout", "HEAD"))}
        run("venv", [sys.executable, "-I", "-m", "venv", python.parents[1]])
        pip = [python, "-I", "-m", "pip"]
        run("download-desktop-deps", [*pip, "download", "--index-url", "https://pypi.org/simple", "--only-binary=:all:",
                                      "--require-hashes", "-r", lock, "-d", wheels])
        run("install-desktop-deps", [*pip, "install", "--no-index", "--find-links", wheels, "--only-binary=:all:",
                                     "--require-hashes", "-r", lock])
        run("install-published-ide", [*pip, "install", "--no-index", "--no-deps", ide])
        before = json.loads(run("before-spell", [python, "-I", "-c", INVENTORY]))
        report["before_spell"] = before
        if any(before["spell_modules"].values()) or any("spell" in k.lower() for k in before["packages"]):
            raise RuntimeError("SPELL package present before the ordinary Python checks")
        report["published_ide_members"] = json.loads(run("verify-ide-members", [python, "-I", "-c", VERIFY, ide]))
        run("ordinary-python", [python, "-I", harness, "--output", root / "desktop"])
        report["ordinary_python"] = json.loads((root / "desktop/result.json").read_text())
        if not report["ordinary_python"]["passed"] or report["ordinary_python"]["qt_platform"] != "windows":
            raise RuntimeError("Windows Qt desktop Run/Debug failed")
        run("download-dss-deps", [*pip, "download", "--index-url", "https://pypi.org/simple", "--only-binary=:all:",
                                  "-d", wheels, "grpcio==1.84.0", "protobuf==7.36.2"])
        run("install-published-spell", [*pip, "install", "--no-index", "--find-links", wheels, *plugins])
        run("installed-dependencies", [*pip, "check"])
        report["after_spell"] = json.loads(run("after-spell", [python, "-I", "-c", INVENTORY]))
        report["published_spell_members"] = json.loads(run("verify-spell-members", [python, "-I", "-c", VERIFY, *plugins]))
        run("public-remote-client-cli", [python.parent / "openbexi-spell-client.exe", "--help"])
        run("public-host-cli", [python.parent / "openbexi-spell-host.exe", "--help"])
        report["wheels"] = {wheel.name: digest(wheel) for wheel in sorted(wheels.glob("*.whl"))}
        report["passed"] = True
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        (root / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
