# Repository consolidation and cleanup

This maintenance preserves the latest IDE and SPELL application code and all original acceptance limits. Full v0.8 remains unqualified; [current status](CURRENT_STATUS.md) retains the unresolved memory blocker. The READMEs include unchanged extracts of both requested architecture diagrams.

## Scope and decisions

- Consolidate all local and origin branch history into `main`, reviewing unique changes before merging. Preserve later integrated implementations. Keep branch names for recovery; merged branches are eligible for later deletion.
- Keep IDE tags `v1.2.1` and the requested `v1.2.9` once its identity is resolved. At inventory time no `1.2.9` or `v1.2.9` exists locally or on origin, so IDE tag deletion is deferred. Keep SPELL `v0.7` and `v0.8-rc1`. Never invent or repoint a release tag. Published releases/assets remain intact.
- Keep application source, acceptance and compatibility inputs, dependency locks, original source/manuals, current reproduction tools, credentials and active application state.
- Archive unique historical outputs, source-bound native binaries, relevant failed evidence, dirty worktree files and exact Git histories before removing redundant copies. Delete reconstructible caches and retired version-specific runner scripts only after reference review.
- Preserve the healthy desktop and project directories used by running services. Do not apply a global Docker prune or remove unrelated system resources.

## Verified external archive

Archive root: `F:\openbexi-archive\cleanup-20261106T0013` (outside both repositories).

`ide-before.bundle` and `spell-before.bundle` contain complete pre-cleanup Git history and refs. `initial-git-inventory.json` records exact worktree HEADs and dirty status; separate binary patches retain the three dirty SPELL worktrees. `archive-manifest.sqlite` maps every inventoried file to keep, Git-bundle recovery, unique archived object or reconstructible cache. `objects/*.zip` deduplicate archived bytes by SHA-256. `archive-verification.json` is written only after every stored object has been read back and hashed.

To recover tracked history, clone the matching Git bundle into a new directory and check out the worktree HEAD from the inventory. For generated/untracked material, use the archive's `restore_archive.py` with an explicit source root and a fresh destination. The manifest restores paths and verifies content hashes. Recover a removed runner with `git show <pre-cleanup-commit>:<path>`; the exact paths and commits are listed in `tracked-deletions.json`. Historical paths in immutable receipts map through the manifest; they are not evidence of currently live worktrees.

The inventory, branch disposition, reference audit, fresh-checkout results, deletion log and disk-space measurements are retained alongside the archive. Final measured outcomes are recorded below after verification completes. Detailed historical reports remain in the repository when current tests, provenance or recovery instructions depend on them.

## Qualification boundary

The original 2-second, 3-second and 1.5-second checks, validated `-g1` compiler optimization, 600-second complete foundation limit, full 300-second trace, 64 MiB growth, zero swap and both original one-hour scenarios remain binding. No acceptance test is disabled or weakened. No product memory correction, version promotion or production migration is part of this cleanup.
