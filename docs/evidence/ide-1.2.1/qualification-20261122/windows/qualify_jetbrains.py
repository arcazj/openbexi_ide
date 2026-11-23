"""Install a candidate ZIP in a private real IDE profile and invoke the native v0.8 tool window."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    for name in ("spell-source", "sdk", "plugin", "interpreter", "connection", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    suite = output / "driver"
    (suite / "qualification").mkdir(parents=True)
    for name in ("build.py", "qualify.py"):
        shutil.copyfile(args.spell_source / "jetbrains" / name, suite / name)
    shutil.copyfile(Path(__file__).with_name("HostQualification.java"), suite / "qualification/HostQualification.java")
    env = os.environ.copy()
    env["OPENBEXI_TEST_GATEWAY_CONFIG"] = str(args.connection.resolve(strict=True))
    command = [sys.executable, str(suite / "qualify.py"), "--sdk", str(args.sdk.resolve()), "--plugin", str(args.plugin.resolve()),
               "--interpreter", str(args.interpreter.resolve()), "--output", str(output / "host")]
    with (output / "driver.log").open("wb") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env, cwd=output, timeout=370)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
