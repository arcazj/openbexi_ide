# Repository consolidation and cleanup

Both projects are consolidated on `main`. Latest application code, tests, compiler fixtures and original acceptance limits are preserved. **v0.8 remains unqualified**; the unresolved memory blocker is retained in [current status](CURRENT_STATUS.md). Both README diagrams and the supplied architecture ZIP are unchanged.

## Measured cleanup — November 6 UTC

- Removed **107 retired worktrees** and **236.69 GB (236,693,504,711 bytes)** of original project files after preservation and verification. The [cleanup receipt](maintenance/cleanup-20261106.json) records categories, remaining roots, retained paths and observed disk-space changes.
- Removed 47 stopped project containers, 25 inactive project volumes and obsolete image tags covering eight original image IDs. Verified exports retain their state. The desktop, current baseline/build images, credential volumes and unrelated resources remain intact; no global Docker prune or VHD compaction was performed.
- Removed [ten obsolete tracked runners/workflows](maintenance/retired-files-20261106.json). Current qualification tools, failed evidence, dependency declarations/locks, original manuals/source, compatibility fixtures and native binaries remain available. [Dependencies](DEPENDENCIES.md) identifies the retained tooling.
- Preserved active environments, preferences, application data, running service fixtures and special IPC nodes. Ordinary deletion leaves the recorded read-only remnants. Automatic approval review rejected forced removal with the reason **“blocked by policy”**; no permission or attribute bypass was used. The final check found no remaining temporary diagram copies; earlier blocked attempts remain recorded.

Logical file deletion and Docker reclamation are separate from net host free space. Archive growth and other host activity affect the measured C: and F: totals in the receipt.

## Verified recovery archive

Archive: `F:\openbexi-archive\cleanup-20261106T0013`. It contains **110 completed roots**, **933,404 file records** and **132,552 unique archived objects**. Every stored object's bytes passed SHA-256 read-back verification. Clean tracked files recover from complete Git bundles at the exact recorded commits; rebuildable caches are classified separately.

`archive-manifest.sqlite` maps original paths to Git history, archived objects, caches or retained state. `objects/*.zip` deduplicate identical bytes. `initial-git-inventory.json`, binary patches, native binaries and failed-run evidence preserve the original worktrees, including all three dirty SPELL trees. Recovery tests passed for both repositories and a dirty SPELL tree; 2,628 dirty-tree overlays were hash-checked and the modified evidence files matched byte for byte.

Use the archive's `restore_archive.py --root <original-path> --destination <new-directory>`. Optional `--include <relative-prefix>` restores a selected evidence subtree. Registered source worktrees have separate roots and exact commits. The archive's `ARCHIVE_README.md` gives examples, Docker recovery locations and verification records. Historical absolute paths in immutable receipts resolve through this manifest; they do not identify currently active worktrees.

## Branches and tags

All reviewed local/origin branches are ancestors of consolidated `main`; branch names remain available for recovery. [Branch decisions](maintenance/branch-integration-20261106.json) explain integrated and superseded changes. The historical `pathlib.Path` harness alias fixes a directly reproduced wildcard-modifier collision; product code is unchanged.

Historical `refs/remotes/recovery/*` pointers preserve earlier qualification experiments. They have no configured remote and remain in the Git backups for later investigation.

Requested IDE `1.2.9`/`v1.2.9` does not exist locally or on origin, so IDE tags remain pending identification. SPELL retains `v0.7` and `v0.8-rc1`; four obsolete nonrelease tags were removed. Exact original `v0.4.0`, `v0.5` and `v0.6` tags were restored to preserve their published releases. Release IDs and asset IDs/digests are unchanged. The choice about those three release-linked tags remains pending. No tag was invented or repointed.

## Fresh-checkout validation

- [SPELL reference Linux run](https://github.com/arcazj/openbexi_spell_plugin/actions/runs/42137659032): **1,823 foundation tests passed in 423.326 seconds**, zero failures/errors/skips, within the original **600 seconds**. Lint, formatting and types passed; 290 input hashes match committed Git blobs. All **27 concurrent-request/heartbeat cases** passed in 34.925 seconds with their existing bounds.
- [IDE reference Linux run](https://github.com/arcazj/openbexi_ide/actions/runs/42137624350): **304 passed** in 397.106 seconds, zero failures/errors, one original Windows-only exclusion. That exact case passed in the fresh Windows checkout (0.58 seconds).
- Fresh Windows builds and installed IDE/DSS CLI checks passed. The attempted native server CLI exposed its existing Linux `fcntl` dependency; that failed attempt is retained, and Windows native-server support is not claimed. Downloaded CI artifacts match GitHub SHA-256 digests and pass CRC verification.

The [validation receipt](maintenance/validation-20261106.json) binds these results to tested commits. The retained fresh-checkout workflows run manually; their temporary cleanup-branch triggers were removed. No test command or limit changed.

## Qualification boundary

Keep the validated `-g1` optimization and original **2 / 3 / 1.5-second** deadlines. The complete **303.491-second** Context/bridge trace grew **319,567,872 bytes** against **67,108,864 bytes (64 MiB)** allowed, with **zero swap**. No conforming correction is established. The 300-second memory gate must pass before both original one-hour scenarios; all eleven release groups remain open. This cleanup did not rerun either hour scenario or promote a release.
