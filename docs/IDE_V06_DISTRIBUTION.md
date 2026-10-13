# Windows distribution candidate

The offline Windows x64 distribution is under qualification. It is independent
of the sibling SPELL plugin's version series. No final IDE v0.6 release is
accepted while the earlier IDE milestones or their live noVNC checks remain open.

## Artifact and installation

`packaging/windows/build_bundle.py` assembles a normal private CPython interpreter,
the IDE wheel, and the four hash-locked desktop dependency wheels. The normal
interpreter is also used by Run, debugpy, workers and optional runtime plugins.
Neither the installer nor the installed desktop requires a machine Python.

The ZIP contains `Install.cmd`, PowerShell scripts, `package.json`, and a payload.
Extract it and run `Install.cmd`. The default location is
`%LOCALAPPDATA%\OpenBEXI\IDE`, with a Start menu shortcut. An explicit location
and no-shortcut installation are supported:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 -Root "C:\My IDE" -NoShortcuts
```

Windows' built-in `tar.exe` was also checked for extracting the complete ZIP into
a directory containing spaces and long resource paths. For example, create an
empty extraction directory and run `tar.exe -xf <release.zip> -C <directory>`.
This extraction path does not need Python or an additional archive utility.

The installer checks every payload hash before creating or updating an owned
installation. It copies into a private staging directory, verifies the copy, then
activates a versioned directory. Existing version directories remain available;
running processes keep their original interpreter. Reinstalling identical bytes
is idempotent. Existing directories without the OpenBEXI ownership marker and
modified installation tools are rejected without overwriting them. Extended
literal Windows paths support the long resource names in PySide6 with Windows
PowerShell 5.1.

User-edited Start menu shortcuts are also preserved: an upgrade rejects the
overwrite, and uninstall reports the retained shortcut. Modified installation
tools retain the ownership marker so their preserved state remains reviewable.

Run a newer bundle's installer with the same root to upgrade. Versioned examples
are shipped from an explicitly selected source snapshot. Copy examples to a
project before editing them; the installer never publishes over a user's project.

Run the installed `uninstall.ps1` to remove the application. It removes only
unchanged manifest-owned files and empty owned directories. Modified files and
unknown files remain. Projects, edited example copies and QSettings preferences
are outside the owned payload. An active bundled Python process blocks uninstall
before any files are removed. Close it and repeat uninstall. The uninstaller does
not delete whole directories recursively.

The optional SPELL host wheel and qualified Docker execution image are separate
artifacts. Ordinary Python works without them. SPELL Run/Debug requires Docker
and the selected installed host plugin/image.
Each application version has a separate Python environment. Install optional
plugins in the new interpreter through the plugin manager after upgrading; the
old environment and explicitly saved interpreter preferences remain available.

## Locked inputs and provenance

The runtime is CPython 3.13.15, Astral standalone build 20260814, Windows x64:

* Archive SHA-256: `4ca61e4b09c2240cc50cc6910c90664051e93ab7caa2f48b3c6b3c070670c0bd`.
* Size: 47,131,996 bytes.
* Exact upstream URL and release metadata are in
  [`runtime.lock.json`](../packaging/windows/runtime.lock.json).

The runtime archive hash was checked against the asset digest in the
[upstream release](https://github.com/astral-sh/python-build-standalone/releases/tag/20260814).
Astral describes these as self-contained Python distributions in its
[distribution documentation](https://docs.astral.sh/python-build-standalone/).

Desktop dependencies are the exact wheel bytes in
[`requirements-windows-cp313.lock`](../requirements-windows-cp313.lock):
PySide6-Essentials 6.10.3, shiboken6 6.10.3, debugpy 1.8.22, Pygments 2.21.0.
Every wheel RECORD is validated before extraction. The builder refuses archive
traversal, symlinks, duplicate paths and overlapping package files. Runtime scripts
with installation-specific shebangs and upstream bytecode caches are excluded;
`runtime\python.exe -I -m pip` remains available. The builder then compiles
deterministic CPython 3.13.15 checked-hash bytecode with relative source names.
These caches are manifest-owned, so ordinary imports do not leave unowned caches
behind after removal. Changed cache bytes remain preserved like any other modified
owned file.

`provenance.json` records the runtime source, input wheel hashes, packaging recipe
hashes, example hashes, source snapshot and license hashes. With
`--source-snapshot`, every IDE Python file in the wheel must exactly match the
selected snapshot, whose source ZIP is shipped in `source/`. Wheel license files
and the runtime's supplied notices remain in the payload. Source metadata is
taken from the wheel and snapshot; the builder never changes repository versions.
Exact packaging recipe bytes are also shipped under
`source/distribution/packaging/windows/`, including when a historical application
snapshot predates the packaging work.

All ZIP paths are sorted with a fixed timestamp and file mode. A build output
directory must be new. Packaging recipes changing during a build cause failure.
The complete runtime archive and dependency wheels can be cached for offline
rebuilds; no downloads occur when the runtime cache is present and valid.

```powershell
# Use exact CPython 3.13.15 and an immutable candidate source snapshot.
python -m pip download --require-hashes --only-binary=:all: --no-deps `
  -r requirements-windows-cp313.lock --dest .qualification/v0.6/windows-inputs/wheels
python packaging/windows/build_bundle.py `
  --ide-wheel <candidate-wheel> --source-snapshot <candidate-source> `
  --examples <candidate-source>/examples `
  --wheels .qualification/v0.6/windows-inputs/wheels `
  --cache .qualification/v0.6/windows-inputs --output <new-output-directory>
```

