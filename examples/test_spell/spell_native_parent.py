"""Original native SPELL: run a child, then ask the parent's question.

Requires the qualified child-capable host candidate. Keep spell_native_child.py
in this project. Both prompts accept 0=Yes or 1=No; no commands are sent.
"""
import spell.lib
from pathlib import Path
from spell.lang.constants import YES_NO
from spell.lang.functions import Display, Prompt, StartProc
from spell.runtime import Step

Step('child', 'Run and wait for the child procedure')
directory = Path(__file__).resolve().parent.relative_to(Path.cwd()).as_posix()
assert StartProc((directory + '/' if directory != '.' else '') + 'spell_native_child', HandleError=False)
Step('parent', 'Return control to the parent')
choice = Prompt('Parent: finish this example? (0=Yes, 1=No)', Type=YES_NO)
Display('SPELL_PARENT_PASS choice=' + str(choice))
