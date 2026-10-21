# OpenBEXI IDE 1.2.0 with SPELL v0.7

The Docker project and image are named `openbexi-ide-spell-v07`. This release
combines IDE 1.2.0, host/DSS bridge 0.7.0, the unchanged native source wheel
0.6.0 and the bounded simulator SDK 0.1.0. It retains white procedure rows,
one soft current-line highlight and green/red/amber result cells in both themes.

Download the image archive, Compose files and checksums from the
[1.2.0 release](https://github.com/arcazj/openbexi_ide/releases/tag/v1.2.0).
Verify SHA256SUMS, then run:

```powershell
docker load --input openbexi-ide-spell-v07-linux-amd64.tar.gz
docker compose -f compose.v07.yaml up -d --wait ide
docker compose -f compose.v07.yaml ps
docker compose -f compose.v07.yaml exec ide python -I /opt/test-lab/health.py
```

Open <http://127.0.0.1:6080/vnc.html?autoconnect=1&resize=remote>. Select the
SPELL launcher, open a native procedure, Run or Debug and answer its prompts.
The language menu and all 763 reference entries remain under `test_spell/`.
The repository's default `docker compose` command selects this same project.

Finish or abort procedures and stop the previous desktop before replacement.
The default volumes remain `openbexi-v1-final-workspace` and
`openbexi-v1-final-preferences`, preserving projects, settings and records.
Use `down` without `--volumes` to remove an old deployment. For an independent
desktop, set `OPENBEXI_WORKSPACE_VOLUME`, `OPENBEXI_PREFERENCES_VOLUME` and
`OPENBEXI_V07_PORT` before starting. The service publishes only on loopback.

Expected package versions:

```powershell
docker compose -f compose.v07.yaml exec ide python -c "from importlib.metadata import version; print(version('openbexi-ide'), version('openbexi-spell-host'))"
docker compose -f compose.v07.yaml exec ide /opt/spell-native/bin/python -c "from importlib.metadata import version; print(version('openbexi-spell-source'), version('openbexi-spell-dss'))"
```

The first command prints `1.2.0 0.7.0`; the second prints `0.6.0 0.7.0`.
The separate native interpreter preserves the original SPELL namespace.

## Offline rebuild

Load the IDE 1.1.0 dependency image and the SPELL v0.7 native runtime archive.
Download the matching host 0.7.0 and SDK 0.1.0 wheels. From this checkout:

```powershell
python scripts/build_v07_desktop.py --host-wheel PATH/openbexi_spell_host-0.7.0-py3-none-any.whl --sdk-wheel PATH/openbexi_spell_plugin-0.1.0-py3-none-any.whl
```

The builder checks exact image and wheel identities, disables network access
and retains logs and input hashes under `.qualification/spell-v07-desktop/`.

## Durable service recovery

The core CLI adds `openbexi backup` and `openbexi restore` for stopped durable
authorities. Restore requires a hash-bound operator receipt, a new directory,
verified worker shutdown and independent external-effect evidence. It preserves
uncertain intents, holds nonterminal work, advances the epoch, revokes historical
Execution approvals and never replays a procedure. Read the exact commands and
limits in the [SPELL v0.7 recovery guide](https://github.com/arcazj/openbexi_spell_plugin/blob/v0.7/docs/V07_INSTALLATION.md).

The Docker desktop runs the Development procedure workspace. Durable shared
Development, read-only Monitoring and approved Execution use the separately
installed shared provider and service-owned Docker workers; no Docker socket is
mounted into the desktop. The qualified domain is the GENERIC DSS simulator,
Linux x86_64 runtime and CPython 3.13. Real mission/RF operations and native
checkpoint resume remain outside this release.
