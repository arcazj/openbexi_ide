# Procedure execution workspace

This Development workspace follows the SPELL GUI User Manual 2.4.4 procedure
presentation: sections 3.2.1 (tabular view), 3.2.6 (prompt inputs) and 5.4
(procedure input). IDE release candidate version is `1.2.0rc1`; the companion native host
package is `0.3.1.dev3`. SPELL v0.6 remains paused at the user's request.

The [release notes](IDE_1_2_0_RC1_RELEASE.md) describe the candidate artifacts.
The development qualification below remains bound to its original `1.2.0.dev1`
build; the release candidate has a separate dossier and retained checks.

## Using the desktop

The updated local desktop is available at
<http://127.0.0.1:6080/vnc.html?autoconnect=1&resize=remote>. The SPELL menu is
open there. The existing workspace and preferences volumes were preserved;
the previous container is retained, stopped, as
`openbexi-ide-pre-workspace-20261017`. The Windows project's `.venv` also has
the matching IDE and host wheels installed.

Select the installed SPELL runtime and Run or Debug a procedure. The
**Procedures** tab opens automatically. Its history records the procedure,
local start time, Run/Debug mode and final result. Selecting a previous run
shows that run's captured code and output. History retains up to 100 runs
for the current IDE session; native artifacts remain under `.openbexi/runs`.

**Code & results** shows line number, procedure source, native timestamp,
item, value and result. The current line is highlighted as execution proceeds.
**Follow current line** follows both the location and visible child source;
turn it off to inspect another source or scroll independently. Double-click
a row to navigate to its editor line. Native source snapshots arrive from
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
