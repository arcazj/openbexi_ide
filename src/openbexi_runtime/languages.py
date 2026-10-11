"""Optional language support is checked in the selected worker interpreter."""
from pathlib import Path
import subprocess

from .launch import clean_environment


def check_spell(interpreter: Path):
    result = subprocess.run([str(interpreter), '-I', '-B', '-c',
        'import importlib.metadata; import openbexi_spell_plugin; '
        'assert importlib.metadata.version("openbexi-spell-plugin") == "0.1.0"'],
        env=clean_environment(), capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise ValueError('SPELL requires openbexi-spell-plugin 0.1.0 installed in the selected interpreter')
