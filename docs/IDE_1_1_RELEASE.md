# OpenBEXI IDE 1.1.0

Version 1.1.0 develops the 1.2.0rc1 code base into a shared SPELL execution
workspace for the native desktop, IntelliJ IDEA, PyCharm and a web browser.
SPELL v0.6 remains paused. This IDE release does not promote the independent
SPELL language or operational Execution milestones.

The code/results table, blue current line, native status colors, embedded
prompts and persistent procedure strip follow SPELL GUI User Manual 2.4.4.
Python panes disappear in SPELL mode. Running a procedure focuses the execution
workspace; completed and paused instances remain selectable. The additional
procedure list is collapsed until requested.

The Python service owns native execution. Clients can detach, reconnect, inspect
captured source and explicitly take control of the original instance. One
controller answers prompts and sends commands; other clients monitor. Native
acknowledgements govern button state and execution-slot release. Prompt IDs
prevent duplicate or stale answers. SQLite records retain notification history,
item information and source snapshots after completion. Item dialogs provide
Latest, History and Full; Qt and browser clients export As-Run records.

## Downloads and compatibility

The release tag is `v1.1.0`, and the package version is `1.1.0`.
Publication status and exact evidence are recorded in
[the acceptance record](IDE_1_1_ACCEPTANCE.md). Verify downloaded files against
the release's `SHA256SUMS.txt`.

| Component | Version |
| --- | --- |
| IDE core, service and desktop | 1.1.0 |
| CPython / desktop Qt | 3.13.15 / PySide6 Essentials 6.10.3 |
| Optional native host | openbexi-spell-host 0.3.1.dev3 |
| Native image | openbexi-spell-host:0.3.1-dev3 |
| JetBrains plugin | 0.3.1-workspace.2 |
| Qualified IntelliJ IDEA | 2026.2.3, build 262.10968.63 |
| Qualified PyCharm | 2026.1.2, build 261.24374.152 |

## Windows installation and migration

Extract the entire `OpenBEXI-IDE-1.1.0-windows-x64.zip` and run `Install.cmd`.
The offline bundle includes Python and desktop dependencies. It preserves user
projects and preferences and selects the version from its package manifest.
**1.1.0 sorts below 1.2.0rc1** in Python version ordering, so explicitly install
this artifact rather than relying on a "newer version" update check.

For an existing CPython 3.13 environment with desktop dependencies installed:

```powershell
python -m pip install --no-index --no-deps --force-reinstall ./openbexi_ide-1.1.0-py3-none-any.whl
```

Native SPELL on Windows additionally needs Docker running Linux containers and
the supplied optional host wheel in the selected interpreter:

```powershell
docker load --input openbexi-spell-host-0.3.1-dev3-linux-amd64.tar.gz
python -m pip install --no-index --no-deps ./openbexi_spell_host-0.3.1.dev3-py3-none-any.whl
```

Finish or abort live native instances before replacing an older service. The
launcher refuses to replace a live service; it replaces an idle older service
and restores its saved records without replaying execution. Restart clients
after updating their interpreter packages.

## IntelliJ IDEA and PyCharm

Install `openbexi-spell-0.3.1-workspace.2.zip` through **Settings > Plugins >
gear > Install Plugin from Disk**, then restart the IDE. In **SPELL Runtime
Settings**, select the CPython interpreter containing **both** the IDE core and
host wheels. Select image `openbexi-spell-host:0.3.1-dev3`; existing explicitly
saved image choices are preserved. Synchronize editor definitions as usual.

Use **Tools > SPELL > Procedures > Run File with SPELL** or **Debug File with
SPELL**. **Procedure Workspace** shows execution, prior instances, source,
results and embedded prompts. **Return to editor** restores the editor layout.
Use **Web workspace** to open another view of the same service.

## Web control and monitoring

The desktop's **Web workspace** button opens the Python service in a browser.
The browser can start, pause, continue, step and abort supported native
procedures, answer embedded prompts, inspect item history and export As-Run.
Reconnect restores the saved workspace; it does not replay a command or take
control automatically. A monitor credential cannot control execution.

The default endpoint binds only to loopback. For another computer, configure
the service's mutual-TLS certificate identities and operator/monitor roles as
described in [the workspace guide](PROCEDURE_WORKSPACE.md). Do not distribute
the endpoint file containing both private credentials to monitors.

## Linux Docker desktop

The image includes the native runtime and teaching DSS:

```sh
docker load --input openbexi-ide-1.1.0-linux-amd64.tar.gz
docker compose -f compose.v11.yaml up -d --wait
```

Open <http://127.0.0.1:6091/vnc.html?autoconnect=1&resize=remote>.
`OPENBEXI_V11_PORT` selects a different local port. The Compose file uses an init
process so native executor children are reaped. Workspace and preferences use
named volumes. Keep previous user-data volumes when retiring old containers.

## Verified scope and remaining limits

The acceptance record links exact artifact hashes, automated reports and actual
captured previews. Checks include native Windows and packaged Linux Run/Debug,
five prompts and child-source transitions, Abort followed by Run, ordinary
Python, two-instance reconnect, real IntelliJ/PyCharm debugging and prompts,
browser control/monitor behavior, item records and As-Run export. The fresh
installation check uses GitHub's hosted Windows Server 2025 VM; it is separate
from private-directory migration on the development machine.

There is one running slot per service. The container backend supports eight
live instances; the packaged Linux native backend currently supports one.
The service retains 100 recent instances in the visible workspace; durable
notification records are paged. A service restart marks interrupted live
records disconnected and does not automatically recover native execution.

Skip, Goto, Recover, Run Until, By Step, scheduling, Shell and TC confirmation
are unavailable in this backend. Full legacy domain navigation, shared-variable
and editable executor-defaults panels are outside this release. Native prompt
validation remains authoritative; interactive coverage focuses on Yes/No, text,
numeric and list prompts. Operational admission and external-effect authority
remain separate from this Development workspace.
