# Service resilience candidate

Each shared-session HTTP listener admits at most 32 concurrent handlers. Excess
connections close before a new worker thread is created. Both ordinary HTTP and
TLS use that same bound, and completed or disconnected handlers return their
capacity. The Python API accepts `max_handlers` from 1 to 256 for a deliberately
sized deployment; the desktop/service CLI uses 32.

Request bodies retain the existing 128 KiB limit and now reject JSON nesting
deeper than 32 levels. A parser recursion error also becomes a bounded client
error. The health endpoint remains available after malformed input is rejected.
The limit is per listener; it is not a guarantee of availability during sustained
overload. Controller leases and process fencing still fail closed when a client
cannot communicate.

Real-socket tests fill the handler capacity with partial requests, verify that an
additional connection does not create a handler, disconnect the clients, and
verify successful requests afterward. Integration checks cover real mutual TLS,
revocation, durable restart, output/input backpressure, shared debugging and
lease expiry. A short-lease expiry test now explicitly renews during cold worker
startup, then stops renewal to exercise the intended expiry event.

This is a candidate milestone. Earlier browser interaction and fresh Windows
environment acceptance remain independent open release gates.
