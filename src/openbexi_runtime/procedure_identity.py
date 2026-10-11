"""Domain-neutral migration of the legacy procedure identity rules.

The legacy namespace is retained so captured catalog identities remain stable.
Source versions and execution contexts never change logical admission identity.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import tokenize
import uuid

LEGACY_NAMESPACE = uuid.UUID('d5e918ab-c027-5d31-94c0-cb9fb09c5743')


def canonical_definition_id(value):
    try:
        parsed = uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError('Procedure definition requires a canonical UUID') from error
    if str(parsed) != value or parsed.version not in {4, 5}:
        raise ValueError('Procedure definition requires a lowercase version 4 or 5 UUID')
    return value


def definition_id(catalog, source):
    if not isinstance(catalog, str) or not 1 <= len(catalog) <= 1024:
        raise ValueError('Invalid procedure catalog identity')
    markers = []
    if '@procedure-id' in source:
        try:
            for token in tokenize.generate_tokens(io.StringIO(source).readline):
                if token.type != tokenize.COMMENT or not re.match(r'#\s*@procedure-id\b', token.string):
                    continue
                match = re.fullmatch(r'#\s*@procedure-id\s+(\S+)\s*', token.string)
                if match is None or token.start[0] > 64:
                    raise ValueError('@procedure-id requires one UUID in the first 64 lines')
                markers.append(canonical_definition_id(match[1]))
        except (tokenize.TokenError, IndentationError) as error:
            raise ValueError('Procedure identity metadata cannot be tokenized') from error
    if len(markers) > 1:
        raise ValueError('Procedure has multiple @procedure-id declarations')
    return markers[0] if markers else str(uuid.uuid5(LEGACY_NAMESPACE, catalog.casefold()))


def version_id(definition, source_sha256, runtime, bundle_digest):
    canonical_definition_id(definition)
    if any(re.fullmatch('[0-9a-f]{64}', value or '') is None
           for value in (source_sha256, bundle_digest)):
        raise ValueError('Invalid captured source or dependency digest')
    raw = json.dumps({'schema': 'openbexi.procedure-version/1', 'definition': definition,
                      'source': source_sha256, 'runtime': runtime, 'bundle': bundle_digest},
                     sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()
