# IDE and session architecture

`openbexi_ide` contains Qt widgets. `openbexi_runtime` contains GUI-independent
launch/process ownership, DAP framing, the CLI and the shared-session server.
The core imports no SPELL package at startup. GUI dependencies are an optional
desktop extra; a headless wheel uses the standard library.

The v0.2 desktop uses a bounded background HTTP queue and queued Qt signals; no
network request runs on the GUI thread. It shares CLI authentication, fencing,
slots, cooperative pauses and source admission. Desktop identities are issued
independently per join and held only in memory. Disconnect revokes the member's
credential atomically, releases owned control and pauses session work. A request
authenticated before revocation cannot reacquire mutation authority afterward.
Late join responses are revoked when the user cancels a pending connection.

Only a current controller changes the slot limit. Reducing it below occupied
tokens is rejected; acknowledged pauses/finished workers make room. The GUI
never guesses that PAUSING is quiescent. Service failures disable mutations and
clear the desktop's lease authority; recovery requires explicit claim/resume.
Shared live inspection has no expression evaluation or remote source writes.
The selected local folder must match the session project for desktop Run.

One authenticated controller identity and one monotonic fencing epoch govern
session mutations. Monitoring credentials cannot claim, renew, submit, send input,
pause, resume or stop. Names are display labels; authority belongs to independently
issued credentials and client IDs. An expired/released lease fences old commands
and requests a pause of every active procedure, including queued work. Claiming
never automatically resumes old work.

Execution slots are separate from controller ownership. The server grants at most
`max_parallel` slots and dispatches waiting submissions in FIFO order. A logical
project-relative procedure cannot have two active instances in a session. Paths
resolve inside the opened project, source SHA-256 is checked on worker startup,
and the selected interpreter must be CPython 3.13. This is mutable Development;
the optional durable profile captures committed Git trees and their local
dependencies. Approved immutable Execution bundles and isolation remain later work.

Workers use isolated interpreters, clean Python environment variables, owned
process trees, explicit project paths and UTF-8 streams. Windows Job ownership
handles the venv redirector and actual interpreter separately. Stop/server death
ends owned descendants. Pause is cooperative at Python trace checkpoints; native
calls and owned child processes keep the token until real quiescence. Unsupported
platform process-count evidence also keeps the token rather than assuming pause.

Snapshots sample live threads even during blocked input/native calls. They contain
real project stack frames and bounded primitive local values; library-only threads
remain visible with no project frames and keep their execution token until quiescent.
Object values show their type without calling user `repr`, properties or an
expression evaluator. Monitors never evaluate expressions. Output uses incremental
UTF-8 decoding; 2,048 bounded events are retained and cursor gaps are reported.
Input is delivered by a bounded queue outside the control lock, so a script that
does not read stdin cannot block controller renewal or Stop. Active procedures
are capped at 128; completed procedure records are also bounded.
Live stacks and credentials are memory-only. The default ephemeral service starts
a new session identity after restart. The optional durable profile preserves its
session identity, event cursor, logical reservations, procedure fences and captured
source identities. It revokes credentials and restores started work only as held
recovery records, never as automatically replayed processes. See
[durable Development](DURABLE_SERVICE.md) for its transaction, TLS, recovery and
offline reconciliation boundaries and the remaining v0.3 gates.

SPELL is selected explicitly with `--language spell`, checked in the worker
interpreter and activated inside that worker. Procedures still import SPELL
symbols explicitly. The plugin owns DSS/driver services; the IDE core owns no
satellite concepts. The first plugin profile is bounded local testing, not full
legacy SPELL language or JetBrains host qualification.
