"""Read the retained archives independently and exercise real ENOSPC on a private disposable volume."""

import argparse
import json
from pathlib import Path
import runpy

setup=runpy.run_path(str(Path(__file__).with_name("compose_fixture.py")))
Fixture,docker,FINAL=setup["Fixture"],setup["docker"],setup["FINAL"]

CHECK="""
import hashlib,json,sqlite3,sys
from pathlib import Path
r=Path('/archive')/sys.argv[1]
m=(r/'manifest.json').read_bytes()
assert hashlib.sha256(m).hexdigest()==sys.argv[2]
manifest=json.loads(m)
archive=(r/'context.sqlite3')
assert hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()==manifest['database_sha256']
def db(path):return sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
copy=db(archive);live=db(Path('/source/context.sqlite3'));restored=db(Path('/replacement/restored/context.sqlite3'))
def rows(c,n):return c.execute('select sequence,type,body from events where sequence<=? order by sequence',(n,)).fetchall()
n=manifest['last_sequence'];original=rows(live,n);checkpoint=rows(copy,n);replacement=rows(restored,n)
assert len(original)==len(checkpoint)==len(replacement)==manifest['audit_events'] and original==checkpoint==replacement
assert copy.execute('pragma integrity_check').fetchone()[0]=='ok' and restored.execute('pragma integrity_check').fetchone()[0]=='ok'
files={}
for f in sorted(Path('/archive/worker-native-audit').rglob('*')):
    if f.is_file():files[f.relative_to('/archive/worker-native-audit').as_posix()]={'bytes':f.stat().st_size,'sha256':hashlib.file_digest(f.open('rb'),'sha256').hexdigest()}
print(json.dumps(dict(sqlite_integrity='ok',byte_identical_original_audit_rows=len(original),last_sequence=n,audit=files,manifest_sha256=hashlib.sha256(m).hexdigest())))
"""

FAULT="""
import errno,json,runpy,sqlite3,sys
from pathlib import Path
op,archive_name,pin=sys.argv[1:];m=runpy.run_path('/tools/context_checkpoint.py')
src=Path('/source');small=Path('/small');archive=Path('/archive')/archive_name;dest=small/'incomplete'
try:
    if op=='capture':m['capture'](src,dest,'A')
    else:m['restore'](archive,dest,'A',pin)
except (sqlite3.Error,OSError) as error:
    full=(isinstance(error,OSError) and error.errno==errno.ENOSPC) or getattr(error,'sqlite_errorname','')=='SQLITE_FULL'
    assert full and not dest.exists() and not list(small.iterdir()),(repr(error),list(small.iterdir()))
    print(json.dumps(dict(operation=op,error=type(error).__name__,kind='ENOSPC',target_absent=True,temporary_files_remaining=0)))
else:raise AssertionError('Operation unexpectedly fit in the one-page filesystem')
"""


def main():
    p=argparse.ArgumentParser();p.add_argument("--case",type=Path,required=True);p.add_argument("--probe",type=Path,required=True)
    a=p.parse_args();f=Fixture(a.case)
    receipt=json.loads((a.probe/"result.json").read_text());assert receipt["passed"]
    source=f.bind("original","/source",sub="current",readonly=True)
    archive=f.bind("archive","/archive",readonly=True)
    replacement=f.bind("replacement","/replacement",readonly=True)
    tool=f.bind("fixture","/tools",sub="tools",readonly=True)
    name=receipt["audit_cutover"]["restored_archive"];pin=receipt["verified_empty_volume_restore"]["restored"]["manifest_sha256"]
    check=json.loads(f.helper(["-I","-c",CHECK,name,pin],volumes=[*source,*archive,*replacement]).stdout)
    assert check["audit"]==receipt["durable_original_native_audit"]==receipt["live_native_audit"]
    faults=[]
    for op in ("capture","restore"):
        result=docker("run","--rm","--network","none","--read-only","--user","10003:10003","--cap-drop","ALL","--security-opt","no-new-privileges",
            "--tmpfs","/small:rw,size=4k,mode=0777,nosuid,nodev","--entrypoint","python",*source,*archive,*tool,FINAL,"-I","-c",FAULT,op,name,pin)
        faults.append(json.loads(result.stdout))
    final={"passed":True,"retained_volume_verification":check,"enospc_on_operator_storage":faults,
           "scope":"Online and restored Context events, retained native ASRUN and operator backup/restore behavior on a real full filesystem."}
    (a.probe/"storage.json").write_text(json.dumps(final,indent=2)+"\n")
    print(json.dumps(final))


if __name__=="__main__":main()
