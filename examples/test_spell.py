"""SPELL smoke procedure for the browser SDK or original native backend.

The console names the runtime profile. Native mode additionally checks original
DataContainer, procedure variables, shared data and Step. No commands are sent.
"""
import importlib.util
import json
from pathlib import Path

try:
    import spell
except ModuleNotFoundError as error:
    raise RuntimeError('Install a SPELL plugin in the selected interpreter, or run '
                       'this example in the supplied browser desktop.') from error

native = importlib.util.find_spec('spell.lib') is not None
if not native:
    from openbexi_spell_plugin.runtime import activate
    from spell.lang import Display, TIME, NOW, WaitFor

    activate()
    Display('SPELL profile: browser development SDK')
    instant = TIME(NOW)
    duration = TIME(1.25)
    assert instant.isAbs() and duration.isRel()
    assert abs(((instant + duration) - instant).rel() - 1.25) < 1e-6
    assert WaitFor(0.05)
    Path('test_spell_result.json').write_text(json.dumps({
        'profile': 'browser-sdk', 'answer': 42, 'native_data': False,
        'checks': ['Display', 'absolute and relative TIME', 'WaitFor'],
    }, indent=2) + '\n', encoding='utf-8')
    Display('SPELL_EXAMPLE_PASS profile=browser-sdk answer=42')
    Display('Select the native SPELL backend for DataContainer, Step and shared-data checks.')
else:
    import spell.lib
    from spell.lib.adapter.utctime import TIME, NOW
    from spell.lang.functions import (
        ClearSharedData, Display, GetSharedData, GetSharedDataKeys, SetSharedData,
    )
    from spell.runtime import ARGS, IVARS, Step
    from libSPELL_DTA_v3 import DataContainer, Var

    Display('SPELL profile: original native runtime')
    Step('library', 'Inspect the configured original SPELL library')
    Display('Original SPELL library: ' + str(spell.lib.__file__))
    assert isinstance(ARGS, DataContainer) and isinstance(IVARS, DataContainer)

    Step('data', 'Exercise native typed data and procedure variables')
    sample = DataContainer('example')
    sample['counter'] = Var(Default=5, Range=[0, 10])
    sample['counter'] = 7
    assert sample['counter'] == 7
    IVARS['example_answer'] = sample['counter'] * 6
    assert IVARS['example_answer'] == 42

    Step('time', 'Check absolute and relative SPELL time')
    instant = TIME(TIME(NOW).value())  # Snapshot NOW before comparing two instants.
    duration = TIME(1.25)
    assert instant.isAbs() and duration.isRel()
    assert abs(duration.rel() - 1.25) < 1e-9
    assert abs(((instant + duration) - instant).rel() - 1.25) < 1e-6
    Display('Time arithmetic passed: ' + str(instant))

    Step('shared', 'Round-trip owned shared data and clean it up')
    # A fresh key avoids overwriting another procedure's shared data.
    import uuid
    key = 'example_' + uuid.uuid4().hex
    try:
        SetSharedData(Name=key, Value=[True, 42, 'café'])
        assert key in GetSharedDataKeys()
        assert GetSharedData(key) == [True, 42, 'café']
    finally:
        ClearSharedData(key)
    assert key not in GetSharedDataKeys()

    Step('result', 'Export a result for the IDE run artifacts')
    Path('test_spell_result.json').write_text(json.dumps({
        'answer': IVARS['example_answer'], 'native_data': True, 'shared_data_cleaned': True,
        'original_library': str(spell.lib.__file__),
    }, indent=2) + '\n', encoding='utf-8')
    Display('SPELL_EXAMPLE_PASS answer=42 native_data=True shared_data_cleaned=True')
