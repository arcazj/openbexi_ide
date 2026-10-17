"""Read raw/engineering values and qualified extended telemetry."""
from spell.lang.functions import Display, GetTM
from spell.lang.constants import RAW
raw = GetTM('TM.POWER.BUS_VOLTAGE', ValueFormat=RAW, Wait=False, HandleError=False)
eng = GetTM('TM.POWER.BUS_VOLTAGE', Wait=False, HandleError=False)
item = GetTM('TM.POWER.BUS_VOLTAGE', Extended=True, Wait=False, HandleError=False)
assert raw == 28000 and eng == 28.0 and item.status()
assert item.raw() == raw and item.eng() == eng
Display('SPELL_RAW_ENGINEERING_PASS raw=%s engineering=%s' % (raw, eng))
