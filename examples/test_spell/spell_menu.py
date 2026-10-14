"""Interactive SPELL language explorer. Run with Python in the browser desktop.

Native SPELL uses its own Prompt service. The full reference catalogue is listed
separately from executable demonstrations: unavailable features never pass.
Option 13 runs every non-command demonstration; option 16 explicitly sends CMD1
to the local development DSS after confirmation. Results go to spell_menu_results.json.
"""
import importlib.util
import json
from pathlib import Path
import sys
import uuid

import spell

NATIVE = importlib.util.find_spec('spell.lib') is not None
if NATIVE:
    import spell.lib
    from spell.lang import functions as api
    from spell.lang import constants
    from spell.lib.adapter.utctime import TIME, NOW
else:
    from openbexi_spell_plugin.runtime import activate
    from spell import lang as api
    from spell import lang as constants
    from spell.lang import TIME, NOW
    activate()

PROFILE = 'original-native' if NATIVE else 'browser-sdk'
FAMILIES = ('PY', 'COMMON', 'TIME', 'DATA', 'FILES', 'FLOW', 'UI', 'OBS', 'CMD', 'LIMIT', 'SPECIAL')
CATALOG = json.loads(Path(__file__).with_name('feature_catalog.json').read_text(encoding='utf-8'))
RESULTS = []


def say(text, *, flush=False):
    # The original embedded interpreter routes Display to the procedure console;
    # Python's stdout is an ASCII process stream and is not forwarded reliably.
    if NATIVE:
        api.Display(text)
    else:
        print(text, flush=flush)


class Unavailable(Exception):
    pass


def ask(message):
    if NATIVE:
        return str(api.Prompt(message, Type=constants.ALPHA)).strip()
    return input(message + ' ').strip()


def need_native():
    if not NATIVE:
        raise Unavailable('Select an installed original native SPELL backend for this family.')


def demo(family):
    if family == 'PY':
        assert [x*x for x in range(4)] == [0, 1, 4, 9]
        assert sum(x for x in range(5)) == 10
        try:
            raise ValueError('handled example')
        except ValueError as error:
            assert str(error) == 'handled example'
    elif family == 'COMMON':
        assert int(constants.ABORT | constants.SKIP) & int(constants.ABORT)
        # The original language and bounded SDK have different constant values.
        assert int(constants.NOACTION) == (64 if NATIVE else 0)
        api.Display('Explicit constants, common modifiers and notification', Notify=True)
    elif family == 'TIME':
        now = TIME(TIME(NOW).value()) if NATIVE else TIME(NOW)
        duration = TIME(0.05)
        assert now.isAbs() and duration.isRel()
        assert abs(((now + duration) - now).rel() - 0.05) < 1e-6
        assert api.WaitFor(duration)
    elif family == 'DATA':
        need_native()
        from libSPELL_DTA_v3 import DataContainer, Var
        data = DataContainer('menu')
        data['counter'] = Var(Default=2, Range=[0, 10])
        data['counter'] = 7
        assert data['counter'] == 7
        key = 'menu_' + uuid.uuid4().hex
        try:
            api.SetSharedData(Name=key, Value=[True, 7, 'café'])
            assert api.GetSharedData(key) == [True, 7, 'café']
        finally:
            api.ClearSharedData(key)
    elif family == 'FILES':
        need_native()
        filename = 'spell-menu-' + uuid.uuid4().hex + '.txt'
        handle = None
        try:
            handle = api.OpenFile(filename, Mode=constants.WRITE, HandleError=False)
            assert api.WriteFile(handle, 'SPELL file round trip', HandleError=False)
            api.CloseFile(handle, HandleError=False)
            handle = None
            handle = api.OpenFile(filename, Mode=constants.READ, HandleError=False)
            assert api.ReadFile(handle, HandleError=False) == ['SPELL file round trip']
        finally:
            if handle is not None:
                api.CloseFile(handle, HandleError=False)
            if Path(filename).exists():
                api.DeleteFile(filename, HandleError=False)
    elif family == 'FLOW':
        need_native()
        from spell.runtime import Step
        Step('menu-flow', 'Native procedure step; child workflow is option 15')
    elif family == 'UI':
        api.Display('SPELL UI: text and Unicode café ✓')
        api.Display('Native Prompt is demonstrated by option 14; SDK menu input uses Python.')
    elif family == 'OBS':
        if NATIVE:
            raise Unavailable('This menu has no configured native DSS connection. Use the native driver qualification environment.')
        value = api.GetTM('TM1', Wait=False)
        api.Display('TM1 = ' + str(value))
        assert api.Verify('TM1', -1000000, Op='GT')
        assert api.Verify('TM1', 1000000, Op='LT')
    elif family == 'CMD':
        if NATIVE:
            raise Unavailable('Native command construction needs the configured native DSS catalogue.')
        command = api.BuildTC('CMD1')
        assert command.as_dict()['command_name'] == 'CMD1'
        api.Display('Built CMD1; nothing sent. Option 16 sends one simulator command.')
    elif family in ('LIMIT', 'SPECIAL'):
        raise Unavailable('Requires native DSS services beyond this desktop profile. Option 12 lists every reference feature and its native qualification status.')
    else:
        raise ValueError('Unknown family: ' + family)


