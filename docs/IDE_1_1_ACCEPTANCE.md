# OpenBEXI IDE v1.1 acceptance

The requested stable version is **1.1.0**, based on `1.2.0rc1` commit
`66dfffa5e8abbd048b9db38cbd6ecbefa998c93f`. The **1.1.0** artifacts pass all six
release gates. [The qualification manifest](IDE_1_1_QUALIFICATION.json) binds
their bytes to retained reports and previews. SPELL v0.6 remains paused;
its runtime feature work is excluded.

## Compatibility

| Component | Candidate / tested version |
| --- | --- |
| IDE and procedure service | 1.1.0 |
| Native host Python package | openbexi-spell-host 0.3.1.dev3 |
| Native container | openbexi-spell-host:0.3.1-dev3 |
| Native image digest | sha256:0518192b4748bd4f5fa2cef5daa4ebe5b884735f559636bce5ba0b4119355c79 |
| JetBrains plugin | 0.3.1-workspace.2 |
| IntelliJ IDEA | 2026.2.3, build 262.10968.63 |
| PyCharm | 2026.1.2, build 261.24374.152 |
| Python | CPython 3.13.15 |
| Qt | PySide6 Essentials 6.10.3 |

JetBrains' selected interpreter needs both the IDE core wheel and native host
wheel. The core has no Qt dependency; the desktop extra supplies Qt. Install the
ZIP through **Settings > Plugins > gear > Install Plugin from Disk**, then restart
the IDE. In **SPELL Runtime Settings**, select that interpreter and the image
listed above. Existing explicitly saved image settings are preserved.

## Manual coverage

The reference is SPELL GUI User Manual 2.4.4, especially tabular presentation,
item information, prompt inputs and execution controls.

| Behavior | Implementation |
| --- | --- |
| Execution layout | Python panes hidden in SPELL; execution, menu and instance strip retained; layout restored on leaving |
| Code/results | Captured source, native item/value/time/status, independent state/result/current-line colors |
| History | Durable SQLite notifications; recent instance strip; source and output restored after reconnect |
| Item information | Latest / History / Full; native SCount as EX; compound fields, stack and comments; paged records |
| Prompt inputs | Embedded choices, text, number, date and masked password; Reset / Commit / whole-procedure Abort |
| Ownership | One controller per procedure, multiple monitors; explicit claim/release; stale/duplicate prompt rejection |
| Native lifecycle | Run, Debug, breakpoints, Pause, Continue, Step, Step over, Abort and Abort-to-Run cleanup |
| Reconnection | Server owns execution; native/browser views reconnect without replay or automatic control claim |
| As-Run | Qt/browser export source snapshot and notifications through a fixed sequence boundary |
| Multiple instances | Eight live container instances, one running; packaged Linux native backend currently limited to one live instance |
| Remote browser | Mutual TLS, enrolled certificate identity, operator/monitor credentials and role/revocation checks |

Advanced Skip, Goto, Recover, Run Until, By Step, scheduling, shell and TC
confirmation are not implemented by this backend. They are reported unavailable.
The native debugger exposes current-frame variables and edits; full legacy shared
variables, domain navigation and editable executor-defaults panels are not claimed
as implemented. INTERRUPTED is a native paused-wait state; connection loss has its
own indicator. Reaching a line never implies item success.

## Qualification

Private builds, logs and captured previews are on **F:\openbexi-builds\ide-v1.1**.
The release includes `IDE_1_1_RELEASE_DOSSIER.json`, `release-check.json` and an
evidence ZIP. Extract the evidence beside the downloaded artifacts and run
`scripts/check_release.py --manifest IDE_1_1_RELEASE_DOSSIER.json --root .`
to verify their recorded hashes and gates.

Passing native checks include Windows and packaged Linux Run/Debug with five
prompts and visible children; Abort followed by Run; ordinary Python afterward;
desktop two-instance reconnect; actual IntelliJ and PyCharm debugger, prompts,
persisted item dialogs and reconnection; browser operator/monitor, colors,
reconnect, item dialogs and As-Run download. Authentication, ownership, native
acknowledgement ordering, durable history and mutual-TLS checks also pass.

The final full Windows suite passed **201 tests, 9 skipped**, in one process.
The full Linux suite passed **201 tests, 9 skipped**. Eight skips on each
platform concern the separately approved operational Execution-image profile.
Windows also lacks symlink permission; Linux skips Windows Job-object cleanup.
Earlier Windows attempts encountered asynchronous UI/probe timeouts while other
qualification jobs were running. Their reports are retained privately; the
final complete run has no failures. One test now waits for UI acknowledgement
before clicking Release. No production timeout was increased to conceal these
failures. Linux uses `--init` so native child processes are reaped.

The exact Windows ZIP passed fresh installation on a GitHub-hosted **Windows
Server 2025 Datacenter** VM: [workflow and retained results](https://github.com/arcazj/openbexi_ide/actions/runs/39091854219).
The harness verified all 7,757 payload files and exercised Python Run/Debug,
menus, shared debugging and complete removal. Independently, installation over
1.2.0rc1 passed on this development machine, preserving projects, saved examples
and preferences. Native Windows and packaged Linux workflows passed, including
Abort followed immediately by Run. Both final JetBrains SDK qualifications
passed 12 checks, including captured source after the original file moves.

Actual captured previews: [desktop prompt](evidence/ide-1.1.0/windows-native/run-prompt.png),
[desktop results](evidence/ide-1.1.0/windows-native/run-results.png),
[browser controller](evidence/ide-1.1.0/browser/controller-prompt.png),
[browser monitor](evidence/ide-1.1.0/browser/monitor-prompt.png),
[IntelliJ](evidence/ide-1.1.0/intellij/workspace-prompt.png), and
[PyCharm](evidence/ide-1.1.0/pycharm/workspace-prompt.png).

## Version migration and retirement

1. Install the explicitly selected 1.1.0 artifact. Package-version ordering treats
   1.1 as lower than 1.2.0rc1; do not rely on an automatic "newer version" check.
   For a Python environment, install the exact wheel with
   `python -m pip install --no-deps --force-reinstall PATH_TO_1_1_WHEEL`.
2. The Windows installer selects its package manifest explicitly and preserves
   previous version directories, user projects, preferences and execution records.
   Validate the downgrade in a private installation before changing the user's
   active installation. Restart desktop/JetBrains clients after updating both wheels.
   The launcher compares the service implementation fingerprint. It replaces an
   idle older service while preserving history, and refuses replacement while any
   native instance is live. The native update qualification tests both paths.
3. Stable [1.1.0 is published](https://github.com/arcazj/openbexi_ide/releases/tag/v1.1.0)
   with 16 verified assets. Both repositories' main branches contain the qualified
   changes. The release tag identifies IDE commit `8ec46d4`; the companion source
   archive identifies `6a00c5c`.
4. The old RC release, tag and 15 assets are removed. Local `dist/1.2.0rc1` and
   `.qualification/ide-1.2.0rc1`, the dedicated RC container, its image and its
   temporary base-image alias are removed. Shared Python/dependency caches were
   copied to `F:\openbexi-builds\ide-v1.1\shared-build-cache` and hash-verified.
   Source history, accepted historical evidence and both RC user-data volumes
   remain preserved. No global Docker/cache prune was performed.

Post-publication receipts: [release](evidence/ide-1.1.0/published-release.json),
[GitHub retirement](evidence/ide-1.1.0/rc-remote-retirement.json), and
[local retirement](evidence/ide-1.1.0/rc-retirement.json). The new Docker desktop
is healthy at <http://127.0.0.1:6091/vnc.html?autoconnect=1&resize=remote>.
