"""Read-only installation diagnostics without importing optional plugin code."""
from importlib import metadata
import platform
import re
import sys


LOCKED_DESKTOP = {'PySide6-Essentials': '6.10.3', 'shiboken6': '6.10.3',
                  'debugpy': '1.8.22', 'Pygments': '2.21.0'}


def package_version(name):
    try:
        value = metadata.version(name)
    except metadata.PackageNotFoundError:
        return None
    # Untrusted wheel metadata must not inject arbitrary text into the report.
    return value if re.fullmatch(r'[0-9A-Za-z.!+_-]{1,80}', value) else 'invalid-metadata'


def report(*, desktop=False):
    from .plugin_inventory import inventory
    dependencies = {name: {'installed': package_version(name), 'required': required}
                    for name, required in LOCKED_DESKTOP.items()}
    interpreter_ok = platform.python_implementation() == 'CPython' and sys.version_info[:2] == (3, 13)
    desktop_ok = all(item['installed'] == item['required'] for item in dependencies.values())
    plugins = []
    for package in inventory():
        plugins.append({'name': package['name'], 'version': package_version(package['name']),
                        'backends': sorted({item['id'] for item in package['backends']
                            if re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', item['id'])})})
    return {'schema': 1, 'product': 'OpenBEXI IDE', 'version': package_version('openbexi-ide'),
            'python': {'implementation': platform.python_implementation(),
                       'version': platform.python_version(), 'isolated': bool(sys.flags.isolated),
                       'supported': interpreter_ok},
            'platform': {'system': platform.system(), 'architecture': platform.machine()},
            'desktop_requested': desktop, 'desktop_dependencies': dependencies,
            'optional_plugins': plugins,
            'ready': interpreter_ok and (not desktop or desktop_ok),
            'scope': 'Installation inventory only; no project, credentials, environment or runtime effects inspected'}
