"""Poll changing spacecraft time using a bounded for-loop; native SPELL + DSS."""
from spell.lang.functions import Display, GetTM, WaitFor
first = GetTM('TM.CORE.TICK', Wait=False, HandleError=False)
Display('Initial simulator tick: ' + str(first))
for sample in range(12):
    WaitFor(.5)
    current = GetTM('TM.CORE.TICK', Wait=False, HandleError=False)
    Display('Sample %d: %s' % (sample + 1, current))
    if current != first:
        break
else:
    raise AssertionError('No simulator tick change within six seconds')
Display('SPELL_TELEMETRY_FOR_LOOP_PASS')
