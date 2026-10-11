# openbexi_ide roadmap

## v0.1 — standalone IDE and collaborative CLI

Reuse the tested desktop editor/runtime/debugger. Establish a fresh independent
Git repository, packaging and current documentation. Add headless local Python
and optional SPELL runs; authenticated Development sessions, real shared output/
stack snapshots, one fenced controller, configurable parallel slots, paused FIFO
queue, explicit handoff, lease expiry and owned process cleanup. Qualification
is Windows x64 / CPython 3.13. This bounded v0.1 phase is complete;
see [qualification](docs/QUALIFICATION.md) and its source/package manifest.

## v0.2 — richer IDE and session controls

Connect desktop widgets to the same session API. Add completion and navigation,
clear session/queue/owner views, debugger integration for shared sessions, explicit
interactive prompt handling and verified plugin install/uninstall UI. Improve
pause responsiveness for supported blocking operations without claiming arbitrary
native/subprocess suspension. Add Windows packaging and platform-specific gates.

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
