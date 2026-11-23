"""Run the packaged JetBrains Swing workspace with a settings-only Project test object."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    for name in ("sdk", "plugin", "interpreter", "case", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--worker", required=True)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    jar = out / "openbexi-spell.jar"
    with zipfile.ZipFile(args.plugin) as outer:
        jar.write_bytes(outer.read("openbexi-spell/lib/openbexi-spell.jar"))
    sdk = args.sdk.resolve()
    classpath = os.pathsep.join([str(jar), str(sdk / "lib/*"), str(out)])
    source = Path(__file__).with_name("GatewayComponentProbe.java")
    product = json.loads((sdk / "product-info.json").read_text())
    report = {"sdk": {k: product[k] for k in ("name", "version", "buildNumber")},
              "zip_sha256": sha(args.plugin), "jar_sha256": sha(jar), "source_sha256": sha(source),
              "wrapper_sha256": sha(Path(__file__)), "case_sha256": sha(args.case / "case.json"), "commands": []}
    try:
        for name, command in (("compile", [sdk / "jbr/bin/javac.exe", "--release", "21", "-encoding", "UTF-8",
                                          "-classpath", classpath, "-d", out, source]),
                              ("swing", [sdk / "jbr/bin/java.exe", "-classpath", classpath, "GatewayComponentProbe",
                                        args.interpreter.resolve(), args.case.resolve(), args.worker, out / "swing"])):
            cmd = list(map(str, command))
            with (out / (name + ".log")).open("wb") as log:
                res = subprocess.run(cmd, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=230)
            report["commands"].append({"argv": cmd, "exit_code": res.returncode, "log_sha256": sha(out / (name + ".log"))})
            res.check_returncode()
    finally:
        if (out / "swing/result.json").is_file():
            report["swing"] = json.loads((out / "swing/result.json").read_text())
            report["screenshots"] = {p.name: sha(p) for p in (out / "swing").glob("*.png")}
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
