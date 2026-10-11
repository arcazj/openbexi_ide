"""Headless source-checkout entry point."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from openbexi_runtime.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