## Qualification and platform matrix

| Profile | Current evidence |
| --- | --- |
| Windows 11 Pro x64, build 26200; Windows PowerShell 5.1 | Private CPython installation, long/spaced paths, installed Python/debugpy, editor/examples, interactive menu and collaborative debugging pass on 0.6rc1 |
| Windows x64 lifecycle safety | Eight focused checks pass: install/idempotency/upgrade, preserved edits and user data, rejection of unowned roots, full clean removal, edited installation tools and shortcuts, corrupted payload rejection, traversal rejection |
| Byte reproducibility | Independent 0.3.0, 0.4rc1, corrected 0.4rc3 and 0.6rc1 assemblies produce identical complete ZIP bytes within each pair |
| Existing-host clean directory | Full 0.5rc1 to 0.6rc1 upgrade, installed Python/SPELL Run/Debug, active-process protection and complete removal pass |
| Release ZIP extraction | Windows system bsdtar 3.8.8 extracts the archive; every extracted payload hash is checked |
| Fresh Windows VM without development tools | Not yet qualified |
| Actual noVNC X-button/mouse-wheel operation | Remains an earlier milestone's open live UI gate |
| Windows ARM64, Linux desktop, macOS desktop | No installer acceptance claimed |

The ZIP is not Authenticode signed. Its published SHA-256 must be checked before
installation. The launcher uses a process-local execution policy; it makes no
persistent policy changes and cannot override managed Windows policy.
Signing/SmartScreen behavior on a clean machine remains a
distribution qualification limitation.

The historical baseline pair is
`.qualification/v0.6/windows-build-{b,c}/OpenBEXI-IDE-0.3.0-windows-x64.zip`,
SHA-256 `390d9c808dba8dedaa6350c0f05720372e3d20966c5dabb76980d429059c25a4`.
It predates the explicit examples/source-snapshot builder additions. The first
`windows-build-a` trial exposed the legacy PowerShell path-length defect and
is retained as diagnostic evidence; its extracted installer scripts were then
patched for a long-path development trial. It is not promoted as a final artifact.

Two later v0.4rc1 assemblies including the exact example/source snapshots also
matched: `.qualification/v0.6/windows-build-v04rc1-source{,-b}/`, ZIP SHA-256
`d41b5e154400c53a1fd1b72a9b5475c46c0cc9fd42c8229213b64e58d54290ab`.
The full rc1 lifecycle exposed the launch wrapper's missing pythonw exit-code
handling after the installed Python/UI checks passed. The corrected launcher uses
the normal bundled interpreter beneath the hidden shortcut console. The rc1
failure record remains in `windows-lifecycle-v04rc1`; it is not a passing complete
lifecycle. The application has subsequently moved to the root-coordinated rc2
candidate to correct its independently found fast interpreter-probe ownership race.

