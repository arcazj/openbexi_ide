# Windows and Docker v1.0 candidate

Version 1.0.0rc3 is a release candidate. Final release acceptance remains false
until actual browser interaction and a fresh Windows environment are qualified.
The [machine-checked dossier](IDE_RELEASE_DOSSIER.json) records the exact artifacts,
test results and outstanding gates. No final v1.0 tag is created by this checkpoint.

## Try the corrected console

The v0.5.0rc2 desktop remains available at
`http://127.0.0.1:6086/vnc.html`. The v1.0.0rc3 candidate has a separate desktop:

```powershell
docker compose -f compose.v1.yaml up -d --wait
```

Open `http://127.0.0.1:6087/vnc.html`, launch the Python IDE and open
`test_menu.py`. Run or Debug the script. Type a menu choice into the input field
and press Enter or Send. Typing while console output has focus also forwards
ordinary keys to the enabled input field. The menu returns after each operation;
choices 3 and 5 ask for another answer. Choice 0 exits.

Each candidate has separate workspace/preferences volumes. The preexisting
desktop on port 6080 and its open windows remain preserved. Those older running
processes do not acquire a new installed version when a new image is built.

The sibling SPELL host has a separately tested **0.3.1.dev1** development
candidate for early console answers and native child prompts. It preserves
answers typed after question output but before the native input event. Its
distinct package version allows the IDE's local-wheel installer to upgrade
0.3.0. The actual Qt plugin manager, Run/Debug child answers, removal and ordinary
Python afterward pass on this IDE's source at `3779d85`; all installed wheel
members match the selected artifact. The project and preferences survive.
The [host upgrade record](../../openbexi_spell_plugin/distribution/evidence/host-console-upgrade.json)
binds the reproducible wheel and required child-development runtime image.
The console fix and installable host candidate are on the sibling's main branch
at `a1b482a`; the combined native runtime is still under qualification.
This supplemental check does not replace the immutable IDE candidate's release
dossier or qualify browser/fresh-Windows acceptance.

## Install on Windows

Extract the candidate Windows ZIP and run `Install.cmd`. The package contains
its own locked CPython 3.13.15 interpreter and desktop dependencies. See the
[installation and removal instructions](IDE_V06_DISTRIBUTION.md) for explicit
locations, offline inputs, versioned upgrades and preservation of user files.

The local artifact is
`.qualification/v1.0/windows-build-v1rc3-a/OpenBEXI-IDE-1.0.0rc3-windows-x64.zip`.
Two independent assemblies produced SHA-256
`fdd263e0eb48295689efa084a879e5d943d9bd5fd4658db7a48bb68d66c4a69b`.
The [distribution manifest](IDE_V10_QUALIFICATION.json) binds both ZIPs,
system-tar extraction of all 7,607 files and the 19 installed lifecycle checks.

The supported candidate scope is Windows x64 and Linux x86_64 Docker. It includes
Python editing/completion, local and shared debugging, fenced controller handoff,
console input and optional local runtime plugins. Native SPELL uses its separately
installed host plugin and selected Docker runtime. Shared native SPELL DAP and
full sibling-plugin language conformance retain their separate acceptance gates.

## Qualification boundaries

The frozen source is under `.qualification/ide-v1.0/candidate-v1rc3/source`.
It derives from Git commit `4bb735c` plus recorded version, README, roadmap and
dossier metadata. Installer recipes use canonical LF bytes, matching the v0.6
qualified recipes and the new explicit Git attribute.

Final Windows source tests pass **170 tests**, with one symlink test skipped
because this account lacks symlink creation permission. Linux passes **162
tests**, with eight Docker Execution tests skipped inside its container and one
Windows-only Job test skipped. The eight real Docker Execution tests run in the
Windows suite. Installed X11 workflows, diagnostics, both Run/Debug menus and the
actual Windows v0.6-to-v1.0 upgrade/removal lifecycle pass. The release checker
reports only the fresh-Windows gate as open.

The installed Windows native SPELL lifecycle uses the previously qualified
`0eadf2e3...` runtime. The later sibling `3434d53d...` DTA/telemetry checkpoint
has its own actual native DSS integration report using the test-only live-clock
fixture committed as `c0e2bfe`. That fixture change is outside the immutable IDE
candidate snapshot; it changes neither the packaged application nor its wheel.

An earlier Windows rc1 full-suite run failed during controller handoff. Bounded
reproductions did not reproduce that timeout, but independently demonstrated a
delayed renewal reply replacing a newer control epoch. Commit `bdf5284` fences
both successful and failed stale renewals. Five regression cases and the real
shared-desktop group pass. Earlier failed reports remain preserved; the original
timeout's exact cause has not been established.

Installed Linux menu tests initially failed a focus assertion when synthetic
input targeted an inactive IDE after the graphics window opened. The harness
now activates the IDE before input, while retaining the post-Send focus check.
The installed X11/Openbox Run and Debug menus then pass all choices, nested input,
graphics closure and exit. A separate real Edge/noVNC run now passes 13 browser
checks: choices 1–6, Send/Enter and nested prompts, Run/Debug scrolling, and X
buttons for IDE, graphics, shared-session and terminal windows. The report is
bound in the release dossier. Busy Debug shutdown prints `NoMoreMessages` before
`Stopped`, but closes the window and all owned target/debug adapter processes.
Fresh Windows installation remains pending: Sandbox is unavailable, and this
account cannot enumerate Hyper-V VMs.

Use `openbexi doctor --desktop` for a bounded installed-runtime report. See
[operations and recovery](OPERATIONS.md) before moving service state or restoring
historical evidence. A backup never authorizes replaying an uncertain effect.
