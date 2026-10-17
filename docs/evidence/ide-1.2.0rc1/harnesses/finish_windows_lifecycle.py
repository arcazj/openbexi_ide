"""Resume against the real 1.0 -> initial RC installation, preserving failed evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

work = Path(__file__).resolve().parent
root = work.parents[1]
installation = (work/'windows-lifecycle/installation with spaces').resolve(strict=True)
assert installation.is_relative_to(work)
state_file = installation/'.openbexi-install.json'
state = json.loads(state_file.read_text(encoding='utf-8-sig'))
assert state['product'] == 'OpenBEXI IDE'
original = work/'source-final/scripts/distribution_qualify.py'
source = original.read_text(encoding='utf-8')
replacements = {
    'ROOT = Path(__file__).resolve().parents[1]': 'ROOT = Path('+repr(str(work/'source-final'))+')',
    "installation = evidence / 'installation with spaces'": 'installation = Path('+repr(str(installation))+')',
}
for before, after in replacements.items():
    assert source.count(before) == 1
    source = source.replace(before, after)
adapted = work/'distribution_qualify_resume.py'
adapted.write_text(source, encoding='utf-8', newline='\n')
output = work/'windows-lifecycle-final'
provenance = {'original_harness_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),
              'adapted_harness_sha256':hashlib.sha256(adapted.read_bytes()).hexdigest(),
              'adaptation':'Only source-root and existing owned installation paths; all lifecycle assertions retained.',
              'preexisting_state':state,
              'initial_upgrade_report_sha256':hashlib.sha256((work/'windows-lifecycle/result.json').read_bytes()).hexdigest()}
(work/'windows-resume-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
result = subprocess.run([sys.executable, str(adapted), '--bundle', str(work/'windows-final/bundle'),
                        '--output', str(output), '--shared-debug', '--console-menu'])
raise SystemExit(result.returncode)
