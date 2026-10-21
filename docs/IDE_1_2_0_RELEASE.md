# OpenBEXI IDE 1.2.0 — SPELL v0.7

The `openbexi-ide-spell-v07:0.7.0` Docker image combines IDE 1.2.0 with the SPELL
v0.7 operational release. It preserves the existing workspace/preferences
volumes and the native procedure workspace, prompts, debugger, records and
browser monitor/control views.

Procedure rows stay white. Only the current line has a soft blue highlight;
result cells retain green SUCCESS, red FAILED/ERROR and amber WARNING/IN PROGRESS.
Light and dark themes retain readable black procedure text.

The core CLI adds offline authority backup and restore. Restore retains
uncertain-effect holds, advances the epoch and revokes historical Execution
approvals. Shared backend request admission is now atomic with pause. HTTP error
responses and shutdown pipes are closed cleanly.

```powershell
docker load --input openbexi-ide-spell-v07-linux-amd64.tar.gz
docker compose -f compose.v07.yaml up -d --wait ide
```

Open `http://127.0.0.1:6080/vnc.html`.

The release includes the desktop image archive, core/host/SDK wheels, Compose
files, source, evidence, manifests and checksums. See the
[setup and recovery guide](https://github.com/arcazj/openbexi_ide/blob/v1.2.0/docs/IDE_SPELL_V07.md),
[exact qualification](https://github.com/arcazj/openbexi_ide/blob/v1.2.0/docs/IDE_SPELL_V07_QUALIFICATION.json)
and [SPELL v0.7 packages](https://github.com/arcazj/openbexi_spell_plugin/releases/tag/v0.7).

The native source wheel stays at its accepted 0.6.0 baseline; the host and DSS
bridge are 0.7.0, and the independent simulator SDK is 0.1.0. Native execution is
Linux amd64 in Docker. No new Windows offline desktop bundle is included.
