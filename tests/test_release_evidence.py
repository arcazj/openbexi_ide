import hashlib
import json
from pathlib import Path
import runpy

import pytest


CHECKER = runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/check_release.py'))


def dossier(root):
    report = root/'report.json'
    report.write_text(json.dumps({'passed':True, 'version':'1.0.0'}))
    reference = {'path':'report.json', 'sha256':hashlib.sha256(report.read_bytes()).hexdigest()}
    return {'schema':1, 'product':'openbexi_ide', 'version':'1.0.0',
            'artifacts':{name:reference for name in CHECKER['ARTIFACTS']},
            'gates':{name:{'status':'passed', 'format':'json', 'report':reference} for name in CHECKER['GATES']}}


def test_missing_failed_and_tampered_release_evidence_stays_open(tmp_path):
    manifest = dossier(tmp_path)
    assert CHECKER['verify'](tmp_path, manifest)['release_accepted']
    manifest['gates']['browser_interaction']['status'] = 'pending'
    assert not CHECKER['verify'](tmp_path, manifest)['release_accepted']
    manifest['gates']['browser_interaction']['status'] = 'passed'
    (tmp_path/'report.json').write_text('{}')
    result = CHECKER['verify'](tmp_path, manifest)
    assert not result['release_accepted'] and len(result['open_gates']) == 9


def test_external_evidence_and_wrong_release_are_rejected(tmp_path):
    root = tmp_path/'evidence'
    root.mkdir()
    manifest = dossier(root)
    manifest['version'] = '1.0.1'
    assert not CHECKER['verify'](root, manifest)['release_accepted']
    external = tmp_path/'outside'
    external.write_text('unrelated file')
    with pytest.raises(ValueError, match='inside'):
        CHECKER['checked_reference'](root, {'path':'../outside', 'sha256':'unused'})
