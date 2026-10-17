"""Observe a real SAFE-mode command failure, then recover in NOMINAL mode."""
from spell.lang.functions import Display, GetTM, Send
from spell.lib.exception import SpellException
config = dict(HandleError=False, PromptUser=False, Confirm=False)
assert Send(command='TC.SIMULATOR.SET_MODE', args=[['MODE', 'SAFE']], **config)
try:
    result = Send(command='CMD1', **config)
except SpellException:
    result = False
assert result is False
assert GetTM('TM.PAYLOAD.ENABLED', Wait=False, HandleError=False) is False
Display('EXPECTED_FAILURE: SAFE mode blocked payload enabling')
assert Send(command='TC.SIMULATOR.SET_MODE', args=[['MODE', 'NOMINAL']], **config)
assert Send(command='CMD1', **config)
assert GetTM('TM.PAYLOAD.ENABLED', Wait=False, HandleError=False) is True
assert Send(command='CMD2', **config)
Display('SPELL_EXECUTION_FAILURE_RECOVERY_PASS')
