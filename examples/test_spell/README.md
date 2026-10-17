# Native SPELL learning procedures

Select **SPELL**, then run `spell_menu.py`. It offers all 11 language families,
the full reference catalogue, individual procedures, prompts, child workflows,
and command/telemetry examples. `spell_all_features.py` runs the 11-family tour
without menu input. `test_spell.py` is the short smoke procedure.

Start with `command_wait_telemetry.py`: it checks payload OFF, sends `CMD1`,
waits for ON telemetry, sends `CMD2`, then verifies OFF. The loop has a bounded
number of samples and reports intermediate readings. Other procedures cover:

`command_temperature_ramp.py` waits for three distinct rising temperature
samples after commanding and then switches the payload off again.

- A `for` loop waiting for simulator tick changes; raw/engineering telemetry;
  true/false and compound verification conditions; expected wait timeout.
- Command arguments, command groups, unknown-command rejection, SAFE-mode
  execution failure and recovery to NOMINAL.
- Ground parameter injection, alarm thresholds, restoration of normal limits,
  typed resources and the ranging service lifecycle.
- Native data containers, variables, shared data, time arithmetic, files,
  procedure steps, successive prompts and parent/child control flow.

Expected failures are caught and followed by assertions and recovery. A passing
example ends with a `SPELL_…_PASS` marker. An uncaught exception or nonzero exit
is a failure. `stop_and_rerun.py` is an interactive Stop exercise; it otherwise
ends after 60 samples. Prompt procedures describe their answers in the console.

`procedures.json` lists every procedure and its prerequisites. Each local run
gets a fresh synthetic GENERIC DSS with a half-second clock, payload initially
disabled, and the teaching resource `value` initially 21. Results go to the
project's `.openbexi/runs/<run>/artifacts/` directory.

`feature_catalog.json` maps **763 qualified native requirements** to the exact
published [v0.5 evidence](https://github.com/arcazj/openbexi_spell_plugin/releases/tag/v0.5).
Those results are separate from the learning examples: an 11-family tour does
not rerun all 763 requirements. v0.6 release qualification also checks packaging,
installation, upgrades and supported IDE workflows.

The compatibility files `test_spell.py`, `spell_menu.py` and
`spell_sdk_telemetry.py` can also identify the older bounded Python SDK. Use
**SPELL** for the complete native collection. Python SDK availability is not
evidence that a native feature passed.
