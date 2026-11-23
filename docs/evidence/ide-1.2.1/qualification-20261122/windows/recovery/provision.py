"""Derive a two-slot recovery fixture from the checked ten-slot test issuer within its isolated volume."""

import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import ssl


source = runpy.run_path("/load-provision.py")
root, private, openssl = source["root"], source["private"], source["openssl"]
write = source["write"]
old_pins = source["pins"]
case = json.loads((root / "case.json").read_text())
roles = ("context", "listener", "gateway", "worker-02")
for generation in ("rc0", "live", "restored", "rollback"):
    (root / generation).mkdir()
    for role in roles:
        shutil.copytree(root / role, root / generation / role)
        os.chown(root / generation / role / "tls.key", 10003, 10003)

new_pins = dict(old_pins)
for role in ("context", "listener", "worker-02"):
    dest = root / "restored" / role
    openssl("req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=replacement-" + role, "-keyout", dest / "new.key", "-out", "rotated-" + role + ".csr")
    openssl("x509", "-req", "-in", "rotated-" + role + ".csr", "-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial",
            "-days", "1", "-extfile", "ext", "-out", dest / "tls.pem")
    (dest / "new.key").replace(dest / "tls.key")
    (dest / "tls.key").chmod(0o400)
    os.chown(dest / "tls.key", 10003, 10003)
    new_pins[role] = hashlib.sha256(ssl.PEM_cert_to_DER_cert((dest / "tls.pem").read_text())).hexdigest()
    for item in ("tls.key", "tls.pem"):
        rollback = root / "rollback" / role / item
        rollback.unlink()
        shutil.copyfile(dest / item, rollback)
        if item.endswith(".key"):
            rollback.chmod(0o400)
            os.chown(rollback, 10003, 10003)

for generation in ("rc0", "live", "restored", "rollback"):
    rotated = generation in ("restored", "rollback")
    old_version = generation in ("rc0", "rollback")
    pins = new_pins if rotated else old_pins
    workers = {"recovery-slot": "incarnation-after-fence"} if rotated else {f"worker-{i:02}": f"instance-{i:02}" for i in (1, 2)}
    for role in roles:
        cfgfile = root / generation / role / "config.json"
        cfg = json.loads(cfgfile.read_text())
        if role == "context":
            cfg["listener_fingerprint"] = pins["listener"]
            cfg["worker_slots"] = workers
            cfg["worker_credentials"]["identities"] = (
                {pins["worker-02"]: {"slot": "recovery-slot", "incarnation": "incarnation-after-fence"}} if rotated else
                {pins[w]: {"slot": w, "incarnation": v} for w, v in workers.items()})
            if old_version:
                cfg.pop("worker_launch")
                # The RC1 public surface is reservation-only; no native worker is started with this profile.
                for name in ("native_children", "native_controls", "native_commands", "native_prompts"):
                    cfg.pop(name)
        elif role == "listener":
            cfg["contexts"]["A"]["fingerprint"] = pins["context"]
            if old_version:
                cfg.pop("native_launch_contexts")
                cfg.pop("native_command_contexts")
        elif role == "gateway":
            cfg["listener_fingerprint"] = pins["listener"]
        else:
            cfg["assigned"]["context_fingerprint"] = pins["context"]
            if rotated:
                cfg["assigned"].update(worker_slot="recovery-slot", worker_incarnation="incarnation-after-fence")
        write(cfgfile, cfg)
case["old_private_identities"] = {r: old_pins[r] for r in ("context","listener","worker-02")}
case["replacement_private_identities"] = {r: new_pins[r] for r in ("context","listener","worker-02")}
case["unchanged_public_gateway_pin"] = old_pins["gateway"]
write(root / "case.json", case)
(root / "tools").mkdir()
shutil.copyfile("/context_checkpoint.py", root / "tools/context_checkpoint.py")
for dest in (Path("/state-original/current"),):
    dest.mkdir(mode=0o700)
    os.chown(dest, 10003, 10003)
for dest in (Path("/archive"), Path("/replacement")):
    os.chown(dest, 10003, 10003)
