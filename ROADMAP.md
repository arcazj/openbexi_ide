# openbexi_ide roadmap

## Current release candidate — IDE 1.2.0rc1

Delivered the SPELL GUI User Manual-inspired procedure table, current-line
highlighting, procedure history and embedded prompts in local Run and Debug.
The implementation and exact validation scope are recorded in
[Procedure workspace](docs/PROCEDURE_WORKSPACE.md). The sibling plugin's v0.6
packaging and release qualification resumed at the user's explicit request on
2026-10-19; see [the current handoff](docs/RESUME_V04.md).
The [1.2.0rc1 release](docs/IDE_1_2_0_RC1_RELEASE.md) packages this GUI update;
stable promotion remains pending the recorded release checks and open issues.
Earlier milestone sections below retain their historical candidate status;
the published IDE 1.0 release record and current workspace evidence supersede
those older handoff statements.

## v0.1 — standalone IDE and collaborative CLI

Reuse the tested desktop editor/runtime/debugger. Establish a fresh independent
Git repository, packaging and current documentation. Add headless local Python
and optional SPELL runs; authenticated Development sessions, real shared output/
stack snapshots, one fenced controller, configurable parallel slots, paused FIFO
queue, explicit handoff, lease expiry and owned process cleanup. Qualification
is Windows x64 / CPython 3.13. This bounded v0.1 phase is complete;
see [qualification](docs/QUALIFICATION.md) and its source/package manifest.

## v0.2 — desktop shared sessions

Connect desktop widgets to the same session API. Show developers, queues,
controller ownership, live stacks/locals and selected output. Add controller
claim/release, pause/resume/stop/input, explicit Python/SPELL submission, graceful
disconnect, slot configuration and safe connection-loss handling. Qualify real
desktop/CLI peers and actual binary DSS effects before committing this phase.
This bounded v0.2 phase is complete on Windows x64 / CPython 3.13; see the
source tests, installed-package checks and captures in the current qualification.

Completion/navigation, a shared DAP debugger, interactive SPELL prompt handling,
plugin install/uninstall UI and Windows application packaging remain separate
future gates. Shared v0.2 stacks are read-only inspection; local Debug keeps its
existing real debugpy backend. Native/subprocess pauses remain cooperative.

## v0.3 — durable collaborative service

Add explicit remote identity/TLS, connection revocation, durable bounded events,
source/dependency capture, crash recovery, audited handoff and clear disconnect
behaviour. Preserve exactly Development, read-only Monitoring and approved
Execution. Operational admission uses one active logical procedure across
versions/contexts, leases/fencing and holds on uncertain external effects.

Complete for the recorded single-authority Windows x64 / Linux Docker profiles.
The final [plugin Execution milestone](docs/PLUGIN_EXECUTION_SERVICE.md) extends
the earlier slices below with immutable approved native runtimes, private
service-owned effects, current-authority checks, original DSS driver integration,
revocation and recovery. [Exact final evidence](docs/PLUGIN_EXECUTION_QUALIFICATION.json)
records artifacts and tests. Supplier audits and independent rebuilds, distributed
authorities and real-mission operational approval remain later product gates.
The following paragraphs record the historical sequence of partial milestones.

The [durable Development prerequisite](docs/DURABLE_SERVICE.md) now implements
certificate identities/TLS, revocation, bounded durable output, separate control
audit, committed Git captures, restart holds, logical alias reservations and
offline reconciliation. This is a partial milestone: operational Execution isolation,
full dependency provenance and native shared-runtime/effect integration still
gate v0.3. Plugin v0.4 must not be promoted from this prerequisite evidence.

The subsequent [offline Python Execution milestone](docs/EXECUTION_SERVICE.md)
adds image-bound source/runtime identity, offline approval/revocation, isolated
Linux workers, private pipe control, read-only Execution editors and owned
container recovery. Its real-container, Qt and installed-wheel evidence is in
[Execution qualification](docs/EXECUTION_QUALIFICATION.json). This satisfies the
bounded offline Python approval/isolation profile only. Native shared SPELL,
operational effect receipts and full runtime supply-chain provenance remain open.

The [native shared Development milestone](docs/NATIVE_SHARED_SERVICE.md) now
connects the original native host through an optional installed provider. It
retains captured source/image bindings, verifies whole-container pause before
slot reuse, supports prompts/results and fences restart without replay. This
completes the bounded native shared Development slice; shared native debugger
inspection, approved native Execution, original DSS effects and full provenance
remain open. See [its evidence](docs/NATIVE_SHARED_QUALIFICATION.json).

## v0.4 — usability and examples

Candidate implementation is qualified in [v0.4 evidence](docs/IDE_V04_USABILITY.md).
Add Python completion, definition and symbol navigation, and finish
the deep Python, graphics and explicit original SPELL examples. Console history
must stay readable while output arrives, with an explicit return to the latest
output. Preserve edits and project files when publishing examples.

