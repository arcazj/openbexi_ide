"""Original native SPELL: relative time, absolute time and a short timed wait."""
import spell.lib
from spell.lib.adapter.utctime import TIME, NOW
from spell.lang.functions import Display, WaitFor
from spell.runtime import Step

Step('clock', 'Capture a UTC instant and calculate a duration')
start = TIME(TIME(NOW).value())
duration = TIME(0.1)
assert start.isAbs() and duration.isRel()
assert abs(((start + duration) - start).rel() - 0.1) < 1e-6
Step('wait', 'Wait for one tenth of a second')
assert WaitFor(duration)
Display('SPELL_TIME_PASS')
