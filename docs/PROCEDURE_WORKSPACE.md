# Procedure execution workspace

This Development workspace follows the SPELL GUI User Manual 2.4.4 procedure
presentation: sections 3.2.1 (tabular view), 3.2.6 (prompt inputs) and 5.4
(procedure input). IDE `1.1.1` uses the published SPELL `0.6.0` host and native
runtime. See [the current Docker setup](IDE_SPELL_V06.md). Historical v1.1.0
qualification and its original companion versions remain recorded separately.

## v1.1 development behavior

In SPELL mode, the Python editor, console and debugger panes disappear. Starting
a procedure also hides the project pane. The menu, execution controls and
procedure/history strip remain visible. Leaving SPELL mode restores the Qt
layout; JetBrains provides **Return to editor**. Completed results stay visible.

Procedure-state colors appear in the state badge. Code rows remain white in
both themes. A soft blue highlight follows only the current executing line and
clears after completion. Result cells independently use green for success, red
for failure and amber for warnings or work in progress. An unknown result is
never shown as success. Selecting a row preserves these execution/result colors.
Double-click a Qt result for **Latest information**, **History** or **Full**.
The first two merge item updates; Full preserves the raw notifications. EX uses
the native statement count when supplied. History is paged from SQLite, and
**Export As-Run** writes a JSON-lines record with its captured source.

The local procedure service owns the native adapter. Desktop and JetBrains DAP
bridges connect to it; **Web workspace** opens its native browser interface.
One client controls each procedure. Other clients monitor it, with prompt inputs
and execution actions disabled. Release control while paused or awaiting a prompt,
then take control in the other client. The server rejects stale prompt answers
and duplicate submissions. Connection loss requests a native pause and does not
fabricate a PAUSED state. A server restart retains records but never replays or
resumes a stored process automatically.

Local service credentials and authoritative records are stored under the user's
`OpenBEXI/procedure-services` directory, outside the project snapshot. Qt also
stores its presentation records under `.openbexi/runs/presentation.sqlite3`.
The service supports one running procedure, with up to eight live container
instances. The packaged Linux native backend currently supports one live instance.
Qt, IntelliJ and PyCharm reconnect to that service and restore live instances and
recent history. Selecting a tab does not claim control. Closing a native view
detaches its connection; a lost controller requests a native pause. In Qt, use
**Open procedure** to create another instance while the existing ones are paused.
The desktop qualification covers two paused instances of the same source, closing
the view, reopening it, explicit control claim, Continue and independent Abort.

Local access binds to loopback. Remote browser access requires the same mutual-TLS
certificate identity policy as the existing durable session service:

```text
python -m openbexi_runtime.procedure_service --project PROJECT --host 0.0.0.0 --port 8443 --public-host SERVER_NAME --tls-cert server.pem --tls-key server.key --client-ca ca.pem --identities identities.json
```

The identity file uses `session_identity.CertificateIdentities` format: schema 1,
certificate SHA-256 fingerprints mapped to a name and `developer` or `monitor`.
The browser must present an enrolled client certificate and a workspace credential.
A monitor certificate cannot become a controller by using an operator credential.
Role changes and certificate revocations are checked on subsequent requests.
This Development service does not replace approved Execution admission or fencing.

The native adapter supports Run, Pause, Step, Step over, Abort, breakpoints and
current-frame variable inspection/editing. Skip, Goto, Recover, Run Until, By Step,
scheduling, Shell and TC confirmation are unavailable and are not enabled controls.

The latest qualification artifacts are under `F:\openbexi-builds\ide-v1.1` on the
development machine. Full Windows tests, Windows/Linux native workflows, actual
IntelliJ/PyCharm workflows, and browser control/monitor checks have run there.
The [v1.1 acceptance record](IDE_1_1_ACCEPTANCE.md) tracks packaging, migration and
the independent clean-Windows installation gate. The records below document
the older candidate, not qualification of every new v1.1 feature.

