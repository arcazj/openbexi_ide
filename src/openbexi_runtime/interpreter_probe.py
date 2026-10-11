"""Isolated interpreter and optional backend discovery (stdlib only)."""
from importlib import metadata
import json
import platform
import re
import sys


def describe():
    backends, errors = [], []
    seen = {'python'}
    for entry in metadata.entry_points(group='openbexi.backends.v1'):
        try:
            value = entry.load()()
            if not isinstance(value, dict) or value.get('api') != 1 or value.get('id') != entry.name:
                raise ValueError('Backend must describe API 1 and match its entry-point name')
            identifier = value['id']
            if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', identifier) or identifier in seen:
                raise ValueError('Duplicate or invalid backend identifier')
            if not isinstance(value.get('label'), str) or not 0 < len(value['label']) <= 80:
                raise ValueError('Backend label must contain 1 to 80 characters')
            for name in ('runner', 'debugAdapter'):
                if not isinstance(value.get(name), str) or not re.fullmatch(r'[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*', value[name]):
                    raise ValueError('Runner and debug adapter must be Python module names')
            grace = value.get('gracefulStopMilliseconds', 10000)
            if type(grace) is not int or not 100 <= grace <= 10000:
                raise ValueError('Graceful-stop timeout must be 100 to 10000 milliseconds')
            value['gracefulStopMilliseconds'] = grace
            json.dumps(value, allow_nan=False)
            seen.add(identifier)
            backends.append(value)
        except Exception as error:
            errors.append({'id': entry.name, 'error': str(error)})
    return {'version': list(sys.version_info[:3]), 'implementation': platform.python_implementation(),
        'executable': sys.executable, 'isolated': sys.flags.isolated, 'safe_path': sys.flags.safe_path,
        'debugpy': next((d.version for d in metadata.distributions()
                        if (d.metadata.get('Name') or '').lower() == 'debugpy'), None),
        'backends': backends, 'backendErrors': errors}


if __name__ == '__main__':
    print(json.dumps(describe(), allow_nan=False))
