"""Read telemetry and prove that the driver rejects commanding in Monitoring.

Run with one JSON argument: {"LAB_MODE": "Monitoring"}.
The teaching procedure runs locally; the real DSS dispatcher enforces read-only
driver authority. This is separate from an operational shared Monitoring session.
"""
from spell.runtime import ARGS
from spell.lang.functions import Display, GetTM, Send
from spell.lib.exception import DriverException

assert ARGS['LAB_MODE'] == 'Monitoring', 'Set the JSON procedure argument to Monitoring first'
before = GetTM('TM.PAYLOAD.ENABLED', Wait=False, HandleError=False)
try:
    Send(command='CMD1', HandleError=False, PromptUser=False, Confirm=False)
except DriverException:
    Display('EXPECTED_DENIAL: Monitoring driver rejected command')
else:
    raise AssertionError('Monitoring unexpectedly allowed commanding')
assert GetTM('TM.PAYLOAD.ENABLED', Wait=False, HandleError=False) == before
Display('SPELL_MONITORING_GUARD_PASS')
