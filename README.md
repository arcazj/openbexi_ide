# OpenBEXI IDE

**OpenBEXI IDE 1.2.0** integrates **SPELL v0.7** in the
`openbexi-ide-spell-v07` Docker desktop. Offline authority backup/restore retains
uncertain-effect holds, advances the controller epoch and revokes historical
Execution approvals. The driver admits effects only within durable journal
limits. See [setup and recovery](docs/IDE_SPELL_V07.md) and the
[qualification record](docs/IDE_SPELL_V07_QUALIFICATION.json).

Load the release image archive, then run `docker compose up -d --wait ide`.
Open `http://127.0.0.1:6080/vnc.html`. The default volumes preserve existing
projects and preferences. Download the matching components and checksums from
the [1.2.0 release](https://github.com/arcazj/openbexi_ide/releases/tag/v1.2.0).

The previous **OpenBEXI IDE 1.1.1** integrated **SPELL v0.6**. Its
[procedure workspace](docs/PROCEDURE_WORKSPACE.md) adds a server-owned native
SPELL executor, a browser control/monitor view, persistent records, the manual's
state badge, and an execution-only layout in Qt, IntelliJ and PyCharm.
Procedure rows stay white, with a soft highlight on the current line and colors
only in result cells. See [the current Docker setup and verification](docs/IDE_SPELL_V06.md).

Use the [1.1.1 setup guide](docs/IDE_SPELL_V06.md) for matching SPELL v0.6
components, Docker commands and offline builds. The
[1.1.0 release notes](docs/IDE_1_1_RELEASE.md) retain the previous release's scope.

Download the [1.1.1 Docker image, core wheel, components and checksums](https://github.com/arcazj/openbexi_ide/releases/tag/v1.1.1).
The previous [1.1.0 Windows offline ZIP](https://github.com/arcazj/openbexi_ide/releases/download/v1.1.0/OpenBEXI-IDE-1.1.0-windows-x64.zip)
remains available; this Docker-focused patch does not replace that bundle.
The Git tag is `v1.1.1`; the package version is `1.1.1`. The
[older stable 1.0](https://github.com/arcazj/openbexi_ide/releases/tag/1.0) remains
available as a historical download.

The previous Docker desktop uses `http://127.0.0.1:6080/vnc.html`. Load the 1.1.1
image archive, then start it with `docker compose up -d --wait ide`. It contains
all SPELL procedures under `test_spell/`, with a dedicated language-menu launcher.
The menu exercises available features and lists all 763 reference entries;
unsupported features are explicitly reported. See [the procedures](examples/test_spell/README.md).

The [1.0 release record](docs/IDE_1_0_0_RELEASE.md) retains its original checks
and limitations. Version 1.1 has separate artifact and fresh-Windows evidence.

The corrected [v0.5 Docker desktop](docs/IDE_V05_DOCKER.md) has its own launch
file, `compose.v05.yaml`. Typing a menu choice while the console output has
focus now reaches the script input field; Send restores focus for the next
answer. Linux shared debugging also tracks the debuggee's separate process
group before releasing a paused execution slot.

Shared Development **Debug** now uses real debugpy with shared breakpoints,
threads, stacks and variables. The controller can evaluate, edit variables and
step; monitors inspect cached views and read-only source copies. Durable source
views verify the captured tree rather than displaying changed worktree files.
**Run > Runtime Plugins** installs/removes optional local wheels in the selected
interpreter. See [shared debugging](docs/shared-debugging.md). Native SPELL uses
the separate [procedure workspace service](docs/PROCEDURE_WORKSPACE.md) for
execution ownership, debugging, prompts and browser monitoring.

The usability candidate adds **Ctrl+Space** Python name completion, **F12**
project definition navigation, and **Ctrl+Shift+O** searchable project symbols.
Analysis uses source syntax on a background worker and includes unsaved tabs.
Console history stays readable during new output; **Latest output** resumes
following the tail. The deep Python, interactive graphics and explicitly imported
original SPELL examples are included. See [v0.4 qualification](docs/IDE_V04_USABILITY.md).
Live noVNC X-button/mouse-wheel checks passed on rc3. The IDE releases follow their independent roadmap;
candidate commits do not promote the sibling plugin's conformance releases.

Current release artifacts and remaining work: [resume development](docs/RESUME_V04.md).

A standalone CPython 3.13 IDE and headless CLI. The desktop has a project tree,
tabbed editor, output and real debugpy debugger, with light/dark themes and a
compact Open Folder / Run / Debug / Stop toolbar. SPELL is an optional, separately
installed [plugin](https://github.com/arcazj/openbexi_spell_plugin).

The desktop and CLI now share the same Development session service. The Session
tab shows developers, controller ownership, serial/parallel queues, real live
Python stacks, bounded locals and per-procedure output.

Durable sessions also support [native shared SPELL Development](docs/NATIVE_SHARED_SERVICE.md)
through an optional provider: captured Git sources, whole-container pause,
fenced handoff, native prompts/results and restart holds. The
[approved plugin Execution profile](docs/PLUGIN_EXECUTION_SERVICE.md) now adds
immutable native releases and fenced effects through the optional DSS provider.

## Install and open

For the Docker desktop, load the image from the 1.1.1 release, then run this from
the repository root (see [offline build instructions](docs/IDE_SPELL_V06.md)):

```powershell
docker compose up -d --wait ide
```

Open [the browser desktop](http://localhost:6080/vnc.html?autoconnect=1&resize=scale).
Python, Qt, debugpy, examples, shared sessions, a local DSS and the durable
Python/mutual-TLS test profile are included. See the
[Docker testing guide](docs/DOCKER_TESTING.md) for test steps, CLI commands,
persistent files and automated checks. This tests the current implementation;
the browser lab retains its separately built image and persistent user volumes.

For a native Windows desktop:

```powershell
./install.ps1 -Python C:/path/to/python.exe
./start.ps1 -Project examples -File examples/test_python_support/python_menu.py
```

The installer creates `.venv` and installs the locked Windows x64 desktop
dependencies. `examples/test_python_support/python_menu.py` exercises 39 Python topics and opens,
updates and closes a statistics window. The source launchers are `run_ide.py`
and `run_cli.py`; use `python -I` with either.

The [native learning desktop](docs/LEARNING_DESKTOP.md) adds the original SPELL
runtime with a disposable DSS, 24 SPELL procedures, 47 Python procedures/entry
points, two graphics demos, and menus. Its workspace root contains `hello.py`,
`README.md`, `test_spell/` and `test_python_support/`. This is the IDE 1.1 update;
SPELL v0.6 qualification and release remain a separate milestone.

For a headless installation, the core has no GUI dependencies:

```powershell
python -m pip install .
openbexi run hello.py --project C:/my-project
```

For SPELL, install the plugin into the interpreter that will execute the file,
start its DSS, and use explicit imports inside the procedure:

```powershell
.venv/Scripts/python.exe -m pip install ../openbexi_spell_plugin
.venv/Scripts/openbexi.exe run dss_demo.py --project ../openbexi_spell_plugin/examples --language spell --dss-url http://127.0.0.1:8085
```

## Multiple developers in one session

Start a session with one execution slot, or set `--max-parallel 2` through `16`:

```powershell
.venv/Scripts/openbexi.exe serve --project examples --port 9010 --max-parallel 1
.venv/Scripts/openbexi.exe --connection .session/alice.json connect --user Alice --invite-file .session/server.json
.venv/Scripts/openbexi.exe --connection .session/alice.json claim
.venv/Scripts/openbexi.exe --connection .session/alice.json submit session_first.py
.venv/Scripts/openbexi.exe --connection .session/alice.json submit session_second.py
.venv/Scripts/openbexi.exe --connection .session/alice.json watch --renew
```

In another terminal, connect a read-only monitor:

```powershell
.venv/Scripts/openbexi.exe --connection .session/reader.json connect --user Reader --role monitor --invite-file .session/server.json
.venv/Scripts/openbexi.exe --connection .session/reader.json watch
.venv/Scripts/openbexi.exe --connection .session/reader.json stack
```

Join from the desktop with **Session > Join Shared Session**, or launch two
independent clients from the IDE repository:

```powershell
./start.ps1 -Project examples -SessionInfo .session/server.json -User Alice
./start.ps1 -Project examples -SessionInfo .session/server.json -User Reader -Role monitor
```

In the Session tab, choose **Open session folder**, then **Claim control**. The
toolbar's Python/SPELL choice selects the language for shared Run. The server's
interpreter owns execution and must have the optional SPELL plugin installed.
The desktop interpreter remains for local Run/Debug after disconnecting.

Select a procedure to inspect its live threads, frames, locals and output;
double-click a frame to open its local project file. Pause/Resume/Stop apply to
the selected procedure or **All procedures**. Console input goes to the selected
running/pausing procedure. Shared inspection never evaluates expressions.

**Keep control** renews the controller lease while connected. Release,
Disconnect or closing the desktop pauses its session work and fences ownership.
Another developer claims control and explicitly resumes. An unavailable service
disables execution controls; recovered connectivity never automatically claims
or resumes. Monitor windows also make project editors read-only.

The controller may change **Slots** and click **Apply**, or use
`openbexi configure --max-parallel 2`. Reducing the limit below occupied slots
is rejected until those procedures finish or confirm pause. `openbexi disconnect`
revokes that CLI connection. Other desktop/CLI members remain connected.

Use separate connection files for each developer. A second developer may connect
with the developer invitation and monitor the same session, but cannot claim the
controller while somebody else holds it. `pause ID`, `resume ID`, `stop ID` and
`input ID TEXT` require the current controller token; `all` selects every procedure
for pause/resume/stop. `input ID` without text closes script input.
Input can also unblock a pending read while a procedure is `PAUSING`, allowing
it to reach the next safe checkpoint and confirm its pause.

`release` pauses the session and fences the previous controller. Another developer
then uses `claim` and explicitly `resume all`. The controller lease defaults to
30 seconds; `watch --renew` keeps it alive. Closing that command does not resume
or transfer ownership: expiry requests a pause and a fresh claim/resume is needed.

Queued procedures show `PAUSED / WAITING_TOKEN`. Running procedures show `PAUSING`
until all observed Python threads acknowledge the pause and owned child processes
are quiescent. A native blocking call or live child process keeps its slot until
it returns or the controller chooses Stop. A paused procedure can resume from
its live Python stack; a completed or stopped procedure starts anew on submission.
The same logical file cannot run twice concurrently in one session.

The default session service binds to loopback. An opt-in
[durable Development service](docs/DURABLE_SERVICE.md) now adds committed Git
captures, crash holds and direct remote access with explicit mutual TLS identities.
Durable sessions admit Python only. An opt-in
[approved offline Python Execution profile](docs/EXECUTION_SERVICE.md) runs
immutable source/runtime images with container isolation and offline release
approval. Native shared SPELL and operational external effects remain release gates.
Connection files contain private credentials and are excluded from Git. Give a
monitor only the monitor invitation, not the server file containing both invites.

## Desktop controls and validation

Save Ctrl+S, Run F5, Debug Shift+F5, Stop Shift+F2, Continue F6, Pause F7,
Step Over F10, Step Into F11 and Step Out Shift+F11. Click the line gutter to
toggle a breakpoint. Select an interpreter and arguments in the Run menu.

```powershell
python -m pip install '.[desktop,test]'
python -m pytest tests -q
```

Local Development executes with the server user's OS permissions. These sessions
are not the approved operational Execution service. Monitoring is read-only;
operational driver integration and fine-grained external-effect receipts remain
explicit future gates. Approval and isolation are qualified only for the offline
Python profile above. Durable restart/reconciliation is available in the
bounded profiles described above. See [architecture](docs/ARCHITECTURE.md),
[roadmap](ROADMAP.md), [master prompt](openbexi_ide_master_prompt.md) and
[migration](docs/MIGRATION.md). The v0.2 test scope and remaining gates are in
[qualification](docs/QUALIFICATION.md).