The [1.1 release notes](IDE_1_1_RELEASE.md) describe the current artifacts.
The development qualification below remains bound to its original `1.2.0.dev1`
build; the release candidate has a separate dossier and retained checks.

## Previous candidate: desktop installation and qualification

The updated local desktop is available at
<http://127.0.0.1:6080/vnc.html?autoconnect=1&resize=remote>. The SPELL menu is
open there. The existing workspace and preferences volumes were preserved;
the previous container is retained, stopped, as
`openbexi-ide-pre-workspace-20261017`. The Windows project's `.venv` also has
the matching IDE and host wheels installed.

Select the installed SPELL runtime and Run or Debug a procedure. The
**Procedures** tab opens automatically. Its history records the procedure,
local start time, Run/Debug mode and final result. Selecting a previous run
shows that run's captured code and output. The view lists up to 100 recent runs;
saved records and native artifacts remain under `.openbexi/runs`.

**Code & results** shows line number, procedure source, native timestamp,
item, value and result. The current line is highlighted as execution proceeds.
**Follow current line** follows both the location and visible child source;
turn it off to inspect another source or scroll independently. Double-click
a row for item information. Native source snapshots arrive from
the actual run, including visible child procedures. Empty result cells mean
the runtime has not reported a result; reaching a line does not imply success.

Prompts appear below the table with choice buttons or text, numeric, date and
masked-password fields. **Commit** sends one answer to the identified waiting
prompt; **Reset** clears the selection or input. **Abort procedure** stops the
owning run. The panel identifies child prompts. Native validation, timeout,
defaults and reminders remain authoritative. Expired prompts and late replies
cannot answer or dismiss a later prompt. Ordinary Python continues to use
its existing worker and debugpy.

The desktop image includes the matching runtime and disposable teaching DSS.
For native Windows source launches, install the IDE and companion host wheels
in the selected interpreter. The host's development default image is
`openbexi-spell-host:0.3.1-dev3`; `OPENBEXI_SPELL_IMAGE` can select an explicit
compatible image. The native runtime executes in Linux Docker on Windows.

## IntelliJ

**Tools > SPELL > Procedure Workspace** opens the same style of code/results
and embedded-prompt presentation in the existing `0.3.1-workspace.1` candidate.
Use **Tools > SPELL > Procedures > Run File with SPELL** or **Debug File with
SPELL**. The installed JAR and the running IntelliJ startup log were checked
against the retained candidate; the old statement that this GUI was not yet
installed was superseded on 2026-10-17. Its configured workspace image remains
available. The sibling repository's `docs/JETBRAINS_WORKSPACE_QUALIFICATION.json`
records the exact candidate and host checks.

## Validation and limits

[The qualification manifest](PROCEDURE_WORKSPACE_QUALIFICATION.json) binds the
tested source, images, reports and screenshots. Checks cover actual native
Run/Debug, breakpoints, current-line/item results, Yes/No/text/numeric/list
prompts, child procedures, history, Stop/rerun and ordinary Python afterward.
Both Windows Qt and installed Linux X11 workflows are exercised, alongside the
actual IntelliJ candidate. Rendered screenshots are retained with the evidence.

Actual captures: [Windows prompt](evidence/procedure-workspace/windows/run-prompt.png),
[dark prompt](evidence/procedure-workspace/windows/run-prompt-dark.png),
[tabular results](evidence/procedure-workspace/linux/run-results.png).
The desktop HTTP and native X11 paths were checked; a new browser-click
qualification was unavailable in this session.

This presentation is for local Development. Shared-session Monitoring and
approved Execution keep their existing controls and admission rules. It does
not add mission operational authority or claim full feature/visual equivalence
to the original Eclipse GUI. Date/password widgets retain backend validation;
the full native interactive workflow checks focus on the prompt types above.

Published language conformance evidence stays bound to its original source.
The legacy report tests intentionally reject the changed development adapter
hash; their recorded evidence is not rewritten to make this GUI candidate
appear requalified. Full language/distribution promotion is separate work.
The independent fresh-Windows OS installation gate remains open.
