"""Exercise the installed pinned-mTLS client against an independent ten-slot public deployment."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

from openbexi_runtime.spell_server_client import SpellServerClient, SpellServerError


def key():
    return str(uuid.uuid4())


def stamp():
    return datetime.now(timezone.utc).isoformat()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--case", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    case_dir, out = args.case.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    deployment = json.loads((case_dir / "deployment.json").read_text())
    case = json.loads((case_dir / "case.json").read_text())
    prefix = deployment["prefix"]
    workers = case["workers"]
    assert deployment["ready"] and len(workers) == 10
    procedure_ids = sorted(case["source_sha256"])
    now = time.monotonic()
    folder = Path(importlib.metadata.distribution("openbexi-ide").locate_file("")).resolve()
    assert folder.is_relative_to(Path(sys.prefix).resolve())
    report = {"client_version": importlib.metadata.version("openbexi-ide"), "site_packages": str(folder),
              "server_image": deployment["server_image"], "worker_image": deployment["worker_image"],
              "fixture": hashlib.sha256((case_dir / "case.json").read_bytes()).hexdigest(),
              "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "phases": [],
              "verdicts": {}, "started": stamp(), "passed": False}

    def record(name, value):
        report[name] = value
        report["phases"].append({"name": name, "time": stamp(), "elapsed_seconds": round(time.monotonic()-now, 3)})
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(name, flush=True)

    def client(subject):
        return SpellServerClient.from_config(case_dir / "clients" / subject / "connection.json")

    owner = client("alice")
    observers = {name: client(name) for name in case["subjects"] if name.startswith("watch-")}
    assert len(observers) == 20 and len({case["subjects"][s] for s in observers}) == 20
    ids = {}
    binding_keys = ("procedure_id", "source_revision", "source_sha256", "runtime_image", "driver_binding")
    proofs = {}
    connection = None

    def worker_logs(worker):
        proc = subprocess.run(["docker", "logs", prefix + "-" + worker], capture_output=True, timeout=12, check=True)
        rows = []
        events = {"native-ready", "native-running", "native-finished"}
        for raw in (proc.stdout + proc.stderr).splitlines():
            try:
                row = json.loads(raw)
            except (UnicodeError, ValueError):
                continue
            if row.get("event") in events:
                rows.append({k: row[k] for k in ("event","execution_id","native_status","namespace_pid","native_lifecycle_receipts_settled",
                                                  "hold_retained","full_family_qualified") if k in row})
        return worker, rows

    def observe_workers():
        with ThreadPoolExecutor(10) as pool:
            return dict(pool.map(worker_logs, workers))

    def wait_workers(event, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            snapshot = observe_workers()
            if all(any(r["event"] == event for r in rows) for rows in snapshot.values()):
                return snapshot
            time.sleep(0.5)
        record("last_worker_observation", snapshot)
        raise TimeoutError("Missing independent worker observations for " + event)

    def twenty_reads(expected, *, check_roles=False):
        barrier = threading.Barrier(20)
        def read(name):
            c = observers[name]
            barrier.wait(timeout=15)
            try:
                if check_roles:
                    assert c.contexts() == ["A"]
                    health = c.read("A", "health")
                    assert health["subject"] == name and set(health["permissions"]) == {"context:read", "execution:read"}
                rows = c.read("A", "executions")["executions"]
                assert {row["id"] for row in rows} == expected
                terminal = sum(row.get("native_root_result") == "FINISHED" for row in rows)
                return name, {"fingerprint": case["subjects"][name], "rows":len(rows), "finished":terminal}
            except Exception as e:
                return name, {"error":str(e)}
        with ThreadPoolExecutor(20) as pool:
            return dict(pool.map(read, observers))

    def reserve(name):
        item = catalog[name]
        payload = {field: item[field] for field in binding_keys}
        return owner.authority("A", "execution.reserve", dict(payload, connection_id=connection), key=key())

    def register(name, proof):
        assert owner.remember_controller("A", proof)
        ids[name] = proof["id"]
        proofs[name] = proof

    try:
        assert owner.contexts() == ["A"]
        health = owner.read("A", "health")
        assert health["subject"] == "alice" and health["native_launch"]
        catalog = {row["procedure_id"]:row for row in owner.read("A", "procedures")["procedures"]}
        assert sorted(catalog) == procedure_ids
        assert all(row["source_sha256"] == case["source_sha256"][name] and row["source_revision"] == case["revision"]
                   and row["runtime_image"] == deployment["worker_image"] for name,row in catalog.items())
        record("catalog", {name:{k:item[k] for k in binding_keys} for name,item in catalog.items()})
        first_reads = twenty_reads(set(), check_roles=True)
        record("twenty_authenticated_observers", first_reads)
        report["verdicts"]["twenty_simultaneous_authenticated_reads"] = "PASS" if all("error" not in row for row in first_reads.values()) else "FAIL"
        c = observers["watch-01"]
        try:
            c.authority("A","session.open",{},key=key())
            raise AssertionError("Observer obtained a controller session")
        except SpellServerError as error:
            assert error.status == 403
            record("observer_authority_denied", {"status":error.status,"code":error.code})
        connection = owner.authority("A","session.open",{},key=key())["connection_id"]
        race = threading.Barrier(100)
        lock = threading.Lock()
        accepted = []
        def contend(index):
            race.wait(timeout=30)
            start = time.monotonic()
            receipt = {"index":index, "started_offset_seconds":round(start-now,5)}
            try:
                response = reserve(procedure_ids[0])
                receipt.update(status=200, execution_id=response["id"])
                with lock: accepted.append(response)
            except SpellServerError as error:
                receipt.update(status=error.status, code=error.code)
            except Exception as error:
                receipt.update(status=0, error=type(error).__name__)
            receipt["seconds"] = round(time.monotonic()-start,5)
            return receipt
        with ThreadPoolExecutor(100) as pool:
            contention = list(pool.map(contend, range(100)))
        record("competing_requests", contention)
        rows = owner.read("A","executions")["executions"]
        once = len(rows) == 1 and rows[0]["procedure_id"] == procedure_ids[0]
        record("race_admission", {"public_reservations":len(rows), "owner_response_count": len(accepted),
               "response_counts":dict(Counter(str(r["status"])+"/"+str(r.get("code","")) for r in contention)),
               "public_execution_ids":[r["id"] for r in rows],
               "start_spread_seconds":round(max(x["started_offset_seconds"] for x in contention)-min(x["started_offset_seconds"] for x in contention),5)})
        report["verdicts"]["one_durable_reservation_from_100_simultaneous_attempts"] = "PASS" if once else "FAIL"
        assert once and len(accepted) <= 1
        if accepted:
            register(procedure_ids[0], accepted[0])
        else:
            # Explicit recovery after reading the uncertain outcome. No command or reservation is replayed.
            row = rows[0]
            new = owner.authority("A","session.open",{},key=key())["connection_id"]
            proof = owner.authority("A","execution.rebind",{"execution_id":row["id"], "connection_id":new,
                                   "expected_epoch":row["epoch"]},key=key())
            register(procedure_ids[0], proof)
            record("explicit_connection_rebind", {"execution_id":row["id"]})
        for name in procedure_ids[1:]:
            register(name, reserve(name))
        record("ten_public_reservations",ids)
        def start(name):
            try: return name,owner.launch("A",ids[name],key=key())
            except Exception as error: return name,{"error":str(error)}
        with ThreadPoolExecutor(3) as pool:
            launches = dict(pool.map(start, procedure_ids))
        record("public_launch_receipts", launches)
        assert all(r.get("state") == "ADMITTED" for r in launches.values())
        ready = wait_workers("native-ready",65)
        record("ten_simultaneously_paused",ready)
        actual = {r["execution_id"] for rows in ready.values() for r in rows if r["event"]=="native-ready" and r.get("native_status")=="PAUSED"}
        assert actual == set(ids.values())
        reads = twenty_reads(actual)
        record("twenty_observers_of_ten_live_executions", reads)
        def go(name):
            try:
                receipt=owner.command("A",ids[name],"CMD_RUN",key=key())
                return name,{k:receipt[k] for k in ("state","status","receipt_id","request_id") if k in receipt}
            except Exception as error: return name,{"error":str(error)}
        with ThreadPoolExecutor(10) as pool:
            commands = dict(pool.map(go,procedure_ids))
        record("run_commands",commands)
        assert all("error" not in r for r in commands.values())
        live = wait_workers("native-running",55)
        record("native_running_overlap", live)
        simultaneous = all(not any(r["event"]=="native-finished" for r in rows) for rows in live.values())
        report["verdicts"]["ten_distinct_native_procedures_running_simultaneously"] = "PASS" if simultaneous else "FAIL"
        terminal = wait_workers("native-finished",90)
        record("native_terminal",terminal)
        direct = sorted(r["execution_id"] for rows in terminal.values() for r in rows if r["event"]=="native-finished"
                        and r.get("native_status")=="FINISHED" and r.get("native_lifecycle_receipts_settled"))
        assert direct == sorted(ids.values())
        final = twenty_reads(set(ids.values()))
        record("twenty_public_terminal_views",final)
        report["verdicts"]["twenty_observers_received_ten_finished_results"] = "PASS" if all(r.get("finished")==10 for r in final.values()) else "FAIL"
        report["passed"] = all(v=="PASS" for v in report["verdicts"].values())
    except BaseException as error:
        record("error",repr(error)); raise
    finally:
        if connection:
            try: owner.authority("A","session.close",{"connection_id":connection},key=key())
            except Exception as error: report["close_error"] = str(error)
        owner.forget()
        for c in observers.values(): c.forget()
        record("completed",stamp())
    if not report["passed"]: raise SystemExit(1)


if __name__ == "__main__":
    main()
