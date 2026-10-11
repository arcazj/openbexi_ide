# Test OpenBEXI IDE in Docker

The real Qt IDE runs inside a Linux container and appears in your browser.
The image includes CPython 3.13.15, Qt/PySide6 6.10.3, debugpy 1.8.22, Git,
sample projects, the headless CLI, session services and the bounded SPELL/DSS
development fixture. You do not need Python or Qt installed on Windows.

## Start

Use Docker Desktop with Linux containers and a recent Docker Compose
(2.20 or later). Keep `openbexi_ide` and `openbexi_spell_plugin` as sibling
checkouts. The initial build downloads the base image, Debian packages and
locked Python wheels; later starts use the local image. This image targets
Linux x86_64. Allow about 6 GiB of Docker memory to run the desktop and the
separate automated-test container together; each has a 3 GiB limit.

From `C:/projects/openbexi_ide`:

```powershell
docker compose up -d --build --wait ide
docker compose ps
```

Open **[OpenBEXI IDE](http://localhost:6080/)**. The base address automatically
opens the desktop; `http://127.0.0.1:6080/` also works.
The IDE opens `hello.py`. The desktop underneath has visible launch buttons for
Python, **SPELL / DSS — Alice**, Monitoring and a terminal. Closing an IDE leaves
these buttons available. Right-click the background for the same choices.
Double-click a window title to maximize it; Alt+Tab
switches between windows. If the browser intercepts a function key, use the IDE
toolbar/menu or noVNC's extra-keys controls.

Only `127.0.0.1:6080` is published. To choose another host port in PowerShell:

```powershell
$env:OPENBEXI_DESKTOP_PORT = '6081'
docker compose up -d --wait ide
```

Then use port 6081 in the browser URL. The desktop is a local test fixture with
no VNC password; keep the loopback binding. Its services are separate from
existing Windows DSS/session services and bind only inside the container.

## Choose a test window

| Desktop button | What to test |
| --- | --- |
| Python IDE | Editor, Run, console input, debugpy breakpoints/steps/variables, graphics |
| SPELL / DSS — Alice / Shared developer — Bob | Shared Python or bounded SPELL; controller ownership, queue, slots, pause/resume, handoff |
| Read-only monitor | Shared output/stacks with editing and execution controls disabled |
| Durable Python | Python with captured committed Git sources, durable events and mutual TLS |
| Durable monitor | Read-only certificate identity on the durable service |
| Terminal | CLI, Git and test files inside Docker |

These are convenient windows in one test desktop. They share the container's
test account and are not separate OS security boundaries.

### Python Run and Debug

1. In the initial window, click **Run**. `hello.py` prints a greeting.
2. Click the line gutter beside `message = greet(name)`, then **Debug**.
   Inspect the current frame and variables; use Step Into, Step Over and
   Continue. **Stop** ends the owned debug process.
3. Open `test_menu.py` in the project tree and Run. Enter `1` in the console
   input to exercise all 39 Python topics. Choices `4`, `5` and `6` open,
   update and close the statistics window; `0` exits.

Projects are under `/workspace/projects/demo` and `/workspace/projects/durable`.
The Run menu can select a project virtual environment if you create one.

### Shared developers, Monitoring and DSS

1. Open **SPELL / DSS — Alice**, **Shared developer — Bob** and
   **Read-only monitor** using the desktop buttons. Each joins the same ephemeral session automatically.
2. In Alice's **Session** tab, click **Claim control** and leave **Keep control**
   enabled. Bob and the monitor can inspect without controlling Alice's work.
3. Run `session_first.py` and `session_second.py`. The default is two execution
   slots. Inspect their live stacks and output, then pause/resume a procedure.
   Set **Slots** to one when no more than one slot is occupied to test queuing.
4. Release Alice's control, claim it in Bob's window, then explicitly Resume.
   Monitoring remains read-only throughout.
5. Open `dss_demo.py`, select **SPELL**, and Run as controller. It reads `TM1`
   and sends `CMD1` over the binary DSS transport. This is the included local
   simulator, not an operational command destination.

Shared inspection and pause/resume are supported. Interactive debugpy stepping
uses the local Python window; shared debugger sessions remain outside this profile.

### Durable Development

Open **Durable Python**, claim control and Run `hello.py`. It is already
committed in the durable sample Git repository. Open **Durable monitor** to
inspect through the separate read-only certificate identity.

Commit changes before submitting modified durable procedures. For example,
inside the container terminal:

```sh
git -C /workspace/projects/durable add hello.py
git -C /workspace/projects/durable -c user.name=Tester -c user.email=tester@example.invalid commit -m "Update test procedure"
```

Restarting the container retains the durable journal, Git captures, logical
reservations and certificate identities. Reopen the shared/durable windows
after restarting. Connections and controller leases are revoked, queued work
stays paused, and interrupted work may require explicit offline reconciliation.
The service never automatically replays uncertain work. See
[the durable-service guide](DURABLE_SERVICE.md) for recovery rules and receipts.
The default shared session is ephemeral, so its session history resets on restart.

## CLI and automated tests

From Windows, run the same installed CLI in the desktop container:

```powershell
docker compose exec ide openbexi run hello.py --project /workspace/projects/demo
docker compose exec ide openbexi run dss_demo.py --project /workspace/projects/demo --language spell --dss-url http://127.0.0.1:8085
docker compose exec ide bash
```

For a separate shared CLI identity, inside that shell:

```sh
openbexi --connection /workspace/connections/cli.json connect --user CLI --invite-file /workspace/connections/shared-server.json
openbexi --connection /workspace/connections/cli.json status
openbexi --connection /workspace/connections/cli.json disconnect
```

The following checks the live services and the noVNC WebSocket-to-VNC connection
without claiming control or running procedures:

```powershell
docker compose exec -T ide python -I /opt/test-lab/check_lab.py
```

Run the full suite in a separate container, with its own disposable services:

```powershell
docker compose --profile tests run --rm tests
```

This runs pytest with warnings treated as errors, the installed CLI/plugin
integration, and two installed Qt clients on X11 with a CLI peer. The tests
exercise real debugpy, queues, TLS/revocation, durable crash holds and binary
DSS commands. They do not use your desktop's project or service data.
After source changes, rebuild with the start command before running tests.

JUnit XML, installed-check JSON, Python reference output and desktop PNGs stay
in the `evidence` volume, under a timestamped directory printed by the test
command. Copy them to Windows while the desktop container is running:

```powershell
New-Item -ItemType Directory -Force .qualification/docker-test | Out-Null
docker compose cp ide:/evidence/. .qualification/docker-test
```

## Keep files and troubleshoot

The `workspace` volume stores your projects, DSS database, durable state,
captures, generated test certificates and `/workspace/logs`. `preferences`
stores each IDE window's settings; `evidence` stores test results. These are
initialized on first start and retained across rebuilds and `docker compose down`.
Updated image examples do not overwrite your saved project edits.

```powershell
docker compose logs --tail 100 ide
docker compose exec ide ls /workspace/logs
docker compose stop ide
docker compose up -d --wait ide
```

To copy your sample projects out:

```powershell
docker compose cp ide:/workspace/projects ./docker-project-backup
```

Use `docker compose down` to remove this lab's containers/network while
retaining its volumes. Do not add `-v` or prune volumes if you want to keep
your files. Closing an IDE window leaves the desktop launcher visible; use a
button to reopen a window. The display's idle screen blanking is disabled.
The health check requires the launcher to be running as well as the services.
From Windows you can also use
`docker compose exec -d ide openbexi-lab local` (or `alice`, `bob`, `monitor`,
`durable`, `durable-monitor`, `terminal`).

If startup fails, read `/workspace/logs` through `docker compose cp` and the
container log. Test certificates are generated locally on first start, have
a one-year lifetime and are private to the persistent test workspace. Expired
certificates need explicit replacement; rebuilding does not change the CA.

## Scope and evidence

This packages the current IDE 0.2 distribution plus partial v0.3 prerequisites
for testing. The plugin's bounded SDK distribution is 0.1.0, independently of
its separately qualified native host v0.3. The latter image, native driver
integration, Kafka/operational DSS, approved Execution and plugin v0.4–v0.6
are not included in this test profile. See the
[remaining release gates](RESUME_V04.md).

The image runs as UID 10003, with dropped capabilities and no Docker socket or
host project mounts. The base image digest and Python wheel hashes are pinned;
Debian packages still resolve from their repositories at build time, so this is
not a claim of complete release reproducibility. Local qualification details
are recorded in [DOCKER_QUALIFICATION.json](DOCKER_QUALIFICATION.json).

On 2026-10-11 the Docker suite passed 83 tests, with one Windows-only test
skipped; the Windows regression suite passed all 84. Installed CLI and X11
desktop checks, live browser transport, first startup and persistent restart
checks passed. An interactive browser click-through was unavailable in the
automation environment; the actual Qt/X11 captures were visually reviewed.