def run_case(name, operation):
    row = {'feature': name, 'profile': PROFILE}
    try:
        operation()
        row['status'] = 'PASS'
    except Unavailable as error:
        row.update(status='UNAVAILABLE', reason=str(error))
    except Exception as error:
        row.update(status='FAIL', reason=type(error).__name__ + ': ' + str(error))
    RESULTS.append(row)
    say(row['status'] + ' ' + name + (': ' + row['reason'] if 'reason' in row else ''), flush=True)
    Path('spell_menu_results.json').write_text(json.dumps({
        'profile': PROFILE, 'scope': 'Selected demonstrations; not full language conformance',
        'results': RESULTS,
    }, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def catalogue(family='ALL'):
    rows = [row for row in CATALOG['rows'] if family == 'ALL' or row['package'] == family]
    if not rows:
        say('Unknown family. Choose ' + ', '.join(FAMILIES))
        return
    say('Historical native catalogue - these are NOT SDK or menu test results.')
    for row in rows:
        line = f"{row['package']:7} {row['native_status']:9} {row['name']} [{row['id']}]"
        say(line)
    say(f'{len(rows)} reference entries. Source commit: {CATALOG["source_commit"]}')


def native_procedure(name):
    need_native()
    assert api.StartProc(name, HandleError=False)


def send_simulator_command():
    if NATIVE:
        raise Unavailable('This command demonstration is for the local browser DSS simulator.')
    if ask('Send one CMD1 to the local simulator? Type SEND CMD1 to confirm:') != 'SEND CMD1':
        raise Unavailable('Command cancelled; nothing sent.')
    assert api.Send(api.BuildTC('CMD1'))


def main():
    say('SPELL language menu - profile: ' + PROFILE, flush=True)
    say('763 reference entries across 11 families. PASS applies only to the selected demonstration.')
    if '--all' in sys.argv[1:]:
        for family in FAMILIES:
            run_case(family, lambda family=family: demo(family))
    else:
        while True:
            for index, family in enumerate(FAMILIES, 1):
                say(f'{index:2}. {family} demonstration')
            say('12. Reference catalogue\n13. Run all non-command demonstrations\n'
                  '14. Native successive prompts\n15. Native parent/child workflow\n'
                  '16. Send one local simulator command (confirmation required)\n0. Exit', flush=True)
            try:
                choice = ask('Choose 0-16:')
            except EOFError:
                break
            if choice == '0':
                break
            if choice.isdigit() and 1 <= int(choice) <= len(FAMILIES):
                family = FAMILIES[int(choice)-1]
                run_case(family, lambda: demo(family))
            elif choice == '12':
                catalogue(ask('Family name or ALL:').upper())
            elif choice == '13':
                for family in FAMILIES:
                    run_case(family, lambda family=family: demo(family))
            elif choice in ('14', '15'):
                name = 'spell_native_prompt' if choice == '14' else 'spell_native_parent'
                run_case(name, lambda: native_procedure(name))
            elif choice == '16':
                run_case('Send CMD1', send_simulator_command)
            else:
                say('Invalid choice; enter a number from 0 to 16.', flush=True)
    failed = sum(row['status'] == 'FAIL' for row in RESULTS)
    say(f'SPELL_MENU_COMPLETE checks={len(RESULTS)} failures={failed}', flush=True)
    return int(bool(failed))


if __name__ == '__main__':
    if main():
        raise RuntimeError('One or more selected SPELL demonstrations failed; see spell_menu_results.json')
