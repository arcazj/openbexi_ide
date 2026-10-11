# openbexi_ide engineering master prompt

Build a domain-neutral CPython 3.13 desktop IDE and CLI. Keep the Python runtime
independent of Qt and SPELL. Reuse the existing tested launch, owned process-tree
and real debugpy/DAP foundation; do not replace mature debugger/tooling APIs with
an invented implementation. Version starts at 0.1.0 after the repository split.

Prioritize a beginner-friendly PyCharm-inspired, macOS-style desktop: subtle
colours, generous spacing, rounded surfaces, thin borders, restrained shadows,
system fonts, crisp icons and light/dark themes. Files left, editor centre,
output/debug below. Keep Open Folder, Run, Debug and Stop compact and obvious.

Provide a GUI-independent CLI for normal Python and explicitly selected installed
language plugins. Multiple developers connect to one session and inspect real
output and project stack state. Exactly one developer controls execution at a
time. A configurable slot count supports serial or bounded parallel procedures;
queued procedures remain paused until granted a token. A running procedure must
confirm actual pause/cleanup before its slot is reused. Reject duplicate active
logical procedures. Handoff and lease expiry fence stale commands and require
explicit resume; never silently resume on reconnect or transfer.

Keep exactly three fundamental operating modes: Development (mutable local
Run/Debug under the user's OS permissions), Monitoring (read-only, no commands,
input, prompt answers or evaluation), and Execution (approved immutable sources,
server authority and qualified operational isolation). Label bounded Development
sessions accurately; do not infer operational approval from a local Run.

SPELL belongs in `openbexi_spell_plugin`, installed into the selected interpreter.
Procedures import its symbols explicitly; no startup/builtins injection. The IDE
starts, runs and debugs ordinary Python without that plugin or DSS. Discover
capabilities honestly and fail clearly for unavailable/incompatible services.

Preserve atomic logical-procedure admission across operational versions/contexts,
controller leases/fencing, distinct Executor and DSS processes/endpoints,
uncertain-effect holds/no automatic replay, captured Git dependencies and immutable
approved release identities as future operational gates. DSS means Dynamic
Satellite Simulator; Monitoring is a separate read-only mode.

Keep original source/license provenance in the plugin project and historical
release evidence in the external migration archive. Current docs describe current
behaviour and explicit gaps. Test actual UI, runtime, debugger, multi-client and
installed-package behaviour; mocks/import success do not establish conformance.
Update docs, remove only demonstrated obsolete resources, and commit/tag each
completed local phase. Never rewrite a remote history without explicit scope.