The corrected rc2 pair is
`.qualification/v0.6/windows-build-v04rc2-final-{a,b}/`, complete ZIP SHA-256
`f09d0a8c3a3bb4fe72265794bde4b8c7c957cf5aa6e416e04db4854983d2386b`.
It contains 5,898 manifest-owned files, including examples, source snapshot and
packaging recipe sources. Its input IDE wheel SHA-256 is
`a4bc65a177fe23d4fd0ea3d34b82b1c6bec96c7805c277c9cba955bdd10cf40b`.
Its full installed Python/SPELL workflows passed. Its strict complete-uninstall
check failed because native-host subprocesses generated previously unowned
CPython cache files; the conservative uninstaller preserved them. This trial is
retained in `windows-lifecycle-v04rc2`. Subsequent builds ship deterministic
manifest-owned caches rather than adding broad cache-directory deletion.

The rc3 pair with checked-hash bytecode is
`.qualification/v0.6/windows-build-v04rc3-{a,b}/`, complete ZIP SHA-256
`d9f6753a975b7276b2b3a05c4a93882da0643c0ad09e726454c4393f949ec950`.
Its 7,593 payload files include 1,695 deterministic bytecode files. The input IDE
wheel SHA-256 is `3b6c2bca32920f078e367df590af2e8e9081e476828fb8dce0369c5c3ec47ce7`.
The source snapshot includes the root's Windows probe ownership and stable ctypes
ABI fixes. The Tcl/Tix resource tree retains its upstream legacy utility data;
bytecode compilation covers the actual `runtime/Lib` import path and the examples.

The complete rc3 lifecycle passes at
`.qualification/v0.6/windows-lifecycle-v04rc3-final/result.json`. It installs the
actual Windows-tar-extracted release bytes, upgrades from 0.3.0, verifies Python
Run and debugpy with machine Python removed from PATH, then tests the optional
host wheel against exact image
`sha256:0eadf2e3b1e961a5e403b79b665e70b22c649179ccde40e86ffceae2ee7559ec`.
Native SPELL Run/export, breakpoint/stack/variable edit/Step/Continue, prompt,
Stop, plugin uninstall and ordinary Python afterward pass. An active private
interpreter blocks application uninstall before deletion; after stopping that
owned test process, both installed versions and the private Start menu shortcut
are completely removed. Project files, saved example edits and preferences are
unchanged. The [bound qualification manifest](IDE_V06_QUALIFICATION.json) verifies
both complete ZIPs, every payload hash, actual extraction and the child reports.

The initial rc3 desktop trial is also retained. Its Qt wait loop failed to yield
the Python GIL during a debugger wait. The corrected harness yields explicitly;
the same installed package passed immediately, and the complete lifecycle was
then rerun from a fresh directory. Application source and package bytes did not
change for this harness correction.

Actual installed v0.4rc1 evidence is in
`.qualification/v0.6/windows-desktop-v04rc1/result.json`: private-runtime Python
Run, debugpy breakpoint/stack/variables/edit/Step/Continue, Ctrl+Space insertion,
F12 navigation into an unsaved definition, read-only symbol navigation, 15 deep
Python chapters and graphics animation/control/close. These are actual Qt widgets
with an offscreen platform, not a noVNC screenshot or a clean-machine claim.

Use `scripts/distribution_installer_checks.py --output <new-directory>` for the
focused ownership tests. Use `scripts/distribution_qualify.py --bundle <bundle>
--previous-bundle <older-bundle> --output <new-directory>` for the actual private
installation lifecycle. The latter removes machine Python from PATH for ordinary
desktop checks, tests ignored Python environment injection, retains all logs, and
verifies user files survive removal. Its optional `--spell-host-wheel`,
`--spell-harness` and `--spell-image` arguments bind the sibling's actual installed
host workflows to the same bundled interpreter and an exact inspected image.

