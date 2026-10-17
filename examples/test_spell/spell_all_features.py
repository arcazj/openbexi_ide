"""Run demonstrations for all 11 SPELL families with the native DSS backend.

This is a teaching tour. feature_catalog.json separately maps all 763 qualified
language requirements to the published native v0.5 evidence.
"""
from pathlib import Path
import runpy
from spell.lang.functions import Display

menu = runpy.run_path(str(Path(__file__).with_name('spell_menu.py')))
for family in menu['FAMILIES']:
    Display('Family: ' + family)
    menu['run_case'](family, lambda family=family: menu['demo'](family))
assert len(menu['RESULTS']) == 11
assert all(row['status'] == 'PASS' for row in menu['RESULTS']), menu['RESULTS']
Display('SPELL_ALL_FAMILIES_PASS families=11')
