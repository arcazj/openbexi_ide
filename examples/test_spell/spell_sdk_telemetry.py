"""Read current TM1 from the browser lab DSS; sends no commands.

Run with Python in the supplied browser desktop. Start the lab DSS first.
The development SDK reads one current sample; it does not wait for fresh data.
"""
import importlib.util
if importlib.util.find_spec('spell.lib') is not None:
    from spell.lang.functions import Display, GetTM, Verify
    from spell.lang.constants import eq
    value = GetTM('TM.POWER.BUS_VOLTAGE', Wait=False, HandleError=False)
    assert value == 28.0
    assert Verify('TM.POWER.BUS_VOLTAGE', eq, 28.0, Wait=False, Retries=0, HandleError=False)
    Display('SPELL profile: original native runtime; read-only telemetry')
else:
    from openbexi_spell_plugin.runtime import activate
    from spell.lang import Display, GetTM, Verify
    activate()
    Display('SPELL profile: browser development SDK; read-only telemetry')
    value = GetTM('TM1', Wait=False)
    assert Verify('TM1', -1000000, Op='GT')
    assert Verify('TM1', 1000000, Op='LT')
Display('Current value: ' + str(value))
Display('SPELL_TELEMETRY_PASS')
