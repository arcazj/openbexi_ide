"""Select one named disposable namespace; all operations still use the pinned cluster."""

import os
from pathlib import Path
import runpy
import sys


if __name__ == "__main__":
    _, case, operation, *args = sys.argv
    assert case in {"ten","concurrent","cohort2","admission","fence","final47","final47one"}
    assert operation in {"prepare","deploy","ingress","collect","fence","single","probe","cluster"}
    os.environ["OPENBEXI_KIND_CASE"]=case
    root=Path(__file__).resolve().parent
    script=root.parent/"api/qualify_load.py" if operation=="probe" else root/(operation+".py")
    sys.argv=[str(script),*args]
    runpy.run_path(str(script),run_name="__main__")
