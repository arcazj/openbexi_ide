# openbexi_ide roadmap

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

## Later — plugin and product acceptance

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
