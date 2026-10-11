# Durable Development service prerequisite

This is a tested prerequisite milestone for IDE v0.3, not acceptance of that
release. IDE v0.3 and plugin v0.4–v0.6 remain open. The default loopback v0.2
service and its bounded SPELL adapter are still available. Durable sessions
currently admit Python only; they reject shared SPELL explicitly.

## Run a durable session

Use a dedicated service directory and a committed Git project:

```powershell
python -I run_cli.py serve --project C:/work/procedures --state-directory C:/work/session-data --port 9010
```

The service owns `session-data/service.lock` for its entire lifetime. A second
process cannot start against that authority, including during recovery. Use the
same directory after a restart: selecting another directory creates another
authority and does not inherit its admission reservations. This milestone does
not provide distributed admission between independent authorities.

SQLite transactions persist procedure metadata, logical reservations, fences,
configuration, event cursors and state changes before granting execution. The
rolling journal retains at most 2,048 events and 8 MiB. Each event is at most
64 KiB. Clients receive an explicit replay-gap indication after retention.
Control/audit events have separate retention, so output cannot displace a
handoff record. The audit store fails closed at 100,000 records or 16 MiB;
archival and provision of a replacement authority are explicit maintenance.
The service does not silently discard audit records. SQLite can retain freed
pages up to its previous high-water size; journal bounds are logical bounds.

Credential tokens, worker secrets and invitations are never persisted. A restart
revokes all connections, clears controller ownership and advances its fence.
Output and procedure identities remain available after clients reconnect.
Queued work remains paused and needs a new claim and explicit resume. Started
work becomes `RECOVERY_REQUIRED`, reserving its logical procedure and conservatively
reserving a slot until shutdown and effects are reconciled. No worker is restored,
replayed or adopted by PID. Persistence failure fences commands and terminates
owned workers while retaining the last committed recovery state.

## Captured source and dependencies

Durable submission requires the Git repository root and a clean tracked tree.
Commit tracked edits first. The capture reads exact Git objects without hooks
or an archive extractor. It captures all regular tracked files, including local
Python dependencies, and records commit, tree, blob and SHA-256 identities.
Untracked files are excluded and cannot be submitted as procedures. Submodules,
symlinks and nonportable/colliding paths are rejected. Limits are 4,096 files,
8 MiB per file and 64 MiB per captured tree.

Each run gets a separate capture directory. Before launch, the service verifies
the complete inventory and hashes; changed, added or missing dependencies fail
before worker creation. Editing the original working tree after admission does
not alter queued execution. Source capture runs outside the session control lock;
admission rechecks the controller fence afterward. The worker's ordinary output
files remain in its capture. Capture directories are retained; this milestone
does not add automatic source/artifact retention or deletion.

Logical identity preserves the legacy UUID namespace and comment declaration
rules. A `# @procedure-id LOWERCASE_UUID` in the first 64 lines provides a stable
version-4/5 UUID across renamed files and versions. Without a declaration, the
case-insensitive catalog path determines identity. An established catalog alias
cannot be rebound to another UUID. Aliases sharing a UUID share the reservation
through completion, cancellation, restarts and uncertainty. Admission and its
event are one transaction under the service's exclusive authority lock.

The legacy `procedure_identity.py`, `execution_locks.py`, `executor_release.py`
and their identity/admission/release tests were inspected in the preserved
archive before migration. This core retains their identity and no-TTL-release
rules without their SQLAlchemy, SPELL parser, native broker, DSS ledger or
operational projection dependencies. The legacy release authority itself has
not been migrated or presented as an operationally approved neutral service.

Captured Git files do not freeze the interpreter installation, third-party
wheels or external services. Captures are writable Development workspaces under
the service account. Their hashes establish launch provenance, not operational
isolation or an approved immutable Execution environment.

## Remote certificate identities

Direct remote service requires durable state, mutually authenticated TLS and an
explicit server-owned identity file. Its schema is:

```json
{
  "schema": 1,
  "identities": {
    "SHA256_OF_CLIENT_CERTIFICATE_DER_LOWERCASE_HEX": {
      "name": "Alice",
      "role": "developer"
    }
  }
}
```

Use `monitor` for a read-only identity. Names and roles come from the configured
certificate fingerprint, never a request's supplied name or invitation. Clients
need their own certificate/key and the server CA, provisioned by the service
owner. Do not distribute a shared client key.

```powershell
python -I run_cli.py serve --project C:/work/procedures --state-directory C:/work/session-data --host server.example --port 9010 --tls-cert server.pem --tls-key server.key --client-ca client-ca.pem --identities identities.json
python -I run_cli.py --connection .session/alice.json connect --url https://server.example:9010 --user Alice --tls-ca server-ca.pem --tls-cert alice.pem --tls-key alice.key
```

