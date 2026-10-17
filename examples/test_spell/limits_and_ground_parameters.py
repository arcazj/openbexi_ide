"""Inject a ground parameter, configure alarm limits, then restore them."""
from spell.lang.functions import Display, GetLimits, GetTM, IsAlarmed, RestoreNormalLimits, SetGroundParameter, SetLimits
from spell.lang.modifiers import LoRed, LoYel, HiYel, HiRed
assert RestoreNormalLimits(HandleError=False)
try:
    assert SetGroundParameter('TMparam', 25.0, HandleError=False)
    assert SetLimits('TMparam', Definition={LoRed:10.0, LoYel:20.0, HiYel:30.0, HiRed:40.0}, HandleError=False)
    assert GetTM('TMparam', Wait=False, HandleError=False) == 25.0
    assert not IsAlarmed('TMparam', HandleError=False)
    assert SetGroundParameter('TMparam', 45.0, HandleError=False)
    assert IsAlarmed('TMparam', HandleError=False)
    Display(str(GetLimits('TMparam', HandleError=False)))
finally:
    assert RestoreNormalLimits(HandleError=False)
Display('SPELL_LIMITS_PASS')
