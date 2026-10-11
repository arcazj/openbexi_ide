# Fresh v0.1 repository

Extracted from `openbexi_spell` commit
`d4b0ed98f186346ea9e9af53816af2578953042c` on 2026-10-10. The former `desktop/`
is now this repository's root. The Python reference procedure is now
`examples/test_Python.py`, making the test menu self-contained.

The distribution/desktop label is `openbexi_ide`; module names remain
`openbexi_ide` and `openbexi_runtime`. The CLI entry point is `openbexi`.
The desktop extra retains the original locked GUI/debugger dependencies.
All new packages use version 0.1.0. `MIGRATION.json` records original copied
file hashes; subsequent relocation, naming and session changes are in this Git.

Legacy monolith history, old release documentation, screenshots and backend/web
implementations are outside this fresh repository, recoverable from
`C:/projects/.openbexi-archive/20261010-split/legacy-history.bundle` and
`legacy-source-d4b0ed9.zip`. The bundle was independently verified and includes
branches, tags, stash and worktree heads. Existing remote Git is unchanged unless
the owner separately requests its migration.

The fresh repository carries only current product code, tests, dependency locks,
examples, license notices and current docs. Historical release hashes and native
SPELL compatibility are not relabelled as new v0.1 acceptance.

## GitHub publication

The independent repository is [arcazj/openbexi_ide](https://github.com/arcazj/openbexi_ide),
created privately on 2026-10-11. Its branch is `master` and its local remote is
`origin`. Publication preserves existing commits and tags. The user subsequently
deleted `arcazj/openbexi_SPELL` and `arcazj/openbexi_REI` on GitHub; authenticated
verification on 2026-10-11 confirmed both old names unavailable and both new
repositories present. Verified retirement backups and the local legacy directory
are retained. Removing that local directory requires the user's confirmation.
See [the current handoff](RESUME_V04.md).
