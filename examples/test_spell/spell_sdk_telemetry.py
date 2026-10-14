"""Read current TM1 from the browser lab DSS; sends no commands.

Run with Python in the supplied browser desktop. Start the lab DSS first.
The development SDK reads one current sample; it does not wait for fresh data.
"""
from openbexi_spell_plugin.runtime import activate
from spell.lang import Display, GetTM, Verify

activate()
Display('SPELL profile: browser development SDK; read-only telemetry')
value = GetTM('TM1', Wait=False)
Display('TM1 current value: ' + str(value))
# Compare with a broad physical sanity bound, rather than expecting a moving
# simulator to return the identical value on two separate reads.
assert Verify('TM1', -1000000, Op='GT')
assert Verify('TM1', 1000000, Op='LT')
Display('SPELL_TELEMETRY_PASS')
