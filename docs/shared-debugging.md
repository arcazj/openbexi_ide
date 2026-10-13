# Shared Development debugging

The session service owns one standard debugpy DAP connection per debug procedure.
Install the pinned `debugpy==1.8.22` in the service's CPython 3.13 interpreter.
The runtime stays independent of Qt. Execution releases reject debugging;
Monitoring members and developers without the current controller cannot send
debugger requests, evaluate expressions, edit variables, or supply input.
The optional native SPELL provider currently has no qualified shared DAP
contract. Its shared debug submission is rejected before admission, with an
explicit unavailable capability. Local plugin debugging remains separate.

Submit using the existing `POST /run` endpoint:

```json
{"epoch":1,"script":"main.py","language":"python","debug":true,
 "stop_on_entry":true,"breakpoints":{"main.py":[12,18]}}
```

Paths are relative to the procedure project. Durable procedures resolve them
against the captured Git tree, including dependencies, rather than a changed
worktree. The trusted isolated Python bootstrap adds only the captured project
and script directory to Python's import path. Its DAP exclusion rule preserves
entry stops in user source.

`GET /session` includes `debug_capabilities` and each procedure's cached `debug`
object. Its fields are `enabled`, `backend`, `state`, `reason`, `revision`,
`thread_id`, `all_threads_stopped`, `threads`, `stack_frames`, `stacks`, `scopes`,
`variables`, `breakpoints`, `capabilities`, and `error`. Stack maps use string
thread IDs; scope maps use string frame IDs; variable maps use string DAP
variablesReference values. Shared source paths remain project-relative. Cached
views are available to every authenticated peer without a live adapter request.

States are `queued`, `starting`, `running`, `pausing`, `paused`, `evaluating`,
`terminated`, or `unavailable`. A procedure may remain PAUSING even after a DAP
stop if an owned child process is still running. Only an actual
`allThreadsStopped` event plus a settled child-process inventory releases its
execution slot. A queued continue/step remains stopped until a slot is granted.

The controller sends `POST /debug` with the procedure ID, current epoch, latest
snapshot revision, standard DAP command, and arguments:

```json
{"epoch":1,"procedure":"procedure-id","revision":4,"command":"evaluate",
 "arguments":{"frameId":2,"expression":"number + 1","context":"watch"}}
```

Supported commands are `threads`, `stackTrace`, `scopes`, `variables`,
`exceptionInfo`, `setBreakpoints`, `pause`, `continue`, `next`, `stepIn`, `stepOut`,
`evaluate`, `setVariable`, and `setExpression`. Only line breakpoints are
accepted. Unknown commands/arguments, paths outside the captured project,
unavailable capabilities, and old frame/variable handles are rejected. Responses
contain `body` and `debug`; continue/step/pause return `accepted` and `debug`.

Resuming, stepping, editing/evaluating, handoff, disconnect, and lease expiry
invalidate stopped views. Outstanding responses must match both controller
epoch and snapshot revision. Handoff/disconnect/expiry request a real DAP pause;
claiming control never resumes work. Expressions can execute Python, so
evaluation and edits reserve a real execution slot. If control expires while an
expression is running, the slot remains reserved until the adapter confirms its
completion; the old response cannot update the new controller's view.

Unstarted debug procedures retain their options across durable service restart
and remain paused until explicitly resumed. Previously launched procedures
retain the existing recovery hold; frame IDs and adapter connections are never
restored as live authority. Normal completion and stop reap the owned adapter,
launcher, debuggee, and descendants. This is the existing trusted Development
process boundary, not an untrusted-code sandbox.

CLI examples:

```text
openbexi --connection alice.json submit main.py --debug --breakpoints '{"main.py":[12]}'
openbexi --connection alice.json status
openbexi --connection alice.json debug PROCEDURE next --revision 4 --arguments '{"threadId":1}'
```

The desktop client provides asynchronous `submit(...)` and
`debug_command(procedure, command, arguments=None, revision=None)` methods.
Its `debug_result` signal carries the originating procedure, command, arguments,
epoch, revision, response body, and updated debug snapshot. The GUI must discard
results whose procedure or view revision no longer matches its selection.

## Desktop use

Open the session folder, join as Developer, claim control, set gutter breakpoints
and choose **Debug**. Without breakpoints the session stops on entry. Select the
procedure in Session and use Debugger's Continue/Pause/Step controls. Selecting
threads/frames inspects scopes and bounded variables. Evaluate an expression in
the text field; double-click a variable's value to edit it. Monitors receive
cached views and cannot issue DAP requests or edits. Frame/variable callbacks
are fenced by procedure, epoch, revision and view generation. Cached callbacks
and snapshot rendering are queued outside Qt tree model notifications.

The asynchronous transport renews controller leases on a separate bounded
request while a debugger operation is in flight. Turning **Keep control** off
retains ordinary expiry and explicit recovery/resume behavior.

Selecting a source frame opens a read-only copy using authenticated
`POST /source` (`procedure`, relative Python `path`). It reads at most 2 MB,
rejects traversal and invalid encodings, and checks durable manifest/file hashes.
Captured copies remain accurate after worktree edits; ordinary Development
copies describe the current procedure project without claiming immutability.
Monitors may read source but cannot modify it through this endpoint.

**Run > Runtime Plugins** inventories optional entry-point packages in the
selected interpreter and installs local wheels without fetching dependencies.
Removal protects IDE, interpreter tooling and desktop/debugger dependencies.
Operations run in an owned process; closing the dialog terminates that process.
Plugin management is available in the local workspace. Shared service providers
must be installed in the service interpreter separately.

`tests/test_shared_debug.py` exercises real debugpy over authenticated HTTP:
two controllers and a monitor, breakpoints and relative captured sources,
thread/stack/locals views, evaluation/editing/stepping/input, running control
handoff/disconnect/expiry, stale handles, long evaluation fencing, occupied
slots and owned child processes, startup cancellation, durable queued restart,
missing debugpy, and unavailable native SPELL debugging.
`tests/test_shared_debug_ui.py` adds actual Qt controller/monitor workflows,
variable editing, stepping, handoff, captured-source tamper rejection, and lease
renewal during a real delayed evaluation.
