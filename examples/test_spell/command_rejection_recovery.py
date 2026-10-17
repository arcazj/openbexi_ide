"""Reject an unknown command, catch its real driver exception, then recover."""
from spell.lang.functions import BuildTC, Display, GetTM, Send
from spell.lib.exception import DriverException
try:
    BuildTC('NO_SUCH_COMMAND', HandleError=False, PromptUser=False)
except DriverException:
    Display('EXPECTED_REJECTION: unknown command')
else:
    raise AssertionError('Unknown command was accepted')
assert Send(command='CMD1', HandleError=False, Confirm=False, PromptUser=False)
assert GetTM('TM.PAYLOAD.ENABLED', Wait=False, HandleError=False) is True
assert Send(command='CMD2', HandleError=False, Confirm=False, PromptUser=False)
Display('SPELL_COMMAND_REJECTION_RECOVERY_PASS')
