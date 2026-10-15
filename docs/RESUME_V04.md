# Resume from openbexi_ide

The current Docker candidate is **1.0.0rc4**; start with
[its Docker record](IDE_RC4_DOCKER.md). The earlier **1.0.0rc3** artifacts remain in
[the v1.0 release record](IDE_V1_RELEASE.md) and
[the exact release dossier](IDE_RELEASE_DOSSIER.json). The console menu input
fix, shared Python debugging, Windows packaging, service limits and diagnostics
are implemented and tested. The actual noVNC gate now passes 13 checks, committed
as `db44911`. Final acceptance still needs installation in a fresh Windows
environment; this account cannot access Hyper-V VMs and has no Sandbox.

The IDE [v1.0.0rc4 prerelease](https://github.com/arcazj/openbexi_ide/releases/tag/v1.0.0rc4)
is published, with an annotated tag at `cf9baca`, the Windows bundle, wheel,
qualification records and checksums. Stable v1.0 acceptance remains open.

The user requested one replacement desktop at `http://127.0.0.1:6080/vnc.html`
and removal of all older IDE containers. Preserve their named volumes and
retained evidence. `compose.yaml` now selects rc4 with a fresh workspace.
At qualification, all 17 old IDE containers were removed, nine old named
volumes retained, and one healthy rc4 desktop served port 6080. Check current
container state before treating that historical observation as live. The final image,
seven native procedures, five installed SDK checks and browser menu evidence are
bound in [the rc4 qualification record](IDE_RC4_QUALIFICATION.json).
Windows rc4 also has two identical offline ZIPs and 14 passing rc3-to-rc4
upgrade/removal checks; [its record](IDE_RC4_WINDOWS_QUALIFICATION.json) binds
the long-path builder correction, extracted payload and actual lifecycle.

SPELL examples were fixed in `49edb66`. The browser's SDK lacks `spell.lib`, so
`test_spell.py` now runs an explicitly labelled SDK mode there and retains its
native mode under the original backend. Six Windows tests, four installed Linux
checks and six native procedures pass; see [the evidence](SPELL_EXAMPLES_QUALIFICATION.json).
The four former desktops received the corrected smoke example and additional
procedures in `demo/examples-v05-520a34af2e86` (also under `durable`). Unmodified
shipped root files were backed up and refreshed; edited files and windows were
preserved. Their named volumes remain after container removal. Rc4 groups all
procedures under `test_spell/` and adds `spell_menu.py` and the feature catalogue.

SPELL work continues in the sibling repository's
[current checkpoint](../../openbexi_spell_plugin/docs/LANGUAGE_CHECKPOINT.json)
and [plan through stable v1.0](../../openbexi_spell_plugin/docs/STABLE_RELEASE_PLAN.md).
The plugin checkpoint `e024bf2` is pushed to GitHub `master`: **483 qualified /
280 open** requirements. The accepted release remains `v0.4.0` for the GENERIC
simulator; full v0.5/v0.6 and stable v1.0 remain open.

The runtime passes all 33 native suites (1,646 raw checks), 55 focused prompt
controls, 14 child lifecycle checks and eight additional startup/recovery
controls. The latest local suite passes 538 tests plus 64 subtests. Two offline
native/driver rebuilds match. The new checkpoint adds only two bounded StartProc
return clauses and the documented page-79 SCDB existence method. Exact artifacts,
source scope and historical failures are linked in the checkpoint. Final
installed-host workflows still need qualification.

The published worktrees are `C:/obprompt_control` and `C:/obchild_start`.
Active work continues in `C:/obdatabase_scope`: a legacy octal-value correction
passes 24 native value/import checks, 20 user-database checks, two prompt controls
and seven evidence-verifier tests. Its declared diagnostic overlay is excluded
from the 483-row runtime; composed packaging and qualification remain required.
Retain both original failure traces. Continue all 763 language requirements,
then final packaging/host, operational, RC and stable gates. Keep existing
worktrees, named volumes and qualification artifacts. Current local task details
are in the plugin's `.qualification/RESUME_STABLE.json`.

## Current handoff after v0.4

IDE 0.3 durable plugin Execution and plugin 0.4 GENERIC DSS drivers/modes are
implemented and qualified. Read [PLUGIN_EXECUTION_SERVICE.md](PLUGIN_EXECUTION_SERVICE.md),
[PLUGIN_EXECUTION_QUALIFICATION.json](PLUGIN_EXECUTION_QUALIFICATION.json) and the
sibling plugin's `docs/DRIVER_RUNTIME.md` / `docs/DRIVER_QUALIFICATION.json` for
the exact final scope and artifacts. Continue next with plugin v0.5's 763-row
inventory, then v0.6 distribution. Full mission semantics, critical/scheduled
commands, vendor-specific drivers and shared native debugger inspection are not
promoted by the GENERIC simulator acceptance. Preserve all files described below.

The remaining text is the historical handoff and prerequisite progression;
its earlier statements that native Execution and v0.4 were open are superseded
by the qualification records above.

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
is a prerequisite for plugin v0.4. Only analysis had begun at the original project
switch; the partial implementation below is subsequent work. Plugin v0.4, v0.5 and
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

The user requested a Docker test environment before further v0.3 completion.
The browser desktop and isolated automated-test profile are described in
[DOCKER_TESTING.md](DOCKER_TESTING.md). Preserve its named workspace/preferences/
evidence volumes and the user's edits. Linux testing also corrected virtualenv
interpreter selection, debugpy process-group startup and exited-child accounting.
This is a testing milestone, not completion of any outstanding release gate.

An additional tested partial prerequisite is now implemented; read
[DURABLE_SERVICE.md](DURABLE_SERVICE.md) and
[DURABLE_QUALIFICATION.json](DURABLE_QUALIFICATION.json) before editing it.
It provides durable Development sessions, mutual TLS identities/revocation,
captured Git trees, bounded replay and separate audit, crash holds, stable logical
identity and offline reconciliation. It does not complete IDE v0.3 or any plugin
release. The package/release version remains 0.2.0 and no new release tag was
created. Continue from the explicit remaining gates in that document; do not
repeat the completed store/TLS/capture implementation or infer Execution approval.

An additional [offline Python Execution profile](EXECUTION_SERVICE.md) now
implements immutable source/runtime images, offline release approval/revocation,
isolated Linux container workers, private pipe control, read-only Execution
editors and recovery without replay. Its exact evidence is recorded in
[EXECUTION_QUALIFICATION.json](EXECUTION_QUALIFICATION.json). It is a tested
partial milestone; IDE v0.3 and plugin v0.4–v0.6 remain open. Do not repeat this
bounded release authority/container implementation or infer operational DSS
approval from its synthetic offline qualification approvals.

The [native shared Development milestone](NATIVE_SHARED_SERVICE.md) now connects
the original native host through a separate installed provider. Its source,
image, wheel, Qt and fresh-install evidence is in
[NATIVE_SHARED_QUALIFICATION.json](NATIVE_SHARED_QUALIFICATION.json). It adds
captured native source/image bindings, confirmed whole-container pause, native
prompts/results, descendant shutdown checks and owned-container recovery without
replay. The optional provider is `openbexi-spell-shared==0.4.0.dev1`; the accepted
local host image/wheel 0.3.0 remain unchanged. This is a tested partial milestone.

Finish and qualify the neutral IDE's durable collaborative service by extending
the bounded Execution profile to approved native runtime and operational effects.
Retain the implemented identity/TLS, revocation, bounded durable events, captured
Git sources, crash recovery and audited controller handoff. Preserve one fenced, leased
controller, configurable execution slots, logical-procedure admission across
versions/contexts, and uncertain-effect holds without automatic replay.

Inspect the preserved legacy `backend/procedure_identity.py`,
`backend/execution_locks.py`, `backend/executor_release.py` and their tests before
migrating their reusable rules and dependencies. Keep SPELL imports and domain
services out of the neutral IDE core. The default ephemeral shared worker still
uses the bounded v0.1 SPELL adapter; durable shared SPELL now requires the optional
native shared provider and rejects missing providers rather than falling back.
Native shared debugger inspection and approved native Execution remain open.

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

The initial API deletion attempts returned HTTP 403 because the saved Git
credential lacked `delete_repo` scope; `deletion-attempt.json` retains that
earlier result. The user then deleted both repositories from their GitHub
account. Authenticated verification on 2026-10-11 returned HTTP 404 for both old
names and HTTP 200 for both new repositories, whose default branch is `master`.
GitHub retirement is complete; no further deletion attempt is needed.

The old local directory, legacy workspace and retirement backups remain on
disk. Deletion of the two GitHub repositories does not authorize removal of
`C:/projects/openbexi_spell`; preserve it until the user confirms local removal.
It is safe to close the old IntelliJ project and resume from the existing
`C:/projects/openbexi_ide` directory, with the sibling plugin directory retained.

## Restart instruction

> Read docs/RESUME_V04.md and the linked current release records. Continue the
> IDE 1.0.0rc4 candidate's pending fresh-Windows check (13 browser checks passed), and the
> sibling plugin's release sequence through stable v1.0. Preserve the
> qualified console fix, immutable candidate evidence, old local project and
> archives. Ask before removing C:/projects/openbexi_spell. Test, update
> documentation and commit each phase; promote releases only after their gates pass.