Candidate release versions remain prereleases while preceding gates are open.
Final candidate source/wheel identities, repeat-build hashes, real upgrade paths,
installed Python/SPELL workflows and removal must all bind to the same selected
release before final v0.6 acceptance.

## Collaborative debugging and interactive menu qualification

The v0.5rc1 installed lifecycle's first shared-debug trial used a 1.2-second
controller lease even during cold interpreter and debugger startup. That trial
failed with `Stale or missing controller token`; its record remains in
`windows-lifecycle-v05rc1`. A direct recheck passed all four shared-debug checks
against the same installed package. Neither result is rewritten.

The installed harness now uses the service's normal 30-second lease for startup.
At the first real breakpoint it releases the controller fence, configures the
isolated service's deliberate 1.2-second stress lease and claims through HTTP
again. A real 1.6-second debugger evaluation must complete while automatic
renewal preserves ownership. Variable editing, Step Into/Out/Over, monitor
inspection, explicit controller handoff and interactive input then complete.
`shared-v05-separated-leases/result.json` passes these four checks on the original
0.5rc1 private installation and records both lease settings. This qualifies the
normal startup configuration and subsequent short-lease renewal, without claiming
reliable cold startup under a 1.2-second scheduling deadline.

For the console fix, `distribution_menu.py` exercises copied packaged examples
through actual installed Run and Debug widgets. It types at the output prompt,
uses both Send and Return, runs menu choices 1–7 including nested topic/value
prompts, opens and closes the graphics child and exits normally. Source regression
tests reproduced ignored typing when the read-only output console had focus.
Ordinary typing now reaches the enabled input field; Send restores its focus.
Copy, selection, scrolling and disabled-input restrictions have separate checks.
Submitted answers are not echoed into the output history.

Use `distribution_qualify.py --shared-debug --console-menu` together with the
bundle, upgrade and optional native SPELL arguments for these installed checks.
The lifecycle retains exact harness sources, child reports and their hashes;
`distribution_record.py` verifies those bindings before recording prerequisites.
These offscreen checks do not substitute for the live browser or fresh VM gates.

## v0.6 candidate results

The frozen input wheel is `openbexi_ide-0.6.0rc1-py3-none-any.whl`, SHA-256
`4cf2046c53e259e6a20849ca0b0fd09c9aa5a0ab639d874c53d08ee5d56d8429`.
Both independent assemblies in
`.qualification/v0.6/windows-build-v06rc1-{a,b}/` produce
`OpenBEXI-IDE-0.6.0rc1-windows-x64.zip`, SHA-256
`6a2cf9c9a98569aea729a3dd0a5442b4e7ec8ed8c942993a8aa126963ed29a35`.
The 7,603 payload files include 1,700 deterministic owned bytecode files. Both
assemblies use the immutable candidate's packaging recipe, examples, source
snapshot and the exact locked runtime/dependency inputs.
The reproducibility claim binds those retained input bytes. The repository's
general PowerShell checkout rule currently converts LF to CRLF; a fresh Git
checkout therefore needs the exact archived recipe bytes to reproduce this ZIP.
A future checkout-rule correction requires a newly qualified candidate.

Windows system tar extraction at `windows-archive-v06rc1` verifies every payload
hash. The complete `windows-lifecycle-v06rc1/result.json` passes 19 checks: actual
0.5rc1-to-0.6rc1 upgrade; installed Python/debugpy and editor features; all menu
choices through Run and Debug; collaborative breakpoint, evaluation, variable
editing, stepping, monitoring and handoff; the five native SPELL host workflows;
active-process uninstall refusal; and complete removal of both versions and the
owned shortcut with user projects, saved examples and preferences unchanged.
The independent `installer-checks-v06-final` suite passes all eight ownership,
preservation and malformed-input checks.

The [qualification manifest](IDE_V06_QUALIFICATION.json) binds both ZIP hashes,
the extracted manifest, retained harness sources and all child report hashes.
It records `distribution_prerequisites_passed: true` and
`release_accepted: false`. This is a qualified 0.6.0rc1 distribution candidate;
the fresh Windows VM and earlier live noVNC acceptance gates remain open.
