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

## Later — plugin and product acceptance

Qualify the original-source SPELL library against this host and the actual
IntelliJ/PyCharm hosts in the sibling plugin project. Complete OS/platform,
security/capacity, backup/upgrade and independent conformance gates before a full
product compatibility or operational acceptance claim. Commit each tested phase.
