"""Send a typed command argument and verify the resulting engineering telemetry."""
from spell.lang.functions import Display, Send, Verify
from spell.lang.constants import eq, NOACTION
assert Send(command='CMDNAME', args=[['ARG1', 2.5]], HandleError=False, Confirm=False, PromptUser=False)
assert Verify('TM.PAYLOAD.SETPOINT', eq, 2.5, Wait=False, Retries=0, HandleError=False, PromptUser=False, OnFalse=NOACTION)
Display('SPELL_COMMAND_SETPOINT_PASS')
