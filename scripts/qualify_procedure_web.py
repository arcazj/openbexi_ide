"""Real browser controls and a native SPELL executor, with a second monitor."""
import argparse
import json
from importlib.metadata import version
from pathlib import Path
import sys
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tools', type=Path, required=True)
    parser.add_argument('--browser', type=Path, default=Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(args.tools))
    from playwright.sync_api import sync_playwright, expect
    expect.set_options(timeout=120000)
    from openbexi_runtime.procedure_client import ensure_service, Client
    project = args.output / 'project'; project.mkdir()
    (project / 'procedure.py').write_text(
        "from spell.lang.functions import Notify, Prompt, Display\n"
        "from spell.lang.constants import YES_NO\n"
        "Notify('Voltage', '28.0', 'SUCCESS')\n"
        "assert Prompt('Ready from the browser?', Type=YES_NO, HandleError=False) is True\n"
        "Display('BROWSER_NATIVE_PASS')\n", encoding='utf-8')
    endpoint = ensure_service(project); config = json.loads(endpoint.read_text(encoding='utf-8'))
    report = {'passed': False, 'version': version('openbexi-ide'), 'checks': []}; errors = []
    with sync_playwright() as automation:
        browser = automation.chromium.launch(executable_path=str(args.browser), headless=True)
        operator = browser.new_page(viewport={'width': 1660, 'height': 1000})
        monitor = browser.new_page(viewport={'width': 1660, 'height': 1000})
        for page in (operator, monitor):
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.set_default_timeout(120000)
        try:
            for page, role in ((operator, 'operator'), (monitor, 'monitor')):
                page.goto(config['url']); page.locator('[name=name]').fill(role.title())
                page.locator('[name=key]').fill(config[role]); page.locator('#login button').click()
                expect(page.locator('#connection')).to_have_text('Connected')
            expect(monitor.locator('#run')).to_be_disabled()
            operator.locator('#files').select_option('procedure.py')
            operator.locator('#run').click()
            expect(operator.locator('#question')).to_have_text('Ready from the browser?')
            expect(monitor.locator('#question')).to_have_text('Ready from the browser?')
            expect(operator.locator('#role')).to_have_text('CTRL')
            expect(monitor.locator('#role')).to_have_text('MON')
            expect(monitor.locator('#commit')).to_be_disabled()
            expect(monitor.locator('#answers input').first).to_be_disabled()
            colors = operator.locator('#code tbody').evaluate("node => ({current: node.querySelector('[data-line=\"4\"]').style.backgroundColor, success: node.querySelector('[data-line=\"3\"]').lastChild.style.backgroundColor})")
            assert colors == {'current': 'rgb(0, 0, 255)', 'success': 'rgb(0, 255, 0)'}, colors
            operator.screenshot(path=str(args.output / 'controller-prompt.png'), full_page=True)
            monitor.screenshot(path=str(args.output / 'monitor-prompt.png'), full_page=True)
            operator.locator('#answers input[value="0"]').check(); operator.locator('#reset').click()
            expect(operator.locator('#answers input[value="0"]')).not_to_be_checked()
            operator.locator('#answers input[value="0"]').check(); operator.locator('#commit').click()
            expect(operator.locator('#state')).to_have_text('FINISHED')
            expect(monitor.locator('#state')).to_have_text('FINISHED')
            expect(operator.locator('#output')).to_contain_text('BROWSER_NATIVE_PASS')
            operator.screenshot(path=str(args.output / 'finished.png'), full_page=True)
            report['checks'] += ['Native browser Run, prompt Reset/Commit, successful completion',
                'Second browser monitors the same execution and cannot answer or run',
                'Manual current-line and SUCCESS colors']
            # Refreshing a browser preserves the service record and snapshot.
            monitor.reload(); monitor.locator('[name=key]').fill(config['monitor']); monitor.locator('#login button').click()
            expect(monitor.locator('#state')).to_have_text('FINISHED')
            expect(monitor.locator('#code')).to_contain_text('Ready from the browser?')
            report['checks'].append('Reconnect restores completed record and source snapshot')
            operator.locator('#code tbody tr[data-line="3"]').dblclick()
            expect(operator.locator('#information-table')).to_contain_text('Voltage')
            expect(operator.locator('#information-table')).to_contain_text('28.0')
            operator.locator('#information-mode').select_option('History')
            expect(operator.locator('#information-table')).to_contain_text('SUCCESS')
            operator.locator('#information-mode').select_option('Full')
            expect(operator.locator('#information-raw')).to_contain_text('ItemName')
            operator.locator('#information-close').click()
            report['checks'].append('Persisted item dialog Latest/History/Full and native notification fields')
            # Exercise the portable download path used when the File System
            # Access API is unavailable; this keeps the exported content real.
            operator.evaluate('window.showSaveFilePicker = undefined')
            with operator.expect_download() as pending:
                operator.locator('#export').click()
            target = args.output / 'as-run.jsonl'; pending.value.save_as(target)
            entries = [json.loads(line) for line in target.read_text(encoding='utf-8').splitlines()]
            assert entries[0]['schema'] == 'openbexi.as-run/1'
            assert entries[0]['snapshot']['status'] == 'FINISHED'
            assert any(entry.get('event', {}).get('item') == 'Voltage' for entry in entries[1:])
            report['checks'].append('As-Run download contains captured source and complete persisted notifications')
            assert not errors, errors
            report['passed'] = True
            report['browser'] = browser.version
        except Exception:
            report['error'] = traceback.format_exc()
            operator.screenshot(path=str(args.output / 'failure.png'), full_page=True)
            try:
                abort = operator.locator('[data-command=disconnect]')
                if abort.is_enabled():
                    abort.click(); expect(operator.locator('#state')).to_have_text('ABORTED', timeout=60000)
            except Exception:
                pass
        finally:
            report['page_errors'] = errors
            (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
            browser.close()
    print(json.dumps(report)); return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
