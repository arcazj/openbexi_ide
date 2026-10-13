"""Installed runtime plugin package inventory in the selected interpreter."""
from importlib import metadata
import json
import re
import sys

GROUPS = ('openbexi.backends.v1', 'openbexi.shared_backends.v1')
PROTECTED = {'openbexi-ide', 'pip', 'setuptools', 'wheel', 'debugpy',
             'pyside6', 'pyside6-essentials', 'pyside6-addons', 'shiboken6'}


def normalized(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def inventory():
    packages = {}
    for group in GROUPS:
        for entry in metadata.entry_points(group=group):
            distribution = entry.dist
            if distribution is None:
                continue
            name = distribution.metadata.get('Name', '')
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
                continue
            key = normalized(name)
            row = packages.setdefault(key, dict(name=name, version=distribution.version,
                removable=key not in PROTECTED, backends=[]))
            row['backends'].append(dict(id=entry.name, group=group, target=entry.value))
    return sorted(packages.values(), key=lambda row: normalized(row['name']))


if __name__ == '__main__':
    if sys.version_info[:2] != (3, 13) or not sys.flags.isolated:
        raise RuntimeError('Runtime plugin discovery requires isolated CPython 3.13')
    print(json.dumps(inventory()))
