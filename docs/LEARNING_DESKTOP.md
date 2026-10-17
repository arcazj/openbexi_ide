# Native learning desktop

The IDE 1.1 learning update combines the installed Python desktop with the
published v0.5 original native SPELL runtime. The companion host adapter adds
an explicit packaged-desktop backend; Windows and JetBrains continue to use
their existing Docker backend. No Docker daemon socket is exposed to the
desktop. Native procedures run under its user account in private project copies.

The packaged runtime has a separate Python environment to avoid conflicts with
the bounded Python SDK. Each local run owns its DSS, original-schema driver,
SQLite journals, listener, context and executor. Only one native procedure tree
can run at a time because the upstream listener uses its fixed local port.
Stop closes the tree and releases that slot. This is a Development teaching
environment for trusted procedures, not a security sandbox between desktop users.

Use the **SPELL language menu** launcher for native SPELL, or **Python learning
menu** for the 39 Python topics, 15 in-depth chapters and graphics. The selected
backend is visible in the IDE toolbar. `--runtime spell` also selects it from
the installed CLI. See the [workspace guide](../examples/README.md).

The desktop opens the Python IDE and `hello.py`. Each local editor tab keeps its
own runtime choice. New files default to Python; imports of an installed
backend's declared modules select that backend, so the SPELL examples select
SPELL automatically. You can override the selection for each tab. Opening
`hello.py` from a SPELL tab uses the ordinary Python worker and avoids starting
the native executor and simulator.

Interpreter selection validates CPython before changing the saved setting.
Selecting a package installer such as `pip3.13` shows a Python executable hint
and keeps the working interpreter. Saved pip selections recover to the project's
Python environment, or the installed desktop Python when no project environment
exists.

Build from explicit, already-qualified native and desktop images:

```powershell
python scripts/build_learning_desktop.py --plugin-root ../openbexi_spell_plugin `
  --native-image <qualified-native-image> --desktop-image <qualified-desktop-image>
```

The builder records immutable input/output IDs and runs the image assembly
without network access. Launch with Docker's `--init` option (as the existing
desktop does) so orphaned child processes are reaped. Bind noVNC to loopback,
retain UID 10003, drop capabilities and use `no-new-privileges`. Preserve the
existing workspace and preferences volumes when updating an installed desktop.

Startup publishes examples into the two collection folders. Replaced or retired
files are backed up under `.openbexi/example-backups/`; unchanged generated
`examples-<hash>` directories are removed only after their contents reproduce
the original publisher's hash. Modified generated folders are preserved in the
backup area. Repeated startup keeps subsequent user edits.

The 763-row feature catalogue links to exact published native v0.5 evidence.
The learning collection's assertions and 11-family tour are separate evidence.
The `Monitoring` teaching argument exercises real driver-side command denial;
approved immutable Execution and shared-session Monitoring remain separate
service workflows and require their corresponding configuration.

Validation utilities under `docker/` exercise installed Run/Debug, breakpoints,
native prompts and children, all procedures, Stop/rerun and concurrency, and
the X11 IDE UI. `native_manifest.py` records installed runtime identities; each
native run manifest includes its digest. Release qualification still performs
the full v0.6 build, install, upgrade and platform gates in the plugin repository.

The [learning validation record](LEARNING_VALIDATION.json) binds the 24 native
procedures and 47 Python source files to their tested contents. It records 39
individual Python topics, graphics in Run and Debug, concurrent Python sessions,
native Stop/rerun, migration preservation, and the installed UI checks. Raw
reports and screenshots are retained in `docs/evidence/learning/`.
