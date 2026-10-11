# Resume from openbexi_ide

Handoff prepared on 2026-10-11. Open `C:/projects/openbexi_ide` in IntelliJ
and keep `C:/projects/openbexi_spell_plugin` as its sibling repository. The old
`C:/projects/openbexi_spell` IntelliJ project can be closed without moving or
deleting its directory. Use the new repositories' roots for all Git commands.

## Preserve the user's files

The user explicitly requires that `C:/projects/openbexi_spell` stay on disk.
When it is no longer needed, explain that finding and ask the user before
removing it. Do not treat earlier general cleanup requests as permission to
delete this directory. Preserve this requirement across sessions.

Also preserve `C:/projects/.openbexi-archive/20261010-split/`, including the
legacy workspace, Git bundle, source archive and private configuration. The
legacy workspace still contains operational components needed for migration.
Do not publish that whole archive: it includes private configuration and runtime
records. Do not remove ignored qualification directories; a previous automatic
approval review rejected their recursive removal. Clean Docker resources only
when they are demonstrably obsolete project resources and unused by containers.

## Committed starting point

| Project | Accepted state before this documentation handoff |
| --- | --- |
| openbexi_ide | v0.2.0; optional native backend integration and documentation through `31f0eb0` |
| openbexi_spell_plugin | v0.3.0 tagged at `c34b21c`; native source foundation and three local IDE hosts accepted |

The projects have independent version numbers. IDE v0.3 durable shared service
is a prerequisite for plugin v0.4; it has not been implemented yet. Only analysis
had begun when the user requested this project switch. Plugin v0.4, v0.5 and
v0.6 remain open; do not infer their completion from the v0.3 host release.

Read these before resuming:

1. This repository's [master prompt](../openbexi_ide_master_prompt.md),
   [roadmap](../ROADMAP.md) and [runtime extension contract](RUNTIME_BACKENDS.md).
2. In the sibling plugin: `openbexi_spell_plugin_master_prompt.md`, `ROADMAP.md`,
   `docs/EXECUTION_TO_V06.md`, `docs/HOST_RUNTIME.md` and
   `docs/HOST_QUALIFICATION.json`.
3. The original manuals and SPELL 2.6.10 source in the plugin's `docs/reference`.
   In particular, use the Driver Development Manual and original RPC contracts.

## Next implementation work

Implement and qualify the neutral IDE's durable collaborative service: explicit
identity/TLS, revocation, bounded durable events, captured source/dependencies,
crash recovery and audited controller handoff. Preserve one fenced, leased
controller, configurable execution slots, logical-procedure admission across
versions/contexts, and uncertain-effect holds without automatic replay.

Inspect the preserved legacy `backend/procedure_identity.py`,
`backend/execution_locks.py`, `backend/executor_release.py` and their tests before
migrating their reusable rules and dependencies. Keep SPELL imports and domain
services out of the neutral IDE core. The current shared worker still uses the
bounded v0.1 SPELL adapter; local native host acceptance does not upgrade it.

Then implement plugin v0.4 using the original registry, factory, driver manager,
interfaces and `SPELLDriver.proto`, bridged explicitly to the existing DSS
binary/Kafka transport. Preserve exactly Development, read-only Monitoring and
approved Execution. These operating modes are distinct from controller roles.

Continue through plugin v0.5's complete 763-row conformance inventory and v0.6's
distribution/upgrade/reproducibility and actual host acceptance gates. Update
documentation, run meaningful tests and commit each completed phase in order.
Tag a release only after every gate for that release passes.

## Local evidence and runtime assets

The plugin's `docs/HOST_QUALIFICATION.json` binds the accepted v0.3 wheel, ZIP,
runtime image and tests to exact hashes. Accepted local artifact locations are:

- `.qualification/v0.3/host-wheels/openbexi_spell_host-0.3.0-py3-none-any.whl`
- `.qualification/v0.3/jetbrains-release-01/openbexi-spell-0.3.0.zip`
- `.qualification/v0.3/native-package-05/`
- Docker image `openbexi-spell-host:0.3.0`

These ignored local artifacts, `.venv`, service data and Docker images are not
part of a Git push. Preserve them when switching projects. Recheck live service
ownership before stopping anything; the user's DSS/session/desktop processes
must not be treated as disposable qualification processes.

## GitHub migration status

The two repositories were created under `arcazj` on 2026-10-11, initially private:

- [openbexi_ide](https://github.com/arcazj/openbexi_ide)
- [openbexi_spell_plugin](https://github.com/arcazj/openbexi_spell_plugin)

Both use `master` as their working/default branch and `origin` as their GitHub
remote. Initial publication preserves the existing commit histories and release
tags. A local commit does not publish changes: push `master` and new release
tags explicitly, then verify the remote identities.

The user subsequently requested deletion of the old GitHub repositories
`arcazj/openbexi_SPELL` and `arcazj/openbexi_REI`. Both were backed up on
2026-10-11 under
`C:/projects/.openbexi-archive/20261011-github-retirement/f5100ca154e5452da72da5bb7515a9b2/`.
`backup-manifest.json` records verified Git mirrors/bundles, LFS inventory,
seven releases and all 26 release assets, empty issues/PR inventories and REI's
Pages configuration. SPELL had no initialized wiki repository. This is not a
complete export of all GitHub account metadata.

The deletion attempts returned HTTP 403: the saved Git credential lacks
`delete_repo` scope. Both old repositories still existed at that verification;
`deletion-attempt.json` records the result. Deletion through the owner's GitHub
Settings pages, or an appropriately authorized credential, remains pending.
Recheck remote state before a later attempt. The new repositories are preserved.
The request to delete the two GitHub repositories does not authorize removal of
`C:/projects/openbexi_spell`; preserve it until the user confirms local removal.

## Restart instruction

> Read docs/RESUME_V04.md and the linked project instructions. Resume the IDE
> v0.3 durable-service prerequisite, then plugin v0.4, continuing through plugin
> v0.6. Preserve the old local project and archive. Ask before removing
> C:/projects/openbexi_spell. Test, update documentation and commit each phase.
