"""Enable/disable the synthetic ranging service and inspect its catalogue."""
from spell.lang.functions import Display, DisableRanging, EnableRanging, GetAntennaNames, GetBasebandNames
config = dict(HandleError=False, PromptUser=False)
assert DisableRanging(**config)
assert EnableRanging(**config)
Display('Antennas: ' + str(GetAntennaNames(**config)))
Display('Basebands: ' + str(GetBasebandNames(**config)))
assert DisableRanging(**config)
Display('SPELL_RANGING_PASS')
