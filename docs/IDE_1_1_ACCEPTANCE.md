# OpenBEXI IDE v1.1 acceptance

The requested stable version is **1.1.0**, based on `1.2.0rc1` commit
`66dfffa5e8abbd048b9db38cbd6ecbefa998c93f`. The current candidate is
**1.1.0** on `work/ide-v1.1`, prepared but unpublished. Stable publication is not yet approved by the
release checks. SPELL v0.6 remains paused; its runtime feature work is excluded.

## Compatibility

| Component | Candidate / tested version |
| --- | --- |
| IDE and procedure service | 1.1.0, unpublished candidate |
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
The evidence manifest will bind the final candidate bytes to their checks.

Passing native checks include Windows and packaged Linux Run/Debug with five
prompts and visible children; Abort followed by Run; ordinary Python afterward;
desktop two-instance reconnect; actual IntelliJ and PyCharm debugger, prompts,
persisted item dialogs and reconnection; browser operator/monitor, colors,
reconnect, item dialogs and As-Run download. Authentication, ownership, native
acknowledgement ordering, durable history and mutual-TLS checks also pass.

The initial Linux test container lacked an init process and accumulated zombies.
The corrected `--init` container passed all 199 tests with nine documented skips.
The final complete test runs and installable artifact checks are tracked separately.

The independent clean-Windows gate is **pending**. Local `Get-VM` reports
insufficient Hyper-V access. The dedicated GitHub Actions workflow downloads the
exact unpublished installer by asset ID and SHA-256, then runs its bundled
qualification harness on a fresh hosted Windows VM. A new folder on this
development machine does not satisfy that gate. Stable publication and
old-release retirement remain pending until the independent check passes.

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
3. Once stable 1.1.0 is published and migration passes, retire the old GitHub
   release/tag/assets and only the exclusively owned local RC builds, caches,
   image and containers. Preserve source history, accepted evidence, projects,
   preferences, records and shared dependencies. No global Docker/cache prune.
4. Retain the old artifacts until those conditions are met. This document does not
   claim that publication, migration or retirement has already happened.
