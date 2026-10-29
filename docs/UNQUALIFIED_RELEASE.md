# OpenBEXI IDE v1.2.1

**UNQUALIFIED — qualification incomplete.** Published at the owner's explicit request before mandatory acceptance is complete. No production qualification is claimed.

## Delivered scope

This release supplies the exact Git source archive, Python wheels and source distributions, a full Git recovery bundle, SHA-256 checksums, focused-test results and a release manifest. It does not supply newly built native Docker images or Windows/macOS offline desktop bundles. Historical release packages and test results do not qualify these new artifacts.

## Installation and verification

Use CPython 3.13 in an isolated virtual environment. Download the wheel(s), `SHA256SUMS.txt`, and `release-manifest.json` from this release. Verify checksums with `sha256sum -c SHA256SUMS.txt` after downloading all listed files. Install the appropriate wheel with `python -m pip install /path/to/package.whl`; install documented optional dependencies when using desktop or driver components. See the source README and component READMEs for configuration. The manifest distinguishes installed-package/CLI checks from focused regressions and full qualification.

## Known incomplete acceptance

Sustained native memory budgets, complete 763-requirement compatibility, deployed controller/recovery tests, portable dependency packaging, full license/advisory disposition, production-like Kubernetes and independent implemented-system security review remain incomplete or failing. Original sustained memory tests exceeded the 64 MiB growth limit by about 1 GB; short/component passes do not supersede those failures. Unpromoted CPython buffer and Qt derivative experiments are archived, not promoted into this release. No production migration is authorized.

## Recovery and remaining work

`branch-recovery.bundle` and `branch-heads.json` preserve repository branches before cleanup. Verify the archive and recover any branch using Git bundle tools and its recorded commit. Published tags and original release artifacts remain immutable. `prompt4v0.8-qualification.md` contains the full continuation plan and evidence pointers. Full acceptance results remain unchanged.

## Source selection and pairing

Based on `f56ac138166d73bb244972fdd72a015bcbcfeede`, plus the PID-namespace process ownership correction and its two regression files from `3df88b8c4f98fb03f3db57b0fe513af3f32bf13a`. The standard PySide6-Essentials 6.10.3 dependency and corresponding notices are retained. Experimental Qt/PySide derivative builds remain archived for qualification.

Install the wheel with its `desktop` extra to obtain the declared UI dependencies; use `openbexi-ide` to launch. Linux desktop operation needs a supported display and Qt system libraries. CLI import/help validation does not establish desktop or native-runtime acceptance.

Companion: [OpenBEXI SPELL v0.8-rc1](https://github.com/arcazj/openbexi_spell_plugin/releases/tag/v0.8-rc1). Package version `1.2.1` is not a qualification claim. Exact release commits and build results are recorded in each release manifest.