Acceptance requires installed desktop Python workflows, completion/navigation
checks, close/shutdown checks, and actual X-button and mouse-wheel operation at
the noVNC desktop. The existing examples and console prerequisite evidence is in
[the current progress record](docs/V05_PROGRESS.md). Live noVNC verification is
still open; an HTTP health check or offscreen Qt test does not close that gate.

## v0.5 — collaborative debugging

The candidate connects the existing debugpy/DAP foundation to shared
Development sessions: shared breakpoints, threads, stack and variable views,
controller stepping, prompt handling, and runtime plugin installation/removal UI.
Use the same fenced controller lease and procedure/slot admission rules as Run.
Monitoring stays read-only and approved Execution stays immutable.
The implemented shared debugger is Python/debugpy; shared native SPELL DAP is
explicitly unavailable. Its local native debugger remains qualified separately.

Acceptance requires actual two-client debugging, handoff and stale-command
rejection, safe disconnect/lease expiry, explicit recovery/resume, prompt
handling, optional-plugin lifecycle, and ordinary Python after plugin removal.
The earlier live noVNC gate still prevents final release promotion.

## v0.6 — installable distribution

The v0.6.0rc1 candidate passed the recorded installation lifecycle and two
identical Windows ZIP builds; see [distribution evidence](docs/IDE_V06_DISTRIBUTION.md).
Final acceptance still requires the fresh Windows environment and live browser
gates below. Produce a Windows installation artifact with locked
dependencies, reproducible source/package identities, clean installation,
upgrade and removal. Preserve user projects, settings and saved examples across
upgrade/removal. Publish the supported platform/runtime matrix and installation
instructions.

Acceptance requires fresh installed artifacts, reproducibility and integrity
checks, earlier-release upgrades, removal, and installed Python/SPELL Run/Debug
workflows on the declared platforms. This project's release numbers are
independent of the sibling SPELL plugin's v0.5/v0.6 milestones.

## v0.7 — service limits and resilience

Implemented and qualified in the [v0.7 candidate](docs/IDE_V07_RESILIENCE.md).

Bound concurrent HTTP handlers, reject overload without allocating more worker
threads, and recover capacity when slow clients disconnect. Qualify malformed
requests, identity revocation, lease expiry, output backpressure and owned child
cleanup on Windows x64 and Linux Docker. Existing execution fencing remains the
authority for admitting procedures.

## v0.8 — diagnostics and recovery operations

Implemented and qualified in the [v0.8 candidate](docs/IDE_V08_DIAGNOSTICS.md).

Provide a read-only CLI diagnostic report for the installed interpreter and
optional backend inventory. Reports must avoid credentials, environment values,
project contents and user paths. Document stopped-service backups, preservation
of historical authority evidence, explicit reconciliation and rollback under a
new authority identity. Restoring a backup
must never imply that an uncertain external effect is safe to repeat.

## v0.9 — release evidence and upgrade readiness

Implemented and qualified in the [v0.9 candidate](docs/IDE_V09_RELEASE.md).

Bind the supported-platform matrix, candidate artifacts and test reports in a
machine-checked release dossier. Verify hashes, required evidence and open gates;
missing or failed evidence prevents release acceptance. Exercise installation,
upgrade, removal and ordinary Python after optional-plugin removal.

## v1.0 — supported Windows and Docker IDE

The [v1.0.0rc3 candidate](docs/IDE_V1_RELEASE.md) passes the recorded Windows,
Linux and installed upgrade/removal checks. Its [release dossier](docs/IDE_RELEASE_DOSSIER.json)
still reports the live-browser and fresh-Windows gates as open.

Promote only after the earlier milestone gates pass for one selected source and
artifact set, including actual noVNC window/console input and wheel interaction,
and a fresh Windows installation environment. Publish installation, operation,
recovery and known-limit documentation. The initial supported scope is Python
editing, local/shared debugging and optional runtime plugins on Windows x64 and
Linux x86_64 Docker. Full native SPELL language conformance and other IDE-host
compatibility retain their separate sibling-plugin acceptance records.

## Plugin and product acceptance

The optional local runtime extension contract is implemented and covered by 46
regression tests. It adds installed backend discovery, local CLI selection,
Run/Debug integration, bounded shutdown and backend prompts. See
[runtime backends](docs/RUNTIME_BACKENDS.md). Installed SPELL host acceptance
is complete at sibling plugin v0.3.0; this IDE retains its independent versions.

Qualify the original-source SPELL library against this host and the actual
IntelliJ/PyCharm hosts in the sibling plugin project. Complete OS/platform,
security/capacity, backup/upgrade and independent conformance gates before a full
product compatibility or operational acceptance claim. Commit each tested phase.

Coordinate these gates with openbexi_spell_plugin v0.2 through v0.6: original
native runtime, real host plugins, drivers/modes, full conformance, then
distribution/compatibility. Each project retains independent version numbers.
The plugin's v0.6 release requires actual installed-host workflow evidence from
this IDE; it does not automatically advance this project's release number.
