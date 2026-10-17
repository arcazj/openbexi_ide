"""Assemble the native learning desktop offline from explicit installed images."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]


def image_id(reference):
    return subprocess.check_output(['docker','image','inspect',reference,'--format','{{.Id}}'],text=True).strip()


def inventory(root, entries):
    result = {}
    for entry in entries:
        path = root/entry
        for item in sorted(path.rglob('*')) if path.is_dir() else [path]:
            if item.is_file() and '__pycache__' not in item.parts and item.suffix != '.pyc':
                result[item.relative_to(root).as_posix()] = hashlib.sha256(item.read_bytes()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin-root',type=Path,required=True)
    parser.add_argument('--native-image',required=True)
    parser.add_argument('--desktop-image',required=True)
    parser.add_argument('--tag',default='openbexi-ide:1.1.0-learning')
    args = parser.parse_args()
    plugin = args.plugin_root.resolve(strict=True)
    assert (plugin/'host_runtime/python/native.py').is_file()
    output = ROOT/'.qualification/learning-build'/uuid.uuid4().hex
    output.mkdir(parents=True)
    report = {'passed':False,'tag':args.tag,'inputs':{}}
    try:
        for name, reference in (('native',args.native_image),('desktop',args.desktop_image)):
            identity = image_id(reference)
            tag = 'openbexi-learning-'+name+'-input:'+identity.removeprefix('sha256:')
            subprocess.run(['docker','tag',identity,tag],check=True)
            report['inputs'][name] = {'image':identity,'tag':tag}
        report['ide_sources'] = inventory(ROOT,['pyproject.toml','README.md','LICENSE','NOTICE','src','examples','docker','tests'])
        report['host_sources'] = inventory(plugin,['host_plugin','host_runtime/python','src/dss'])
        command = ['docker','build','--network=none','--progress=plain','-f','docker/native-desktop.Dockerfile',
                   '--build-context','spell_plugin='+str(plugin),
                   '--build-arg','NATIVE_IMAGE='+report['inputs']['native']['tag'],
                   '--build-arg','DESKTOP_IMAGE='+report['inputs']['desktop']['tag'],
                   '-t',args.tag,str(ROOT)]
        with (output/'build.log').open('wb') as log:
            subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        report['image'] = image_id(args.tag)
        report['passed'] = True
    finally:
        (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'passed':report['passed'],'output':str(output),'image':report.get('image')}),flush=True)


if __name__ == '__main__':
    main()
