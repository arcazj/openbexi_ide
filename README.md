# OpenBEXI IDE

A CPython 3.13 desktop IDE with local and shared development, debugging and optional domain plugins.

## Current status

**Joint release on hold.** The tested candidate pairs IDE **1.2.2** (`fadac70d`) with SPELL **0.8.0** (`47e0cb37`) and simulator SDK **0.1.0**. Windows uses online installation. Published IDE 1.2.1 passed ordinary Python Run/Debug and stopped at native reservation. The candidate passed installed Windows native execution and browser handoff. Sustained memory, driver deadlines and inherited compatibility still block stable publication. [Qualification results](https://github.com/arcazj/openbexi_spell_plugin/blob/qualification/ide-spell-20261122/docs/v0.8/evidence/qualification-20261122/README.md)

Both five-minute sanitizer workloads exceeded the approved 64 MiB growth limit. Controller handoff grew by **259.07 MiB** and the installed IDE by **308.17 MiB**, with zero swap. The original one-hour runs remain gated. Full native compatibility, supported deployments, JetBrains host acceptance and independent security review remain open. [Qualification status](docs/CURRENT_STATUS.md) · [Roadmap](ROADMAP.md)

## Use and develop

[Desktop setup and recovery](docs/IDE_SPELL_V07.md) · [procedure workspace](docs/PROCEDURE_WORKSPACE.md) · [shared debugging](docs/shared-debugging.md) · [examples](examples/test_spell/README.md)

The existing local desktop at `http://127.0.0.1:6088` uses the v0.7 native baseline. Follow the setup guide for the matching release; desktop health does not establish v0.8 qualification. [Development dependencies and retained tooling](docs/DEPENDENCIES.md) describe fresh-checkout verification.

## Windows installation

For a staged Windows wheel, pass its manifest checksum to the online installer from PowerShell. The script creates a CPython 3.13 virtual environment and verifies the bootstrap and desktop wheels. [Installer](install.ps1) · [Installer dependency lock](requirements-windows-installer.lock)

```powershell
.\install.ps1 -Python C:\path\to\python.exe -IdeWheel C:\path\to\openbexi_ide-1.2.2-py3-none-any.whl -IdeWheelSha256 1d68d0a13f85a9e64a084757c6be280cdc2feb77d97027df0d98bfc2ebffb58f
```

## Architecture reference

[Supplied ZIP, provenance and scope](https://github.com/arcazj/openbexi_spell_plugin/blob/main/docs/v0.8/reference/README.md). Both images below are unchanged extracts of the user-supplied architecture release package. They describe design intent; [current status](docs/CURRENT_STATUS.md) defines implemented and qualified scope.

**Historical comparison (non-normative)**

![Historical SPELL and OpenBEXI v0.8 architecture comparison](docs/diagrams/release-package/previous_comparison.png)

**Proposed v0.8 server architecture**

![Proposed OpenBEXI SPELL v0.8 server architecture](docs/diagrams/release-package/v08_server.png)

[Documentation index](docs/README.md) links to setup, detailed evidence and historical records.
