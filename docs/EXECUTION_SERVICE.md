# Approved offline Python Execution

This partial IDE v0.3 milestone adds an approved, immutable Python Execution
profile to the existing durable session service. The package remains 0.2.0.
Native shared SPELL, operational DSS effects and full v0.3 acceptance remain open.
Exactly three operating modes remain: Development, read-only Monitoring and
Execution. `python-docker-offline/1` is an Execution profile, not another mode.

## Source, runtime and approval

`release-prepare` captures the clean committed Git tree using the existing
bounded capture rules. A release explicitly lists 1–128 runnable Python files;
other tracked files are dependencies. It builds an image containing the source
at `/release`, the neutral worker, and the selected runtime's exact filesystem.
The manifest binds Git commit/tree/blob identities, every captured file's
SHA-256, logical procedure identities, immutable image/base IDs, the interpreter
binary hash, CPython version and installed package names/versions. Procedure
version identity includes the runtime image and captured source inventory.

The whole image freezes installed dependency bytes. This does not establish
upstream package source provenance or independent reproducible builds. Those
remain distribution/operational qualification work. Only Linux amd64 images with
CPython 3.13 and no declared writable volumes are admitted. The preparation
directory retains the capture, build context, recipe, image ID and manifest.
Preparation never grants approval.

An operator reviews that exact manifest, source and runtime, then runs
`release-approve` with its expected release digest, their identity and a reference
to retained review evidence. Approval rechecks the actual image's source,
procedure declarations and runtime inventory. It commits a release decision and
audit record to the durable authority. `release-revoke` records revocation.
Neither operation has an HTTP endpoint. Both require the exclusive service lock,
so the service must be stopped. The OS account administering the authority and
Docker daemon is trusted; the actor/evidence fields are operator attestations,
not signatures or an independent approval quorum.

Approval is checked at submission and again before worker creation. Queued
procedures retain their original release identity through restart. Switching the
service to a newer approved catalog cannot upgrade or bypass a queued release's
revocation. Catalog aliases and logical reservations retain the existing
single-authority admission rules across release versions. Separate durable
directories remain independent authorities and do not provide distributed locks.
The release catalog fails closed at 128 entries or 64 MiB; the separate decision
audit retains at most 10,000 records. No automatic archival/deletion is provided.

## Container boundary and lifecycle

Each execution gets its own Linux container, launched by immutable image ID:

- UID/GID 65532, read-only root/source/runtime, dropped capabilities,
  `no-new-privileges`, and Docker seccomp support required.
- No network, published ports, bind mounts, persistent volumes, Docker socket,
  host credentials or inherited host environment.
- One CPU, 256 MiB memory including swap allowance, 64 processes and a private
  16 MiB `/tmp`. `/tmp` is writable and mounted `noexec,nosuid,nodev`.
- Docker logging disabled; bounded session events retain stdout/stderr. Python
  and native writes are forwarded, including exit-handler and buffered C output.

The control channel uses attached process pipes. No worker HTTP listener or
client credential is exposed inside the container. Controller ownership,
handoff, leases, queue slots, input and read-only stack sampling use the existing
session protocol. Threads must acknowledge pause; live child processes retain
the slot until they exit. Normal execution runs from `/tmp`, so relative input
files should be located through `__file__` or `/release`. Temporary files are
discarded with the owned container; persistent artifact export is not included.

Control-channel loss or missing service heartbeats terminates the worker.
The service verifies and removes its exact labeled container on completion or
Stop. Restart removes only matching recorded containers, fences old client
credentials, retains uncertainty holds and leaves queued work paused. It never
replays interrupted work. Stop, abnormal exit and unconfirmed cleanup require
the existing [offline reconciliation](DURABLE_SERVICE.md#handoff-and-offline-reconciliation).
The operator must independently verify container shutdown before attesting it.

This boundary is qualified for reviewed Python procedures on the recorded Docker
Desktop/Linux runtime. It is not a claim of hostile-container escape resistance,
external-effect authorization, arbitrary platform support or native SPELL driver
acceptance. The local Docker account remains an administrative trust boundary.
The isolation settings follow Docker's documented
[container controls](https://docs.docker.com/engine/containers/run/) and
[daemon trust model](https://docs.docker.com/engine/security/).

## Prepare, approve and serve

Build the supplied minimal runtime from the repository root:

```powershell
docker build --file docker/Dockerfile.execution --tag openbexi-execution-python:3.13.15 .
$runtimeImage = docker image inspect openbexi-execution-python:3.13.15 --format '{{.Id}}'

$prepared = .venv/Scripts/python.exe -I run_cli.py release-prepare main.py `
  --procedure followup.py --project C:/work/procedures `
  --runtime-image $runtimeImage --output C:/work/releases/candidate-01 | ConvertFrom-Json
```

Use a new output directory and a clean committed procedure project. Preparation
may take several minutes. Review `candidate-01/release.json`, the retained source
and runtime image before recording approval. The following records that review
for the exact digest returned by preparation:

```powershell
.venv/Scripts/python.exe -I run_cli.py release-approve `
  --manifest $prepared.manifest --expected-release $prepared.release `
  --state-directory C:/work/execution-authority --actor Operator `
  --evidence 'Reference to completed source and runtime review'

.venv/Scripts/python.exe -I run_cli.py serve --project C:/work/procedures `
  --state-directory C:/work/execution-authority --execution-release $prepared.release `
  --port 9020 --info .session/execution-server.json
```

Connect, claim, submit, inspect, pause, hand off and stop using the existing CLI
or desktop. The desktop shows Execution, disables source editing/local debugging
and rejects Run when the displayed local procedure differs from the approved
source hash (allowing Git's Windows CRLF checkout conversion). Local files are a preview; the container executes its approved
image, including its dependencies. Stack paths under `/release` refer to that
image and currently are not mapped to local editor navigation. Monitoring
remains read-only. Remote access uses the existing mutual TLS identity profile.

Stop the service before revoking a release:

```powershell
.venv/Scripts/python.exe -I run_cli.py release-revoke `
  --release $prepared.release --state-directory C:/work/execution-authority `
  --actor Operator --evidence 'Reference to revocation decision'
```

The browser Development test lab is independent. This Execution profile does not
mount the Docker socket into that lab or replace its running services.

## Qualification

The recorded Windows controller / Linux amd64 container tests exercise actual
Docker, Git, SQLite, HTTP clients, Qt operator/monitor windows and service kills.
They cover approval/tamper rejection, read-only source/runtime, network denial,
native output, exit handlers, input, aliases, queues, handoff, child quiescence,
revocation, cleanup, crash holds and no automatic replay. A fresh non-editable
core wheel is separately checked without Qt or SPELL, including changed host
dependencies and real service kill/restart.

The accepted run passed all 93 source tests with warnings treated as errors,
zero failures/errors/skips, plus all eight fresh installed-core checks. The
controller was Windows x64 / CPython 3.13.15; workers used Linux amd64 on the
Docker Desktop/Engine versions recorded in the qualification manifest.

The optional Docker tests require an exact locally built runtime image ID:

```powershell
$env:OPENBEXI_EXECUTION_TEST_IMAGE = $runtimeImage
.venv/Scripts/python.exe -m pytest tests -q -W error
```

Without that variable, the eight real-Docker scenarios are explicitly skipped;
the manifest parser and ordinary regression tests still run. See
[the qualification manifest](EXECUTION_QUALIFICATION.json) for exact source,
wheel, runtime and evidence identities. No release tag is advanced by this work.
