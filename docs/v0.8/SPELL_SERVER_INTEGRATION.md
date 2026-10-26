# SPELL v0.8 server connection

The **SPELL server** tab connects to the v0.8 certificate gateway. It is separate
from the existing **Session** tab and v0.7 runtime. Development version
`1.2.1.dev1` supports discovery, source catalogs, execution reservations,
observation, explicit control requests, accept/reject and controller rebind.
While connected, local Run and Debug are disabled and direct action calls are
rejected, preventing a server action from falling back to local execution.
Native run, pause, debugging, prompts and driver effects are not yet available
through this new tab. It must not be described as the qualified v0.8 runtime.

Prepare a private JSON connection file outside the project/source repository:

```json
{
  "url": "https://spell.example.net:9443",
  "fingerprint": "<64 lowercase hex gateway certificate SHA-256>",
  "ca": "private/ca.pem",
  "certificate": "private/alice.pem",
  "key": "private/alice.key"
}
```

Paths resolve relative to the connection file. Protect the key with operating
system file permissions. Choose **Connect to server**, then a Context. Read-only
users can inspect executions; control actions are disabled according to the
Context's current permissions. The Context independently authorizes every call.
A control request never grants control on its own. The current controller must
explicitly accept; the new controller then selects **Reconnect control** to
receive its own private capability. Other executions retain their controllers.

The client checks the CA, hostname and pinned gateway certificate before sending
requests. The gateway derives identity from the actual client TLS certificate;
clients cannot supply an identity header. The gateway and Listener use separate
service certificates, and the Context rechecks permissions. One fixed endpoint,
64 KiB messages, bounded timeouts and no automatic mutation retries are enforced.
Capabilities are memory-only and are never put in list rows, logs or files.

Select **Disconnect** to close logical controller connections. If a close fails,
the panel retains its original request key for a safe explicit retry. Closing the
window is transport detachment, not proof that the server closed the connection
or stopped a native process. Automatic heartbeat/WSS disconnect behavior remains
a pending v0.8 gate. The CLI `openbexi-spell-client --config connection.json`
provides read-only Context discovery; add `--context A --resource executions`.

## Qualification scope

14 new local client/desktop checks pass, including nonblocking window detach while a network operation is pending. A development detach fixture initially omitted the client controller-query method; its failed JUnit is retained separately. Real three-client TLS and handoff checks
are maintained in the plugin's `server/tests/test_ide_integration.py`; its CI pins
an exact IDE commit. Independent certificate identities are used for controller
Alice, controller Bob and an observer. GUI connection and observer button states
are exercised with the actual Qt panel and TLS services.

The local legacy regression attempt retained in `evidence/local-baseline-failed.xml.gz`
had **21 passes and 16 failures**, not a compatibility pass. This execution host's
PID namespace differs from its mounted procfs: `os.getpid()` returned 5 while
`/proc/self/stat` reported 27044. Existing ownership/bootstrap checks therefore
reject workers. No containment check was disabled. The hosted workflow reruns
the existing IDE suite on a normal Linux runner; only actual hosted results may
supersede this failed attempt. Native/driver, browser/WSS, deployment and full
v0.8 release qualification remain pending.
# Existing-execution controls in 1.2.1.dev2

The server panel now offers Run / Continue, Step, Pause, Abort and Close execution
when the authenticated Context advertises those commands through an explicitly
enabled Listener. Each operation uses the exact controller capability, epoch
and connection generation originally delivered to this client. An ambiguous
response is not retried, and queue admission is not reported as native completion.
Observers, other owners, fenced executions and missing controller proofs leave
the controls disabled. The backend independently enforces the same authority.

After an accepted native family handoff, B explicitly reconnects control while
the original family is paused, then requests Run. Acceptance does not silently
resume the family. The client drops A's proof when acceptance starts the barrier.
The main IDE's local Run/Debug fallback remains disabled while connected.

This development feature controls an existing host-provisioned execution. It
does not add public worker provisioning, debugger inspection/breakpoints,
browser/WSS, prompt widgets or Git collaboration. Exact paired native results
are recorded in the companion plugin; the historical evidence below retains
its original source identity and scope.

