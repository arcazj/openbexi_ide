"""Native SPELL: command the synthetic payload, then wait for real telemetry.

Select SPELL in the learning desktop. The private DSS starts with payload off.
Expected: OFF -> ON -> OFF, then SPELL_COMMAND_TELEMETRY_PASS.
"""
from spell.lang.functions import BuildTC, Display, GetTM, Send, WaitFor
from spell.lang.constants import ABORT
from spell.runtime import Step

CONFIG = dict(PromptUser=False, PromptFailure=True, HandleError=False, OnFailure=ABORT)


def wait_for_payload(expected):
    # A bounded for-loop makes intermediate samples visible in Run and Debug.
    for attempt in range(20):
        enabled = GetTM('TM.PAYLOAD.ENABLED', Wait=False, **CONFIG)
        Display('Sample %d: payload enabled=%s, expected=%s' % (attempt + 1, enabled, expected))
        if enabled == expected:
            return
        WaitFor(.25)
    raise AssertionError('Payload telemetry did not reach the commanded state within 5 seconds')


Step('initial', 'Confirm the synthetic payload is disabled')
wait_for_payload(False)
Step('enable', 'Send CMD1 and wait for payload telemetry to become enabled')
assert Send(command=BuildTC('CMD1', config=CONFIG), config=CONFIG)
wait_for_payload(True)
Step('disable', 'Send CMD2 and confirm payload telemetry returns to disabled')
assert Send(command='CMD2', config=CONFIG)
wait_for_payload(False)
Display('SPELL_COMMAND_TELEMETRY_PASS')
