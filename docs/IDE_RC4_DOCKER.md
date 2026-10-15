# IDE 1.0.0rc4 Docker candidate

Published as the [v1.0.0rc4 prerelease](https://github.com/arcazj/openbexi_ide/releases/tag/v1.0.0rc4)
on 2026-10-15. The annotated tag selects `cf9baca`; runtime and packaging
sources are unchanged from the qualified builds below. Release assets include
the Windows ZIP, IDE wheel, qualification records and SHA-256 checksums.
Fresh Windows installation remains required for stable acceptance.

The default `compose.yaml` builds the latest source as `openbexi-ide:1.0.0rc4`
and starts one desktop at <http://127.0.0.1:6080/vnc.html>. Its fresh workspace
opens `test_spell/spell_menu.py`. All SPELL procedure examples are in that folder.

The menu has eleven family demonstrations, a complete 763-entry reference
catalogue, native prompt/child options, and an explicitly confirmed local DSS
command. Unsupported operations report `UNAVAILABLE`. The browser SDK does not
implement the full original language, and native qualification remains separate.
See [procedure instructions](../examples/test_spell/README.md).

The Windows source suite passes 168 tests; nine are skipped: this account cannot
create symlinks, and eight Docker Execution tests require a separately selected
exact image. The focused example/publisher suite passes seven tests, including
cancelled and confirmed commands against a fresh DSS and preservation of edits.
The Linux suite also passes 168 tests with nine platform/profile skips. These
full suites precede the final native-menu correction; IDE/runtime code is
unchanged. The final image passes five installed SDK checks, all seven native
procedures against the separately selected native runtime, and actual Edge/noVNC
Run, Debug, Send/Enter, catalogue browsing, scrolling both ways and titlebar X.
Its installed headless and X11 collaboration checks pass as well.

Source commit `21948f3` produces image
`sha256:a73538066ea1eb5ae497f1c8ea6e47f3d298d074c66da36e9ab83adc4fa9aace`.
The native menu uses SPELL Display and its original NOACTION value (64); the
bounded SDK uses 0. Native run-all passes seven demonstrations and reports four
unavailable; SDK run-all passes six and reports five unavailable. Retained failed
attempts document the corrections. See [exact evidence](IDE_RC4_QUALIFICATION.json).

All 17 prior IDE containers have been removed. Their nine named workspace,
preferences and evidence volumes are retained. The new Compose project uses new
volumes; no old projects or service data are deleted. Historical images and
qualification records remain available. Exactly one replacement container,
`openbexi-ide-ide-1`, is healthy on loopback port 6080. The rc3 release dossier is historical
evidence and does not certify rc4; final v1.0 and full SPELL acceptance remain open.

Windows rc4 is also packaged. Two offline assemblies from `9dd968e` produced
identical ZIP bytes, SHA-256
`6a729a7a2208d3648d40f301371ba6aac081dc32d4c463a3148e44749ba59f1b`.
Windows system tar verified all 7,623 payload files. The actual rc3-to-rc4 upgrade,
Run/Debug menus, shared debugging, active-process protection and removal pass
14 lifecycle checks on this host. The builder now handles Windows paths longer
than MAX_PATH during atomic bytecode creation and payload assembly. See the
[Windows artifact and qualification record](IDE_RC4_WINDOWS_QUALIFICATION.json).
This is not a fresh Windows machine qualification.

The [rc4 release dossier](IDE_RC4_RELEASE_DOSSIER.json) now binds the Windows
artifact, Docker image, installed workflows and actual browser checks. All eight
Docker execution tests pass against the final immutable rc4 image. Combined with
the original Windows suite, this gives 176 passes and one symlink-permission
skip. `scripts/check_release.py` reports only the fresh Windows installation gate
as pending; it continues to reject final release acceptance.
