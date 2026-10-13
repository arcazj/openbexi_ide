# v0.5 prerequisites and current work

The accepted baseline remains IDE v0.3 / plugin v0.4. Plugin v0.5 and v0.6 are
open. This checkpoint adds the requested examples and console behavior, and the
sibling plugin starts full inventory qualification. No v0.5/v0.6 release tag is
justified by this checkpoint.

Latest conformance checkpoint: 82/763 rows qualify, including 40/66 COMMON rows.
The remaining 681 rows and live noVNC verification keep the release open. See the
continuation below and the sibling `conformance/COMMON.md` for current evidence.

## Examples and console

`examples/test_Python_in_deep.py` has 15 asserted chapters covering major Python
3.13 constructs, advanced objects, generators, exception groups, generic syntax,
async contexts/tasks/cancellation, modules and cleanup. It adds paced output for
scrolling checks. The existing 39-topic reference suite remains available, and
menu option 7 runs the new example.

The graphics demo has live signal/reference history, a histogram, a fading phase
portrait, summary statistics and pause/speed/amplitude/reset/reference controls.
Its stdin add/close protocol and automatic-close option remain supported. The
final 900x720 rendering was inspected; control/animation/shutdown tests pass.

`examples/test_spell.py` explicitly imports `spell.lib` and original functions,
uses native DataContainer/Var, TIME, Step and shared data, cleans up its owned key,
and exports a result. It passes against the accepted native 0.3.0 image through
the original executor, with answer 42 and the terminal success marker. It needs
the original native backend; the browser lab's bounded SDK is a different runtime.

Console output follows the tail when the reader is at the bottom. Scrolling up
or selecting text keeps the reading position during new output, including bounded
history pruning. **Latest output** returns to following the tail. Tests cover
selection, keyboard scrolling, new output, pruning, memory bounds and resuming.

## Browser lab deployment and remaining verification

The running `openbexi-ide-test-ide-1` container was updated in place without
restarting its windows or services. Existing user project files and volumes were
preserved. New windows load the updated console; already open windows must be
closed and reopened to load it. The current examples are in:

`/workspace/projects/demo/examples-v05-15578957d475`

The durable project has the same named folder. Earlier example folders are
retained. Publication creates a content-versioned directory and never overwrites
an existing directory or its edits. New starts use the updated
`openbexi-ide-test:current` image; the original running image also retains the
`openbexi-ide-test:pre-v05-examples` tag.

Openbox now has explicit focus/raise bindings for client/title/close presses and
an Alt+F4 close binding. Application tests qualify close/shutdown behavior,
including closing a shared controller while preserving its paused worker.
**Actual X-button and mouse-wheel operation through noVNC remains unverified.**
The browser tool reported no browser, and the Windows computer-use connection
reported its native pipe unavailable after reconnect. The live health check
passes. Do not replace the missing browser evidence with the Qt tests.

## Evidence

- Linux lab: 100 tests passed, 9 skipped; installed CLI and X11 Qt shared workflows
  passed. Eight skips need the external Docker Execution fixture; one is
  Windows-only. Evidence is under `.qualification/v0.5/lab/evidence/`.
- Windows focused UI/runtime/session suites: 13 and 32 checks passed. Four final
  graphics/example checks pass in `.qualification/v0.5/examples-final.xml`.
- The sibling native example report is
  `../openbexi_spell_plugin/.qualification/v0.5/native-examples/79151b8cd08a4685b656e244b77c4dba/result.json`.
- The sibling plugin's 204 existing unit tests and six new release-gate checks
  pass. TIME has 168 native checks for 42 rows, with source/image bindings in
  `../openbexi_spell_plugin/conformance/evidence/time.json`.
- Native host regression on the patched TIME development image passes all ten
  DAP cases. All nine native driver cases pass in
  `.qualification/v0.5/native-driver-regression-final.xml`, including immutable
  approved Execution, revocation, fencing, pause, uncertainty and TIME deadlines.
  The earlier attempt exposed an unclosed SQLite connection in the test's receipt
  reader; it was explicitly closed before the successful rerun.
- Wrapped output retention and preservation of edited published examples each
  pass their focused regression checks.

## Continue

The subsequent sibling [COMMON milestone](../../openbexi_spell_plugin/conformance/COMMON.md)
qualifies 40 of its 66 rows and resolves its two manual/source errata. The native
wrapper now separates result/failure prompts, validates policies and handles
configuration for functions absent from language.xml. Actual native IPC verifies
silent text/item feedback while preserving data effects and system diagnostics.
Six fresh native procedures verify abort, cleanup, error propagation, recovery
and configuration isolation. The combined image passes all 168 TIME checks, ten
native host tests and all nine driver tests; the latter evidence is
`.qualification/v0.5/common-native-driver-final.xml`.

The combined DSS development image is `openbexi-spell-dss:v05-common`, exact ID
`sha256:34d20137501f19e34c46bda10022b7fd7eb2ff8b6a2aad47d9b6f6c65e643266`.
The accepted v0.4 image and active browser lab were preserved. A fresh browser
inventory still reports no connected browser, so live X/wheel verification
remains open.

Read the sibling `conformance/README.md`, run its release gate, then continue the
681 open rows in `conformance/coverage.json` (82/763 qualified). The 26 remaining
COMMON rows have service-family dependencies listed in `conformance/COMMON.md`.
Keep independent positive, boundary,
failure and recovery evidence, resolve all source/manual conflicts, and preserve
the accepted v0.3/v0.4 artifacts. Full driver semantics, native control/recovery,
databases, files, prompts, limits and specialized services still gate v0.5.
Complete v0.5 before accepting v0.6 distribution and host compatibility.

Preserve `C:/projects/openbexi_spell`, the legacy archive, all `.qualification`
evidence and the user's active browser desktop. Its absence from the current
release scope is not permission to delete it.
