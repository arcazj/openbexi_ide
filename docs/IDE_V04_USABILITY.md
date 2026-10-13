# IDE v0.4 usability and examples

The implementation is a `0.4.0rc3` candidate. Final v0.4 acceptance is open
because actual X-button closure and mouse-wheel console scrolling through
`http://127.0.0.1:6080/vnc.html` remain unverified. The browser tools return no
connected browser, and the Windows computer-use helper reports its native pipe
unavailable. The HTTP page responds successfully; this is health evidence only.

## Editor assistance

- **Ctrl+Space** or **View > Complete Python name** shows source-local/project
  names, Python keywords and builtins. Enter/Tab inserts the selected name;
  arrow keys choose and Escape dismisses. Insertion remains one undo operation.
- **F12** or **View > Go to Definition** follows source definitions and supported
  project imports, including aliases, relative imports and reexports.
- **Ctrl+Shift+O** or **View > Project Symbols** searches project functions,
  classes and variables and navigates to their source locations.
- Open unsaved tabs supply their current contents, including a target definition
  which has not been saved. Navigation reuses an existing tab and preserves edits.

This is static source assistance. It never imports or executes project code.
Dynamic attributes and installed-library definition inference are unsupported.
Analysis runs off the GUI thread with limits of 2 MB per file, 20 MB per request
and 2,000 files/directories. Only one request and one latest queued request are
retained. Late results cannot insert into a changed, hidden, closed or read-only
editor. Monitoring/Execution keep their existing edit restrictions; source
browsing remains available.

## Examples and console

The [example guide](../examples/README.md) includes the asserted deep Python
chapters, the existing 39-topic reference suite, the graphics signal/history,
histogram and phase-portrait demonstration, and `test_spell.py` with explicit
original `spell.lib` imports. Original SPELL needs its separate native backend.

The console retains bounded history without moving a reader who has scrolled
up or selected text. **Latest output** resumes following new output. Tests cover
history pruning, wrapped lines, selection, keyboard scrolling and memory bounds.
Close/shutdown checks cover owned runtime processes, editor analysis and shared
controller disconnection. Openbox close/focus bindings and Alt+F4 are configured
in the browser lab. Actual noVNC pointer/wheel acceptance remains a separate gate.

Interpreter discovery uses the existing process-owner launch helper. On Windows
the child is assigned its job before its first thread resumes. This closes a
short-process race where a probe could exit before post-start job assignment;
that order reproducibly raises WinError 5 on an already exited process.
Windows thread enumeration types and API signatures are initialized once, so
concurrent probes cannot replace each other's ctypes pointer types. The runtime
check starts nine real probes across three concurrent workers.

The previous browser deployment preserved the active user desktop and its project
volumes. Examples are published to a content-versioned folder without overwriting
an existing folder or user edits. See [the retained deployment record](V05_PROGRESS.md).

## Qualification

The editor's final focused suite passed 17 tests with one Windows symlink check
skipped because the current account cannot create symlinks. Its actual
MainWindow workflow verifies completion and navigation to an unsaved definition.
The complete isolated candidate suite passed 70 tests with that one skip. It
includes real Python Run/Debug/Stop, two shared desktops, console history,
examples, project assistance and concurrent interpreter probes. The exact
wheel and input snapshot are bound in
[the qualification manifest](IDE_V04_QUALIFICATION.json). Installed distribution
workflows retain their separate results in the v0.6 distribution record.

The IDE and sibling SPELL plugin use independent release numbers. This candidate
does not promote the plugin's full v0.5 conformance or v0.6 distribution gates.
