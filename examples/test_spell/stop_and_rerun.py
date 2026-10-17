"""Press Stop during this bounded loop, then Run again; each run starts fresh."""
from spell.lang.functions import Display, GetTM, WaitFor
for sample in range(60):
    Display('STOP_DEMO sample=%d voltage=%s' % (sample, GetTM('TM.POWER.BUS_VOLTAGE', Wait=False, HandleError=False)))
    WaitFor(.5)
Display('SPELL_STOP_DEMO_COMPLETED')
