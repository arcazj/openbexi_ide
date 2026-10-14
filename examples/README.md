# Example workspace

Select **Python** for ordinary Python examples. `test_Python.py` retains the
39-topic reference suite; `test_Python_in_deep.py` adds 15 readable, independently
asserted chapters covering language constructs, advanced objects, generics,
generators, exception groups, asynchronous code and cleanup. It is a broad
language exercise, not an exhaustive test of CPython or its standard library.

Run `test_menu.py` for the interactive menu. Option 7 runs the new chapters.
Run `graphics_demo.py` for animated signal history, a histogram, a fading phase
portrait and live statistics. Pause/resume, speed, amplitude, reference visibility,
add-point and reset controls all operate locally. Close the window with **X** or
**Close**. The menu's existing start/update/close commands still work.

For scrolling practice, run `test_Python_in_deep.py` with script arguments
`--stream`, `1000`, `--delay`, `0.05` (one argument per line in the IDE dialog).
Scroll up and select text while output arrives. **Latest output** returns to the
bottom and follows incoming output. Output history remains bounded.

`test_spell.py` detects the installed SPELL profile and names it in the console.
In the supplied browser desktop, select **Python**: the SDK mode checks Display,
TIME and WaitFor without requiring a DSS connection. It writes a result labelled
`browser-sdk`; it does not claim native data or shared-data coverage.

With the installed **SPELL** native backend selected, the same file explicitly
imports `spell.lib` and runs the original native data, time and shared-data checks.
You can also use the host runner from an interpreter with `openbexi-spell-host`:

```powershell
python -m openbexi_spell_host.runner --project ./examples --program ./examples/test_spell.py
```

The configured Docker runtime must be available. The accepted local image is
`openbexi-spell-host:0.3.0`. The example exercises native data, TIME, Step and
shared data, then exports `test_spell_result.json` into the run artifacts. It
does not require DSS commands or an operator prompt. The browser lab's SDK and
the original native backend remain separate runtimes.

Additional procedures:

| File | Runtime | Exercise |
| --- | --- | --- |
| `spell_sdk_telemetry.py` | Browser Python / SDK with lab DSS | Read TM1 and verify its range; no commands |
| `spell_native_data.py` | Native SPELL | Typed data, procedure variables, UTC time, shared-data cleanup |
| `spell_native_time.py` | Native SPELL | Time arithmetic and a short relative wait |
| `spell_native_prompt.py` | Native SPELL | Two console answers and a JSON result |
| `spell_native_parent.py` + `spell_native_child.py` | Child-capable native host candidate | Child prompt, return, then parent prompt |

For native YES_NO prompts, send **0** for Yes or **1** for No. The parent example
requires the newer child-capable host runtime; the accepted `0.3.0` image does
not provide that workflow. All examples avoid spacecraft commands. New example
folders published to an existing Docker desktop preserve your edited files.