The server accepts TLS 1.2 or later. Clients verify trust and hostname; there is
no insecure certificate switch. A connection token is bound to its certificate
identity. Session redirects are rejected rather than forwarding credentials.
The worker uses a separate loopback listener that accepts worker checkpoints
only; remote TLS clients cannot post checkpoints to the client listener, and
the worker listener cannot be used to bypass remote client authentication.

The service rereads its identity file. Removing a fingerprint or changing its
name/role revokes existing connections and pauses its controller's work, including
idle connections. An unreadable or invalid identity file revokes all certificate
connections. Restoring the file does not restore tokens or controller ownership.
Certificate renewal requires provisioning the new fingerprint and reconnecting.
This milestone uses an explicit allowlist, not an external identity provider.

The CLI saves TLS file paths in its private connection JSON. For a desktop
connection, supply a private JSON file with `url` and `tls`:

```json
{
  "url": "https://server.example:9010",
  "tls": {"ca": "server-ca.pem", "certificate": "alice.pem", "key": "alice.key"}
}
```

Paths in this file are relative to its directory. Select it in the desktop join
dialog and use the matching URL and role. CLI `connect --invite-file` also accepts
this form. Monitor connections cannot claim, execute, supply input, answer
prompts, evaluate or edit shared work. Operating modes remain Development,
Monitoring and approved Execution; controller ownership is a separate role.

## Handoff and offline reconciliation

`handoff CLIENT_ID` pauses running and queued work, fences the former controller,
assigns the connected developer as the recipient and records both identities.
The recipient explicitly claims its credential and resumes after pause is
confirmed. Lease expiry, disconnect and certificate revocation also pause and
fence work. They never release a logical reservation or clear uncertain effects.

An interrupted Python procedure may already have affected external systems.
Even a zero exit code from forced Windows Job cleanup is not a settlement proof.
Stop, abnormal worker exit or crash therefore retains an uncertainty hold.
Pause/resume/stop and new submissions cannot bypass it. Successful normal Python
completion is accepted as completion; fine-grained external-effect receipts
remain part of the pending plugin/operational integration.

Only trusted offline maintenance can reconcile a hold. Stop the service, verify
all relevant workers/children are gone and independently settle possible external
effects. Retain evidence for both checks in a receipt:

```json
{
  "session": "SESSION_ID",
  "procedure": "PROCEDURE_ID",
  "fence": 1,
  "worker_shutdown_evidence": "Reference to verified worker/job shutdown evidence",
  "effect_settlement_evidence": "Reference to independently reconciled external effects"
}
```

```powershell
python -I run_cli.py reconcile --state-directory C:/work/session-data --receipt reconciliation.json
```

The command requires the exclusive service lock, matching session/procedure/fence,
an eligible held state and both evidence fields. It audits the receipt and marks
the old execution cancelled. A new submission is a separate explicit action
with a higher procedure fence. It never resumes or replays the old process.
The command records an authorized operator's attestation; it cannot determine
external effect truth from text. No network endpoint performs reconciliation.

## Evidence and remaining release gates

The source suite exercises real Git, SQLite, subprocesses, Windows Jobs, HTTP,
mutual TLS sockets and the Qt client. Cases include actual server termination
and fresh-process recovery, stale credentials, certificate revocation, monitor
denial, slow-capture revocation, concurrent alias admission, capture tampering,
bounded replay, retained audit, failure of persistence and offline reconciliation.
Windows process creation now suspends the launcher, attaches its owned Job and
then resumes its initial thread, preventing the venv worker from escaping the
parent Job during startup. The implementation uses Microsoft's documented
[thread inventory](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-createtoolhelp32snapshot)
and [ResumeThread](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-resumethread)
interfaces.

`scripts/qualify_durable_installed.py` separately checks a non-editable wheel in
a fresh interpreter with neither Qt nor SPELL. It executes captured dependencies,
kills/restarts the real service, checks worker shutdown and durable replay, and
rejects stale credentials, duplicate admission and automatic recovery replay.
Exact source/artifact hashes and results are recorded in
[DURABLE_QUALIFICATION.json](DURABLE_QUALIFICATION.json).

The final Windows x64 / CPython 3.13.15 run passes all 83 source tests with
warnings treated as errors (zero failures, errors or skips). The final wheel
also passes all seven installed core checks in a separate fresh environment.
These results include the existing desktop/runtime/debugger/session regressions.

IDE v0.3 remains open for approved immutable release authorization and qualified
Execution isolation, complete interpreter/third-party dependency capture,
operational external-effect receipts and native shared-runtime integration.
This milestone is qualified on Windows x64 / CPython 3.13 only. POSIX process
loss/descendant cleanup and other platforms are not accepted by this evidence.
Plugin v0.4's original DSS driver bridge, v0.5's 763-row conformance inventory
and v0.6's distribution/upgrade/actual-host gates have not been completed here.
No release version or acceptance tag is advanced by this milestone.
