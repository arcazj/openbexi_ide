"""Expected bounded wait timeout, followed by a successful telemetry read."""
import time
from spell.lang.functions import Display, GetTM, WaitFor
for attempt in range(4):
    value = GetTM('TM.PAYLOAD.ENABLED', Wait=False, HandleError=False)
    if value:
        raise AssertionError('Fresh simulator unexpectedly enabled the payload')
    WaitFor(.1)
Display('EXPECTED_TIMEOUT: payload remained disabled after four samples')
assert GetTM('TM.POWER.BUS_VOLTAGE', Wait=False, HandleError=False) == 28.0
Display('SPELL_TIMEOUT_RECOVERY_PASS')
