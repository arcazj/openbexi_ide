# OpenBEXI IDE 1.1.1 with SPELL v0.6

The Docker desktop combines IDE 1.1.1 with the published SPELL 0.6.0 host,
native executor and DSS bridge. It uses the accepted v0.6 native image
`sha256:ef97426030ab9db06f573710ebbec56ff2486ed558697c058ce9d724c9036100`.
The native runtime is Linux x86_64, CPython 3.13.15, GENERIC simulator,
ASan/UBSan with leak detection disabled. The IDE's Development workspace keeps
its existing execution and service-restart limits.

Code rows stay white. Only the currently executing line receives a soft blue
highlight; previous lines return to white, including after completion or abort.
Result cells retain green SUCCESS, red FAILED/ERROR and amber WARNING/IN PROGRESS.
Text stays black and readable in light and dark themes. Procedure status colors
appear in the state badge.

## Start, stop and verify

Download the image, Compose files and SHA256SUMS from the
[1.1.1 release](https://github.com/arcazj/openbexi_ide/releases/tag/v1.1.1).
Verify their hashes, then run:

```powershell
docker load --input openbexi-ide-1.1.1-spell-v0.6-linux-amd64.tar.gz
docker compose -f compose.v06.yaml up -d --wait ide
docker compose -f compose.v06.yaml ps
docker compose -f compose.v06.yaml exec ide python -I /opt/test-lab/health.py
docker compose -f compose.v06.yaml exec ide python -c "from importlib.metadata import version; print(version('openbexi-ide'), version('openbexi-spell-host'))"
docker compose -f compose.v06.yaml exec ide /opt/spell-native/bin/python -c "from importlib.metadata import version; print(version('openbexi-spell-source'), version('openbexi-spell-dss'))"
```

Expected package versions: IDE `1.1.1`; host, source and DSS `0.6.0`.
Open <http://127.0.0.1:6080/vnc.html?autoconnect=1&resize=remote> and select the
SPELL launcher. Open a native example, Run or Debug, answer its prompts and
inspect the results. Stop and restart without removing saved files:

```powershell
docker compose -f compose.v06.yaml stop
docker compose -f compose.v06.yaml start
```

The repository's default `docker compose` command uses the same deployment.
`OPENBEXI_V06_PORT` selects another loopback port. The default volume names
preserve the previous desktop's workspace and preferences:
`openbexi-v1-final-workspace` and `openbexi-v1-final-preferences`.
For a fresh independent desktop, set `OPENBEXI_WORKSPACE_VOLUME` and
`OPENBEXI_PREFERENCES_VOLUME` to new names before starting.

Finish or abort procedures and stop the previous desktop before replacing it.
Use `down` without `--volumes` when removing an old deployment. Existing user
projects, preferences and procedure records are preserved.

## Offline rebuild

Load the published IDE 1.1.0 Linux image archive and SPELL v0.6 runtime archive.
These provide the exact desktop dependencies and accepted native input. Download
the published `openbexi_spell_host-0.6.0-py3-none-any.whl` and
`openbexi_spell_plugin-0.1.0-py3-none-any.whl`, then run from this
checkout using a CPython 3.13 interpreter:

```powershell
python scripts/build_v06_desktop.py --host-wheel PATH/openbexi_spell_host-0.6.0-py3-none-any.whl --sdk-wheel PATH/openbexi_spell_plugin-0.1.0-py3-none-any.whl
docker compose -f compose.v06.yaml up -d --wait ide
```

The build checks both image identities and the accepted host/simulator wheel hashes. It
uses networking disabled and copies the native runtime/adapter from the accepted
image, without rebuilding or changing SPELL v0.6. Build logs and source hashes
are written under `.qualification/spell-v06-desktop/`.

## Scope

This IDE patch updates Docker integration and Qt/browser presentation. It does
not replace the accepted SPELL v0.6 tag or promote the plugin's v0.7 operational
qualification. The core wheel can update an existing desktop interpreter with
matching dependencies. No new Windows offline bundle or JetBrains ZIP is part
of this Docker-focused patch.
