"""Verify true/false, AND/OR and boundary conditions without interactive recovery."""
from spell.lang.functions import AND, OR, Display, Verify
from spell.lang.constants import eq, bw, NOACTION
config = dict(Wait=False, Retries=0, PromptUser=False, HandleError=False, OnFalse=NOACTION)
assert Verify('TM.POWER.BUS_VOLTAGE', bw, 28.0, 28.0, **config)
assert not Verify('TM.POWER.BUS_VOLTAGE', eq, 0.0, **config)
assert Verify(AND(['TM.POWER.BUS_VOLTAGE', eq, 28.0], ['TM.PAYLOAD.ENABLED', eq, False]), **config)
assert Verify(OR(['TM.POWER.BUS_VOLTAGE', eq, 0.0], ['TM.POWER.BUS_VOLTAGE', eq, 28.0]), **config)
Display('SPELL_VERIFY_CONDITIONS_PASS')
