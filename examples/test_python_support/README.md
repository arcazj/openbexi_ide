# Python support procedures

Select **Python**. Run `python_menu.py` to choose a topic, run the 39-topic
reference collection, explore the 15 in-depth chapters, or open/update/close
the statistics dashboard.

Each `python_<topic>.py` file runs one topic independently and reports its
assertion count. Their shared, readable implementations live in `test_Python.py`;
use Debug and Step Into to inspect them. Topics include control flow, types,
functions, classes, decorators, generators, exceptions, context managers,
pattern matching, files, binary data, persistence, threads, processes, asyncio,
loopback networking and diagnostics. Optional platform capabilities are
reported explicitly when unavailable.

`test_Python_in_deep.py` covers 15 additional chapters. For scrolling practice,
add script arguments `--stream`, `200`, `--delay`, `0.05`, one per line.
`debug_demo.py` provides a small breakpoint and variable-inspection exercise.
`session_first.py` and `session_second.py` print independent counters. Submit
both in a shared session to explore queues and the parallel-procedure limit.

Two graphical procedures are included:

| File | Requirements | Controls and expected behavior |
| --- | --- | --- |
| `graphics_demo.py` | PySide6, included in the desktop | Animated history, histogram, phase plot and statistics; pause/resume, speed, amplitude, reset, add point and Close |
| `graphics_tkinter.py` | Tkinter/Tk, included in the desktop | Animated sine wave; Pause/Resume and window close |

Both accept `--close-after 2000` for a short automated opening/closing check.
For interactive use, omit it and close the window normally. Menus close their
owned graphics processes when exiting. General Python examples use temporary
files and loopback-only networking where needed. See `procedures.json` for
the complete file catalogue.
