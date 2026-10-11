# Optional runtime backends (unreleased)

Local Run, Debug and CLI execution discover optional packages in the selected
CPython interpreter. Ordinary Python continues to use the isolated worker and
debugpy. The core does not import a plugin into its GUI process.

A package registers an `openbexi.backends.v1` entry point. Its name is the backend
ID. Loading and calling that entry point, in an isolated interpreter probe,
must return a JSON-compatible descriptor:

```json
{
  "api": 1,
  "id": "example",
  "label": "Example runtime",
  "runner": "example_backend.runner",
  "debugAdapter": "example_backend.dap",
  "gracefulStopMilliseconds": 10000,
  "supportsStepOut": false
}
```

Both commands are Python modules, invoked without a shell and with isolated
interpreter flags. The runner receives `--project FOLDER --program FILE -- ARGS`.
The debugger receives `--project FOLDER` and speaks DAP over standard input and
output. Its launch request includes `project`, `program`, `args`, `type` and
`stopOnEntry`. Protocol output belongs on stdout; diagnostics belong on stderr.
Closing the runner's stdin requests graceful cancellation. Debug sends the DAP
disconnect request. The host enforces the descriptor's bounded shutdown grace.
Desktop Run sets `OPENBEXI_HOST_MANAGED=1`, allowing a runner to distinguish
window-owned cancellation from a headless invocation with closed stdin.
`supportsStepOut` defaults to true; false disables that desktop action.

An adapter can emit `openbexi/inputRequest` with `text`, `choices` and
`answerFormat` to enable the desktop input field. The reply is an
`openbexi/input` request with a `text` argument. Prompt semantics belong to the
backend; the neutral host displays and forwards them.

Use Run → Reload Runtime Plugins after installing or removing a package. The
toolbar lists local backends separately from the v0.2 server's shared-session
runtime choices. CLI selection is `openbexi run FILE --language BACKEND_ID`.
Malformed optional descriptors are reported without preventing ordinary Python
execution. Removing a backend removes its local selection on the next refresh.

The existing bounded shared-session adapter remains on its v0.2 protocol until
the durable-service migration. This extension milestone alone does not complete
the independent IDE v0.3 release.

The extension milestone passed 46 runtime, debugger, desktop, shared-desktop
and backend-discovery tests on Windows x64 / CPython 3.13.15. The installed
fixture check discovers a real entry-point distribution, rejects malformed
metadata, removes the backend and runs ordinary Python without debugpy.
Original SPELL desktop acceptance remains tracked in the sibling plugin
project; its native output-flush regression is still under investigation.
