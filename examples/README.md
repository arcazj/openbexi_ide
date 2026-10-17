# OpenBEXI learning workspace

Start with `hello.py` using **Python**, or choose one of the two collections:

| Collection | Runtime selector | Start here |
| --- | --- | --- |
| [SPELL procedures](test_spell/README.md) | **SPELL** | `test_spell/spell_menu.py` |
| [Python support](test_python_support/README.md) | **Python** | `test_python_support/python_menu.py` |

The supplied learning desktop includes the original native SPELL runtime and
a fresh synthetic DSS for each local SPELL run. The **SPELL language menu**
desktop launcher selects the native backend automatically. Commands affect this
disposable simulator. Its payload, telemetry, limits and resources are real DSS
state accessed through the original driver protocol.

Use **Run** first. For **Debug**, click the editor gutter to add a breakpoint,
then inspect Variables, Step and Continue. Answer questions in the console
input field. Use **Stop** to end a procedure, then run it again. One native
procedure tree can run at a time in this desktop; children belong to that tree.

Native runs use private project copies. Result files and manifests are saved
under `.openbexi/runs/`; original procedures are not overwritten. Replaced
examples are preserved under `.openbexi/example-backups/`. The installation
record is `.openbexi/example-installation.json`. Edits made after installation
survive restarting the same desktop version.

The root contains `hello.py` and this README. Teaching procedures belong in
the two collection folders. Each folder includes a procedure catalogue with
purpose, prerequisites and expected results. Qualification results are tracked
separately from the examples and from the native language coverage catalogue.

The learning desktop is a local **Development** environment. Shared Monitoring
and approved immutable Execution workflows are separate service profiles;
switching a label in an example does not grant those modes.
