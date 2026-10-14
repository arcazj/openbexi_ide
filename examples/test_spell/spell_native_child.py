"""Child of spell_native_parent.py; can also run as a standalone procedure."""
import spell.lib
from spell.lang.constants import YES_NO
from spell.lang.functions import Display, Prompt
from spell.runtime import Step

Step('child-input', 'Collect the child answer')
choice = Prompt('Child: continue? (0=Yes, 1=No)', Type=YES_NO)
Display('SPELL_CHILD_PASS choice=' + str(choice))
