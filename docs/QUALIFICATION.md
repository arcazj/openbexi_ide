# v0.1 qualification

Windows x64 / CPython 3.13.15. The migrated native desktop, neutral runtime and
real debugpy debugger passed their original 37 tests; the combined IDE/CLI suite
passed 53 tests with warnings treated as errors. The 39-topic Python reference
passed 260 checks and reported one optional Windows symbolic-link privilege
disposition (261 total checks/dispositions), without requesting administrator
access. Source-bound metrics and package hashes are in
[QUALIFICATION.json](QUALIFICATION.json). Source hashes use canonical Git index
bytes; local test reports and wheels remain in the ignored `.qualification/v0.1/`.

Session tests use actual isolated workers, HTTP clients, live Python stacks and
Windows Jobs. They cover independent developers, read-only monitors, atomic
controller acquisition, stale-command fencing, handoff/expiry, one/two execution
slots, FIFO queue/resume, duplicate logical-file rejection, changed queued source,
UTF-8/stdin, owned child cleanup, blocked input, library threads, input backpressure,
bounded locals and no user metaclass/property execution during inspection.

An installed-package check connects two developers and a monitor, observes a real
blocked stack, queues Python and SPELL, sends an actual binary DSS command, verifies
Unicode/input and exercises controller handoff. Core installation was also tested
before Qt or SPELL was installed. Optional desktop dependencies are installed now.

Both wheels were rebuilt twice with `SOURCE_DATE_EPOCH=1791590400` and matched
byte-for-byte. Re-run the installed integration after installing both wheels with
`python -I scripts/qualify_installed.py --output .qualification/v0.1`.
Native light/dark UI captures and actual Run/Debug/graphics open/close checks
passed. Local CLI runs also exercised the SPELL runner and the explicit desktop
adapter example against the working native DSS.

The native desktop is open. Current test services are the CLI at
`http://127.0.0.1:9010` and native DSS at `http://127.0.0.1:8086`; they are local
Development test services, not approved operational Execution. The default
connection in `.session/client.json` belongs to arcaz and has no controller token
until `openbexi claim`. The active session permits two parallel procedures.

The initial release does not claim durable recovery, direct LAN/TLS identity,
arbitrary native/subprocess suspension, shared desktop debugger sessions, full
SPELL compatibility or actual JetBrains plugin acceptance. Each has a roadmap gate.
