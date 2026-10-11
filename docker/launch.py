"""Convenience commands in the container; starts the real installed desktop."""
import argparse
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('view', choices=('local', 'alice', 'bob', 'monitor', 'durable', 'durable-monitor', 'terminal'))
    args = parser.parse_args()
    if args.view == 'terminal':
        os.execvp('xterm', ['xterm', '-title', 'OpenBEXI test terminal', '-fa', 'DejaVu Sans Mono', '-fs', '11'])
    durable = args.view.startswith('durable')
    project = Path('/workspace/projects') / ('durable' if durable else 'demo')
    command = [sys.executable, '-I', '-m', 'openbexi_ide', '--project', str(project),
               '--file', str(project / 'hello.py')]
    if args.view != 'local':
        info = ('durable-monitor.json' if args.view == 'durable-monitor' else 'durable-alice.json') if durable else 'shared-server.json'
        role = 'monitor' if args.view in {'monitor', 'durable-monitor'} else 'developer'
        command += ['--session-info', '/workspace/connections/' + info, '--role', role, '--user', args.view.title()]
    # Separate preferences avoid sharing the selected project across concurrent windows.
    os.environ['XDG_CONFIG_HOME'] = str(Path('/home/tester/.config') / args.view)
    os.execv(sys.executable, command)


if __name__ == '__main__':
    main()
