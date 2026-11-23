# OpenBEXI IDE

A CPython 3.13 desktop IDE with local and shared development, debugging and optional domain plugins.

## Current status

**November 22 release decision — HOLD.** IDE **1.2.2** and SPELL **0.8.0** are the candidate pairing (IDE `3ec9d4d9` and SPELL `99686362`). The simulator SDK uses **0.1.0**. The installed Windows client and authenticated Chromium workspace can launch a native procedure and display its result. Published IDE 1.2.1 passed ordinary Python Run/Debug and stopped at reservation in the paired SPELL test. [Tested artifacts and limitations](https://github.com/arcazj/openbexi_spell_plugin/blob/qualification/ide-spell-20261122/docs/v0.8/evidence/qualification-20261122/README.md)

Both five-minute sanitizer workloads exceeded the approved 64 MiB growth limit. Controller handoff grew by **259.07 MiB** and the installed IDE by **308.17 MiB**, with zero swap. The original one-hour runs remain gated. Full native compatibility, supported deployments, JetBrains host acceptance and independent security review remain open. [Qualification status](docs/CURRENT_STATUS.md) · [Roadmap](ROADMAP.md)

## Use and develop

[Desktop setup and recovery](docs/IDE_SPELL_V07.md) · [procedure workspace](docs/PROCEDURE_WORKSPACE.md) · [shared debugging](docs/shared-debugging.md) · [examples](examples/test_spell/README.md)

The existing local desktop at `http://127.0.0.1:6088` uses the v0.7 native baseline. Follow the setup guide for the matching release; desktop health does not establish v0.8 qualification. [Development dependencies and retained tooling](docs/DEPENDENCIES.md) describe fresh-checkout verification.

## Architecture reference

[Supplied ZIP, provenance and scope](https://github.com/arcazj/openbexi_spell_plugin/blob/main/docs/v0.8/reference/README.md). Both images below are unchanged extracts of the user-supplied architecture release package. They describe design intent; [current status](docs/CURRENT_STATUS.md) defines implemented and qualified scope.

**Historical comparison (non-normative)**

![Historical SPELL and OpenBEXI v0.8 architecture comparison](docs/diagrams/release-package/previous_comparison.png)

**Proposed v0.8 server architecture**

![Proposed OpenBEXI SPELL v0.8 server architecture](docs/diagrams/release-package/v08_server.png)

[Documentation index](docs/README.md) links to setup, detailed evidence and historical records.
