"""Command the payload ON and observe several changing temperature samples.

Native SPELL + fresh synthetic DSS. Expected: rising temperature after CMD1,
then CMD2 disables the payload. The bounded for-loop retains intermediate values.
"""
from spell.lang.functions import Display, GetTM, Send, WaitFor

initial = GetTM('TM.PAYLOAD.TEMPERATURE', Wait=False, HandleError=False)
samples = [initial]
assert Send(command='CMD1', HandleError=False, PromptUser=False, Confirm=False)
try:
    for attempt in range(20):
        WaitFor(.5)
        temperature = GetTM('TM.PAYLOAD.TEMPERATURE', Wait=False, HandleError=False)
        Display('After commanding: sample=%d temperature=%s' % (attempt+1, temperature))
        if temperature != samples[-1]:
            samples.append(temperature)
        if len(samples) >= 4:
            break
    else:
        raise AssertionError('Temperature did not produce three changes within ten seconds')
    assert all(later > earlier for earlier, later in zip(samples, samples[1:])), samples
finally:
    assert Send(command='CMD2', HandleError=False, PromptUser=False, Confirm=False)
assert GetTM('TM.PAYLOAD.ENABLED', Wait=False, HandleError=False) is False
Display('SPELL_TEMPERATURE_RAMP_PASS samples=' + repr(samples))
