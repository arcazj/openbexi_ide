# OpenBEXI IDE 1.2.0rc1

This prerelease adds the procedure workspace inspired by the SPELL GUI User
Manual: a code/results table, current-line highlighting, per-session procedure
history and embedded prompts with Commit, Reset and Abort controls. Native
results and source snapshots come from the running procedure. Ordinary Python
keeps its existing Run and Debug workflow.

**SPELL v0.6 remains paused.** This IDE GUI candidate does not publish, qualify
or promote the independent SPELL language/distribution milestone.

## Candidate and matching components

The Git tag is `v1.2.0rc1`; the Python package version is `1.2.0rc1`.
Download artifacts and `SHA256SUMS.txt` from the
[GitHub prerelease](https://github.com/arcazj/openbexi_ide/releases/tag/v1.2.0rc1).
Stable IDE 1.0 remains available separately.

- Windows x64 offline installer: `OpenBEXI-IDE-1.2.0rc1-windows-x64.zip`.
- IDE wheel: `openbexi_ide-1.2.0rc1-py3-none-any.whl`.
- Linux amd64 desktop: `openbexi-ide-1.2.0rc1-linux-amd64.tar.gz`.
- Optional host wheel: `openbexi_spell_host-0.3.1.dev3-py3-none-any.whl`.
- Native host image: `openbexi-spell-host-0.3.1-dev3-linux-amd64.tar.gz`.
- IntelliJ plugin: `openbexi-spell-0.3.1-workspace.1.zip`.

The companion host and IntelliJ ZIP are the unchanged workspace candidates
from plugin commit `11d5b3f`. Their candidate versions do not indicate a SPELL
v0.6 release. The native image ID is
`sha256:0518192b4748bd4f5fa2cef5daa4ebe5b884735f559636bce5ba0b4119355c79`.
The release dossier records the desktop image, artifact hashes and test reports.

## Windows

Extract the entire Windows ZIP and run `Install.cmd`. CPython 3.13.15 and the
desktop dependencies are included. No machine Python or administrator install
is required. Upgrading through the installer retains user projects and settings.
The bundle includes Python functionality; native SPELL is an optional component.

For native SPELL, install Docker with Linux containers, load the supplied host
image, and install the matching host wheel into the Python interpreter selected
for the IDE. Use that interpreter's full path in place of `python` below:

```powershell
docker load --input openbexi-spell-host-0.3.1-dev3-linux-amd64.tar.gz
python -m pip install --no-index --no-deps ./openbexi_spell_host-0.3.1.dev3-py3-none-any.whl
```

For an existing CPython 3.13 environment with desktop dependencies installed,
install the IDE wheel with `python -m pip install --no-index --no-deps
./openbexi_ide-1.2.0rc1-py3-none-any.whl`. Select the installed native SPELL
runtime in the IDE before running a SPELL procedure.

## Linux desktop through Docker

The desktop image includes the IDE, native SPELL runtime and local teaching DSS.
Load it, then use the attached Compose file with separate candidate volumes:

```sh
docker load --input openbexi-ide-1.2.0rc1-linux-amd64.tar.gz
docker compose -f compose.rc1.yaml up -d --wait
```

Open <http://127.0.0.1:6088/vnc.html?autoconnect=1&resize=remote>.
Set `OPENBEXI_RC1_PORT` to use another local port. Existing desktop volumes and
the previous installed release are not replaced by this Compose project.

## IntelliJ

Install the supplied ZIP using Settings > Plugins > Install Plugin from Disk,
then restart IntelliJ. Under Settings > SPELL Runtime, select a CPython 3.13
interpreter containing the matching host wheel and image
`openbexi-spell-host:0.3.1-dev3`. Synchronize the editor definitions.
The candidate was exercised on IntelliJ IDEA 2026.2.3 / Windows x64.

Open a procedure and use **Tools > SPELL > Procedures > Run File with SPELL**
or **Debug File with SPELL**. **Tools > SPELL > Procedure Workspace** opens the
table, history and prompts. Submit answers in the embedded panel. The usual
Python run configuration remains a separate interpreter workflow.

## Validation and open issues

See `IDE_1_2_0_RC1_RELEASE_DOSSIER.json` for the exact candidate reports and
`PROCEDURE_WORKSPACE_QUALIFICATION.json` for the earlier development evidence.
Do not treat a development report as a new release-candidate test.

- Linux unit/integration suite: **190 passed, 9 skipped** on the complete rerun.
  The initial run had one TLS timeout; its focused recheck also passed (3 tests).
- Windows suite: **189 passed, 9 skipped, 1 failed** in the complete run.
  The failure was a shared-desktop timeout; the full affected module passed
  on recheck (8 tests). A clean complete Windows rerun remains open.
- The Windows native workspace passed Run and Debug with five prompts each,
  child-source display, results, history, Stop/rerun and ordinary Python.
  The installed Windows candidate also passed Python Run/Debug, interactive
  menus, shared debugging and all 15 deep-Python example chapters with graphics.
  Upgrade and manifest-owned uninstall passed; active-process uninstall was
  refused and user projects, edited examples and preferences were preserved.
- Actual Edge/noVNC inputs exercised Python Run, the native menu's embedded
  prompt, answer submission, `Finished (0)`, and closing both windows.
  Captures include the [prompt](https://github.com/arcazj/openbexi_ide/blob/v1.2.0rc1/docs/evidence/ide-1.2.0rc1/browser/006-native-prompt.png)
  and [completed table](https://github.com/arcazj/openbexi_ide/blob/v1.2.0rc1/docs/evidence/ide-1.2.0rc1/browser-completion/000-connected.png).
- **Known Linux native issue:** an immediate Run after Abort consistently
  timed out during debugger launch in two installed-container checks. Run and
  Debug prompt/result cases passed before that failure. Stop/rerun acceptance
  on the packaged Linux native backend remains open; no fix is claimed here.
- An IntelliJ `spell_menu.py` Debug session ended with `Failed (1)` at a prompt
  on 2026-10-17 without a retained diagnostic. Subsequent direct host and actual
  IntelliJ Run/Debug checks passed, including two successive embedded answers
  and the Python demonstration. The cause remains unconfirmed; no code fix is
  claimed for that incident.
- Independent installation on a freshly provisioned Windows machine remains
  pending. A clean directory on the development host does not satisfy it.
- History is limited to the current IDE session. Native artifacts are retained
  separately under `.openbexi/runs`.
- Native interaction coverage focuses on Yes/No, text, numeric and list prompts.
  Date/password controls still rely on backend validation.
- Full original-GUI equivalence, wider IntelliJ/platform acceptance and SPELL
  language requalification are outside this candidate's scope. Historical
  conformance reports remain bound to their original source identities.

The stable 1.2.0 promotion remains open. To exercise the fresh-Windows check on
a separate fresh Windows x64 environment, use the supplied harness and ZIP hash:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ./qualify_fresh_windows.ps1 -Archive ./OpenBEXI-IDE-1.2.0rc1-windows-x64.zip -ExpectedSha256 04e8f9552e71c12831733d79bc5af921f4f0820e001f6899ba07a9c29fee87bd -ExpectedVersion 1.2.0rc1 -FreshWindows
```
