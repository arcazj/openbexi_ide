# Native shared Development milestone

The durable service can execute captured SPELL procedures through the optional
`openbexi-spell-shared` provider. The neutral core discovers installed providers
through `openbexi.shared_backends.v1`; it imports no SPELL runtime or DSS code.
The provider owns the original native listener, context and executor through
the already qualified `openbexi-spell-host:0.3.0` Linux image and its DAP adapter.
The bounded Python SPELL adapter remains the default for ephemeral sessions.

This is a tested Development prerequisite. IDE v0.3 and plugin v0.4 remain
open. It does not approve native Execution, connect operational DSS transports,
or replace the original driver contracts with a substitute driver.

## Install and run

Use CPython 3.13 on the service host and a local Linux amd64 Docker engine.
Install the core and both optional plugin wheels into the **service interpreter**:

```powershell
python -m pip install ./openbexi_ide-0.2.0-py3-none-any.whl ./openbexi_spell_host-0.3.0-py3-none-any.whl ./openbexi_spell_shared-0.4.0.dev1-py3-none-any.whl
openbexi serve --project C:/work/committed-procedures --state-directory C:/work/native-authority --info C:/work/native-server.json --port 9010
openbexi --connection C:/work/operator.json connect --user Operator --invite-file C:/work/native-server.json
openbexi --connection C:/work/operator.json claim
openbexi --connection C:/work/operator.json submit main.py --language spell
openbexi --connection C:/work/operator.json watch --renew
```

The source project must be a committed Git repository. A procedure uses explicit
imports such as `from spell.lang.functions import Display`. Native arguments
accept zero arguments or one JSON object, matching the local native host adapter.
Use the desktop's SPELL runtime selector after joining the durable session, or
submit through the CLI. Native prompts appear in shared output; send the native
option index with the existing input control. EOF causes a recovery hold.

The default native image tag is resolved to its exact image ID at submission.
`OPENBEXI_SPELL_SHARED_IMAGE` selects a different locally installed candidate for
new submissions. Queued work retains its captured source and original image ID
across configuration changes and service restarts. The procedure version includes
the provider profile/version and image binding. Missing or duplicate providers,
an unsupported stored binding or a missing image fail closed; no fallback runs
the bounded Python adapter for durable native work.

## Control, pause and recovery

The existing durable authority governs admission, logical aliases, leases,
fencing, controller handoff, monitor restrictions and audited commands. Native
workers cannot use the Python checkpoint endpoint. Their runtime configuration
and ownership are persisted before external startup. Startup opens the native
executor paused; only a current service grant continues user code.

Shared Pause uses Docker's whole-container freezer. The service reserves the
slot until the owned container reports both running and paused. Every native
process and descendant is frozen, including children which do not participate
in Python tracing. Resume requires an explicit controller command and a new
available slot. It unfreezes that same container. Shared Pause does not promise
a native statement boundary or shared DAP stack/variable inspection.

An unconfirmed freeze, transport failure, abnormal exit, forced Stop or service
loss creates an uncertain-effect hold. Recovery removes only the matching named,
labelled and image-bound container. A foreign ownership mismatch blocks recovery
without deleting that container. Recovery never relaunches a started procedure;
queued work stays paused until explicitly resumed. The original offline shutdown
and effect-reconciliation receipt remains required to clear a hold.

This Development provider has no independent lease watchdog inside its container.
Service loss can trigger native EOF cleanup, but recovery must confirm removal;
assume effects are uncertain until that cleanup and reconciliation are verified.

Freezing cannot undo work already accepted by an external system. This profile
uses the original isolated example driver and disables container networking.
It provides no operational command receipt, telemetry or external-effect proof.

## Runtime and results

Containers have no host mounts or published ports, run as the image's unprivileged
user, drop capabilities, disable privilege escalation and use a private tmpfs.
They have a 256-process limit, 1 GiB memory/swap ceiling and one CPU limit.
The native Development filesystem remains writable. This is not the approved,
read-only Python Execution isolation profile. Docker and its administering OS
account are trusted. Do not mount a Docker socket into the browser desktop merely
to enable this feature; run the service on the prepared Docker host.

Normal native termination drains ordered output, closes the native session and
verifies that no live descendants remain beyond the adapter's startup processes.
An independently detached child prevents clean completion and requires recovery.
The provider then
exports changed files to `STATE/results/.openbexi/runs/PROCEDURE/artifacts` with
an input/image/output manifest. The live worktree and captured source stay intact.
The existing native host exporter enforces its path, link and size restrictions;
its excluded internal/environment paths remain excluded from artifact export.
Forced termination does not guarantee artifacts. An export failure retains a
recovery hold. Native DAP frames and pending messages are bounded, and long output
is split into bounded durable events.

## Qualification and remaining work

[NATIVE_SHARED_QUALIFICATION.json](NATIVE_SHARED_QUALIFICATION.json) records exact
source, wheel, image and evidence hashes. Acceptance covers Windows x64 / CPython
3.13.15 controlling Linux amd64 Docker workers: 96 core tests, eleven native cases,
three repeated provider-contract cases, eight fresh-core Execution checks and seven
fresh installed-provider checks. The native cases include actual Qt operator and
monitor clients, descendant quiescence, handoff, lease expiry, prompts, capture
tampering, runtime binding, failed pause, foreign-container preservation and real
service termination/recovery and detached-child completion rejection. Tests treat
warnings as errors.

Native shared debugger inspection, approved native Execution, original DSS
driver/RPC integration, external-effect receipts, full provenance and the later
763-row conformance/distribution/upgrade gates remain open. This milestone does
not change the IDE 0.2.0 or accepted native host 0.3.0 versions or release tags.
