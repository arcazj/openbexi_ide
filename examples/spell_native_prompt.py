"""Original native SPELL: answer two YES_NO prompts using the console.

Type 0 for Yes or 1 for No, then Send/Enter. Both answers are valid.
The procedure records the choices locally and sends no commands.
"""
import json
from pathlib import Path
import spell.lib
from spell.lang.constants import YES_NO
from spell.lang.functions import Display, Prompt
from spell.runtime import Step

Step('operator', 'Collect two operator decisions')
first = Prompt('Continue the demonstration? (0=Yes, 1=No)', Type=YES_NO)
second = Prompt('Record the second choice? (0=Yes, 1=No)', Type=YES_NO)
assert type(first) is bool and type(second) is bool
Path('spell_prompt_result.json').write_text(
    json.dumps({'first': first, 'second': second}) + '\n', encoding='utf-8')
Display('SPELL_PROMPT_PASS ' + str([first, second]))
