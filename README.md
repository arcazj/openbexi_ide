# openbexi_ide v0.2

Continuing development after the repository split: [resume v0.4](docs/RESUME_V04.md).

A standalone CPython 3.13 IDE and headless CLI. The desktop has a project tree,
tabbed editor, output and real debugpy debugger, with light/dark themes and a
compact Open Folder / Run / Debug / Stop toolbar. SPELL is an optional, separately
installed [plugin](https://github.com/arcazj/openbexi_spell_plugin).

The desktop and CLI now share the same Development session service. The Session
tab shows developers, controller ownership, serial/parallel queues, real live
Python stacks, bounded locals and per-procedure output.

## Install and open

For a complete local Docker test desktop, run this from the repository root with
`openbexi_spell_plugin` beside it:

```powershell
docker compose up -d --build --wait ide
```

Open [the browser desktop](http://localhost:6080/vnc.html?autoconnect=1&resize=scale).
Python, Qt, debugpy, examples, shared sessions, a local DSS and the durable
Python/mutual-TLS test profile are included. See the
[Docker testing guide](docs/DOCKER_TESTING.md) for test steps, CLI commands,
persistent files and automated checks. This tests the current implementation;
IDE v0.3 acceptance is still in progress.

For a native Windows desktop:

```powershell
./install.ps1 -Python C:/path/to/python.exe
./start.ps1 -Project examples -File examples/test_menu.py
```

The installer creates `.venv` and installs the locked Windows x64 desktop
dependencies. `examples/test_menu.py` exercises 39 Python topics and opens,
updates and closes a statistics window. The source launchers are `run_ide.py`
and `run_cli.py`; use `python -I` with either.

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
