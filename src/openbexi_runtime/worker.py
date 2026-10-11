"""Trusted script bootstrap. Run only as a separate isolated interpreter."""
from pathlib import Path
import runpy
import sys


def main() -> None:
    if not sys.flags.isolated:
        raise RuntimeError("The development worker must be started with -I")
    if len(sys.argv) < 3:
        raise RuntimeError("Missing project/script launch arguments")
    project, script = (Path(value).resolve() for value in sys.argv[1:3])
    if not project.is_dir() or not script.is_file() or not script.is_relative_to(project):
        raise RuntimeError("Invalid project/script boundary")
    runtime_root = str(Path(__file__).resolve().parents[1])
    sys.path.insert(0, runtime_root)
    try:
        from openbexi_runtime.processes import own_worker_tree
    finally:
        sys.path.remove(runtime_root)
    own_worker_tree()
    sys.path[:0] = list(dict.fromkeys([str(script.parent), str(project)]))
    sys.argv = [str(script), *sys.argv[3:]]
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
