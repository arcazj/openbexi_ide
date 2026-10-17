import json
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[2]
work = Path(__file__).resolve().parent
context = work / 'docker-context'
context.mkdir(exist_ok=False)
wheel = root / 'dist/1.2.0rc1/openbexi_ide-1.2.0rc1-py3-none-any.whl'
shutil.copyfile(wheel, context / wheel.name)
for name in ('README.md', 'pyproject.toml'):
    shutil.copyfile(work / 'source' / name, context / name)
for name in ('qualify_procedure_workspace.py', 'distribution_desktop.py', 'distribution_shared_debug.py'):
    shutil.copyfile(work / 'source/scripts' / name, context / name)
base = 'sha256:6c71e0e74b1be154cadded7877a5181272f06190e559d5a5d194a596869d9ddd'
alias = 'openbexi-ide:1.2.0rc1-build-input'
subprocess.run(['docker', 'tag', base, alias], check=True)
dockerfile = f'''FROM {alias}
USER root
COPY {wheel.name} /opt/wheels/{wheel.name}
RUN rm /opt/wheels/openbexi_ide-1.2.0.dev1-py3-none-any.whl && python -m pip install --no-index --no-deps --force-reinstall /opt/wheels/{wheel.name}
COPY pyproject.toml README.md /opt/openbexi/
COPY qualify_procedure_workspace.py distribution_desktop.py distribution_shared_debug.py /opt/rc1-checks/
LABEL org.opencontainers.image.version="1.2.0rc1" org.opencontainers.image.source="https://github.com/arcazj/openbexi_ide"
USER 10003:10003
'''
(context / 'Dockerfile').write_text(dockerfile, encoding='utf-8', newline='\n')
(work / 'docker-input.json').write_text(json.dumps({'base_image': base, 'base_alias': alias, 'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()}, indent=2)+'\n')
print(context)
