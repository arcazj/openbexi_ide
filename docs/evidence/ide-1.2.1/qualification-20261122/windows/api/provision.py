"""Prepare a certificate-scoped ten-slot qualification fixture inside its private Docker volume."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess

from openbexi_spell_server.contracts import digest
from openbexi_spell_server.snapshots import git_manifest


root = Path("/case")
image = os.environ["WORKER_IMAGE"]
port = int(os.environ["PUBLIC_PORT"])
roles = ("context", "listener", "gateway")
workers = [f"worker-{i:02}" for i in range(1, 11)]
observers = [f"watch-{i:02}" for i in range(1, 21)]
subjects = ["alice", *observers]
for directory in [*roles, *workers, "clients", "git", "snapshot", "state", "audit"]:
    (root / directory).mkdir(mode=0o755)
for subject in subjects:
    (root / "clients" / subject).mkdir(mode=0o700)
private = Path("/tmp/load-pki")
private.mkdir(mode=0o700)


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def openssl(*args):
    subprocess.run(["openssl", *args], cwd=private, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=local-load-qualification",
        "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign",
        "-keyout", "ca.key", "-out", "ca.pem")
(private / "ext").write_text("subjectAltName=DNS:context,DNS:listener,DNS:gateway,IP:127.0.0.1\n"
                             "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n"
                             "extendedKeyUsage=serverAuth,clientAuth\n")
pins = {}
for name in [*roles, *workers, *subjects]:
    directory = root / "clients" / name if name in subjects else root / name
    openssl("req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=" + name, "-keyout", directory / "tls.key", "-out", name + ".csr")
    openssl("x509", "-req", "-in", name + ".csr", "-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial",
            "-days", "1", "-extfile", "ext", "-out", directory / "tls.pem")
    shutil.copyfile(private / "ca.pem", directory / "ca.pem")
    pins[name] = hashlib.sha256(ssl.PEM_cert_to_DER_cert((directory / "tls.pem").read_text())).hexdigest()
    (directory / "tls.key").chmod(0o400)
    os.chown(directory / "tls.key", 10003, 10003)

gitdir = root / "git"
def git(*args):
    return subprocess.check_output(["git", "-C", gitdir, *args], text=True,
                                    env=dict(os.environ, GIT_AUTHOR_DATE="2026-11-22T00:00:00Z", GIT_COMMITTER_DATE="2026-11-22T00:00:00Z")).strip()


git("init", "-q")
procedures = [f"procedure-{i:02}" for i in range(1, 11)]
for name in procedures:
    # All ten can be directly observed in RUNNING during the same bounded period.
    content = ("import time\nfrom pathlib import Path\ntime.sleep(12)\n"
               f"Path('/workspace/{name}.done').write_text('{name} finished')\n").encode()
    for directory in (gitdir, root / "snapshot"):
        (directory / (name + ".py")).write_bytes(content)
git("add", "--all")
git("-c", "user.name=Qualification", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "Approved ten-procedure load fixture")
revision = git("rev-parse", "HEAD")
entries, checksums = {}, {}
for name in procedures:
    filename = name + ".py"
    checksums[name] = digest(git_manifest(gitdir, revision, filename))
    entries[name] = dict(repository="/git", revision=revision, entrypoint=filename, runtime_image=image, driver_binding="context-audit", aliases=[])
for current, directories, files in os.walk(gitdir):
    os.chown(current, 10003, 10003)
    for filename in files:
        os.chown(Path(current) / filename, 10003, 10003)
for name in ["state", "audit"]:
    os.chown(root / name, 10003, 10003)
    (root / name).chmod(0o700)

tls = dict(ca="/credentials/ca.pem", certificate="/credentials/tls.pem", key="/credentials/tls.key")
common = dict(tls, bind="0.0.0.0", port=9443, max_handlers=64)
scope = {s: ["context:read", "execution:read"] for s in observers}
scope["alice"] = ["context:read", "execution:read", "execution:start", "execution:control", "execution:request_control"]
slots = {name: f"instance-{i:02}" for i, name in enumerate(workers, 1)}
write(root / "context/config.json", dict(common, allowed_hosts=["context:9443"], context_id="A", state_directory="/state",
      listener_fingerprint=pins["listener"], subjects=scope, worker_slots=slots, worker_launch="assigned-single-use",
      worker_credentials={"profile": "single-host-preflight", "identities": {pins[w]: {"slot": w, "incarnation": slots[w]} for w in workers}},
      approved_sources=entries, native_children="admission-only", native_controls="run-journal", native_commands="owner-queue",
      native_prompts="owner-reply-candidate"))
write(root / "listener/config.json", dict(common, allowed_hosts=["listener:9443"], edge_fingerprint=pins["gateway"],
      identities={pins[s]: s for s in subjects}, scopes={s: ["A"] for s in subjects},
      contexts={"A": {"url": "https://context:9443", "fingerprint": pins["context"]}}, native_command_contexts=["A"], native_launch_contexts=["A"]))
write(root / "gateway/config.json", dict(common, allowed_hosts=[f"127.0.0.1:{port}"], listener_url="https://listener:9443",
      listener_fingerprint=pins["listener"], clients=[pins[s] for s in subjects]))
for worker in workers:
    write(root / worker / "config.json", {"assigned": dict(tls, context_url="https://context:9443", context_fingerprint=pins["context"],
          context_id="A", worker_slot=worker, worker_incarnation=slots[worker], runtime_image=image,
          snapshots={v: "/source" for v in checksums.values()}), "native_prompts": True})
    (root / "audit" / worker).mkdir(mode=0o700)
    os.chown(root / "audit" / worker, 10003, 10003)
for name in subjects:
    write(root / "clients" / name / "connection.json", {"url": f"https://127.0.0.1:{port}", "fingerprint": pins["gateway"],
          "ca": "ca.pem", "certificate": "tls.pem", "key": "tls.key"})
write(root / "case.json", dict(revision=revision, source_sha256=checksums, image=image, port=port, workers=workers,
      subjects={s:pins[s] for s in subjects}, permissions=scope, max_handlers=64))
