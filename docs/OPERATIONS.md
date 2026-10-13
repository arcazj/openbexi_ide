# Installation diagnostics and recovery

Run `openbexi doctor` for a read-only installation inventory, or
`openbexi doctor --desktop` to check the locked desktop dependencies too. A
nonzero exit reports an unsupported interpreter or missing desktop dependency.
The report includes package versions and optional backend identifiers. It does
not import plugin entry points, connect to a service, read projects, or include
environment values, credentials or user paths. Runtime readiness and native
plugin conformance still require their separate acceptance checks.

## Supported candidate profiles

| Profile | Runtime | Distribution | Boundaries |
| --- | --- | --- | --- |
| Windows x64 | CPython 3.13.15, locked Qt/debugpy | Offline per-user bundle | Fresh VM qualification pending |
| Linux x86_64 | CPython 3.13.15, locked Qt/debugpy | Local Docker/noVNC image | Loopback browser desktop; live pointer acceptance pending |
| Native SPELL | Optional separately installed host wheel | Original native container runtime | Full language conformance follows sibling plugin gates |

Ordinary Python needs no SPELL plugin. Shared Debug uses Python/debugpy. Native
SPELL supports the separately qualified local debugger and shared Run profiles.
The Docker lab's bounded SPELL/DSS fixture is identified separately from the
original native runtime. Local development processes are trusted code; process
ownership is cleanup support, not a security sandbox.

## Preserve projects and settings

The Windows installer keeps private versioned runtimes and activates a selected
version. It does not overwrite projects or copy arbitrary pip installations into
the new runtime. Install optional wheels for each selected interpreter. The
uninstaller checks ownership and hashes and preserves unknown or modified files.
An active private interpreter blocks removal. Keep the previous bundle and its
manifest when rehearsing an upgrade.

Docker workspace and preferences reside in the named volumes declared by the
selected Compose file. Use `stop` and `start` for an ordinary pause. Keep the
volume names and image ID in the deployment record. A new candidate uses its own
volumes; copy projects explicitly after saving edits. Do not delete volumes as
part of a routine update.

## Durable authority backup and recovery

Stop the authority service and verify all its owned workers and children have
stopped before making a filesystem backup. Retain the complete state directory,
captured sources, approved runtime manifests/images, identity policy and audit
records together. Store private keys and invitations with restricted access,
separately from shareable diagnostic reports. Hash the copied files and retain
the source version and shutdown evidence. A copy of an active SQLite directory
is not a qualified backup workflow.

A backup is historical evidence. Restoring an old database can roll back epochs,
procedure fences, revocations and effect receipts. Never restart that old copy as
an operational authority merely because it opens successfully. Keep it offline
for reconciliation; independently determine what happened after the backup.
Provision a new authority identity, rotate client credentials, reapprove the
reviewed runtime/source releases, and explicitly submit only procedures whose
external effects have been settled. Keep the original authority fenced.

For recovery of the current durable directory after service loss, the service
retains uncertain procedures in `RECOVERY_REQUIRED` and does not replay them.
The documented [offline reconciliation](DURABLE_SERVICE.md) requires evidence
of both worker shutdown and settlement of possible external effects. Only then
can an operator explicitly authorize a new execution. Do not clear a hold by
editing SQLite, removing a lock file, or changing procedure IDs.

## Release acceptance

`python scripts/check_release.py --manifest docs/IDE_RELEASE_DOSSIER.json`
checks artifact/report hashes and all required Windows/Docker gates. A missing,
pending, mismatched or failed report keeps acceptance false. The checker records
evidence status; it cannot manufacture browser interaction or fresh-machine
observations. The sibling plugin maintains its own conformance/distribution
decision independently of the IDE version.
