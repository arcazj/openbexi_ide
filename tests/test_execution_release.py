"""Fail-closed release parsing without requiring a Docker daemon."""
import copy
import json

import pytest

from openbexi_runtime.execution_release import digest, read_manifest, validate
from openbexi_runtime.procedure_identity import version_id


def manifest():
    definition = '184ad12b-8ad4-435d-96b3-b2de45e4abb1'
    image = 'sha256:' + 'a'*64
    source = {'schema': 'openbexi.source-capture/1', 'git_commit': 'b'*40,
              'git_tree': 'c'*40, 'files': {'main.py': {'sha256': 'd'*64, 'git_blob': 'e'*40, 'mode': '100644'}}}
    return {'schema': 'openbexi.execution-release/1', 'profile': 'python-docker-offline/1',
            'image': image, 'base_image': 'sha256:' + 'f'*64, 'source': source,
            'source_digest': digest(source), 'runtime': {'implementation': 'CPython', 'version': [3, 13, 15]},
            'procedures': {'main.py': {'definition': definition,
                                      'version': version_id(definition, 'd'*64, image, digest(source))}}}


def test_manifest_rejects_mutable_runtime_and_malformed_source(tmp_path):
    original = manifest()
    assert validate(original) == original
    for key, value in [('image', 'runtime:latest'), ('profile', 'Development'), ('runtime', []),
                       ('procedures', {}), ('source_digest', '0'*64)]:
        malformed = copy.deepcopy(original)
        malformed[key] = value
        with pytest.raises(ValueError):
            validate(malformed)
    for name in ('../main.py', '/main.py', 'a//main.py', 'C:main.py'):
        malformed = copy.deepcopy(original)
        malformed['source']['files'][name] = malformed['source']['files'].pop('main.py')
        malformed['source_digest'] = digest(malformed['source'])
        with pytest.raises(ValueError):
            validate(malformed)
    path = tmp_path / 'release.json'
    path.write_text('{"schema":"one","schema":"two"}')
    with pytest.raises(ValueError, match='Duplicate'):
        read_manifest(path)
    path.write_text(json.dumps(original))
    assert read_manifest(path) == original
