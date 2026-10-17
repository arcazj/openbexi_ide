"""if/elif/else, conditional expressions, loops, break, and continue.

Run with Python. The shared implementation is in test_Python.py;
select Step Into in Debug to explore its assertions and examples.
"""
from pathlib import Path
import sys

# Explicit sibling imports also work with isolated Python (-I).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_Python import main

if __name__ == "__main__":
    raise SystemExit(main(["--section", 'control-flow']))
