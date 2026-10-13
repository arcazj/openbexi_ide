# Durable plugin Execution — IDE v0.3

The durable collaborative service now admits an installed runtime provider into
the same immutable release authority used for Python. The neutral core contains
no SPELL, DSS, Kafka or protobuf imports. `plugin-docker-isolated/1` is a release
profile within Execution; the only operating modes remain Development,
read-only Monitoring and Execution.

The optional SPELL provider 0.4.0 supplies the native worker, original driver RPC
and GENERIC DSS bridge. See the sibling plugin's `docs/DRIVER_RUNTIME.md` and
`docs/DRIVER_QUALIFICATION.json`; this repository records its neutral prerequisite
evidence in [PLUGIN_EXECUTION_QUALIFICATION.json](PLUGIN_EXECUTION_QUALIFICATION.json).
The older durable/Python/native qualification documents remain historical
snapshots, including the limitations that applied to their prerelease artifacts.

## Immutable release and effects

Preparation captures the clean Git tree and resolves the installed provider's
bounded JSON binding. Its image must match the reviewed base image. The release
image freezes procedure dependencies, original runtime, driver wheel and neutral
runtime bytes; its manifest binds source hashes, interpreter hash, package
inventory, image/base IDs, provider version and driver endpoints. Provider
`for_release` validates the profile and derives an Execution binding using the
canonical approved manifest digest. Approval rechecks actual image contents.

The provider receives a private service callback. The service serializes requests
against control changes and checks controller, lease, slot, execution intent,
logical fence and current approval before dispatch and before each external
command stage. Only the service constructs the authority identity. Providers are
trusted installed extensions, not arbitrary procedure plugins. Their private
requests cannot release admission slots or supply controller credentials.

The native provider uses UID/GID 10003, a read-only root and release, no network,
mounts, host credentials or Docker socket, dropped capabilities, no-new-privileges,
required seccomp, one CPU, 1 GiB memory, 256 processes and a private 256 MiB noexec
tmpfs. It verifies whole-container pause before slot reuse and checks descendant
shutdown before clean completion. Its parent-loss watchdog is independent of
procedure execution. The Python profile retains its own smaller resource bounds.

Approval is required on submission, startup and while running. Revocation or an
uncertain driver result stops the worker and retains a recovery hold. Recovery
uses the provider's exact container ownership check before generic Python
recovery. Old credentials remain fenced; reapproval alone cannot clear a run's
uncertainty. Offline reconciliation still requires independent effect evidence.
No worker replay occurs during recovery.

## Procedure release workflow

Install the IDE wheel and the optional provider as described by the plugin, then
configure the service-owned DSS endpoints. In a clean committed procedure project:

```powershell
$runtimeImage = docker image inspect openbexi-spell-dss:0.4.0 --format '{{.Id}}'
openbexi release-prepare main.py --backend spell --project C:/work/procedures --runtime-image $runtimeImage --output C:/work/releases/native-01
```

Use the separate review/approve/serve commands in
[EXECUTION_SERVICE.md](EXECUTION_SERVICE.md#prepare-approve-and-serve), substituting
the prepared native manifest and its digest. Select SPELL when submitting a
native release. A release admits only its declared provider and procedure list;
mutable host edits cannot replace its embedded sources. The live session never
exposes release approval as a client API.

## Accepted scope and later work

IDE v0.3 qualifies a single durable authority on Windows x64 with the recorded
Linux amd64 Docker runtime, certificate identities/TLS, revocation, bounded
events, audited handoff, captured dependencies, logical aliases, controller
leases/fences and uncertainty holds. Its native effect prerequisite is qualified
against GENERIC DSS. Monitoring remains unable to execute, enter input, answer
prompts or evaluate expressions. Existing Qt regression covers the same session
controls and read-only Execution UI.

Content identities and upstream native source/schema provenance are recorded in
the release evidence. Independent reproducibility, transitive supplier audits,
distributed authorities, hostile-container security, shared native debugger
inspection and real-mission operational approval are separate later gates.
Plugin full-language conformance and distribution remain v0.5 and v0.6. Local
IDE host 0.3.0 artifacts retain their earlier acceptance and are not rebuilt here.
