"""Send an ordered command group and check its final effect."""
from spell.lang.functions import Display, GetTM, Send
assert Send(group=['CMD1', 'CMD2', 'CMD3'], HandleError=False, Confirm=False, PromptUser=False)
assert GetTM('TM.PAYLOAD.ENABLED', Wait=False, HandleError=False) is False
Display('SPELL_COMMAND_GROUP_PASS')
