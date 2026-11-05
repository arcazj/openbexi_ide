"""Provision the identical frozen native input for a recorded comparison."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd() / 'scripts'))
import qualify_v08_memory_comparison as comparison
original_run_child = comparison.run_child
def provisioned_child(command, cwd, log, timeout):
    if len(command) != 3 or Path(command[1]).name != 'qualify_v08_native_launch.py':
        raise ValueError('Unexpected comparison child')
    return original_run_child([command[0], '/tmp/capture-native-start.py', command[2]], cwd, log, timeout)
comparison.run_child = provisioned_child
raise SystemExit(comparison.main())
