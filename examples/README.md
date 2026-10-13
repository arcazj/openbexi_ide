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

`test_spell.py` explicitly imports `spell.lib` and original language functions.
Select the installed **SPELL** native backend in OpenBEXI, or use the native host
runner from an interpreter with `openbexi-spell-host` installed:

```powershell
python -m openbexi_spell_host.runner --project ./examples --program ./examples/test_spell.py
```

The configured Docker runtime must be available. The accepted local image is
`openbexi-spell-host:0.3.0`. The example exercises native data, TIME, Step and
shared data, then exports `test_spell_result.json` into the run artifacts. It
does not require DSS commands or an operator prompt. Running it under the bounded
SDK or ordinary Python fails with a backend-selection message. The browser lab's
bounded DSS session and this original native backend are separate runtimes.
