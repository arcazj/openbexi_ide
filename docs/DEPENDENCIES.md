# Dependencies and verification

The cleanup retains all dependency declarations, lock files, original source/manual inputs, patch recipes, compatibility fixtures, licenses, release-gate tooling and current deadline/memory diagnostics. Build caches and historical worktree copies are replaceable; source-bound results and failed evidence are archived with hashes.

| Dependency | Retained purpose / authoritative declaration |
| --- | --- |
| CPython 3.13 | Package constraint `>=3.13,<3.14`; reference Linux checks pin 3.13.17; existing local baseline uses 3.13.15 |
| setuptools 80.9.0 | Build backend in each `pyproject.toml` |
| PySide6-Essentials 6.10.3, debugpy 1.8.22, Pygments 2.21.0 | IDE desktop extras; do not remove the active desktop environment |
| pytest 8.4.2 | Original test runner |
| ruff 0.14.1, mypy 1.18.2, grpcio 1.84.0, protobuf 7.36.2 | SPELL `server/requirements-test.lock` |
| Docker Linux engine, native compiler and headers | Native fixtures, isolated execution and diagnostic reproduction; recipes pin their inputs |
| Original SPELL source and manuals | SPELL `docs/reference`; required for native builds, provenance and all-763 compatibility |

Use the repository's `pyproject.toml`, component manifests, lock files and Dockerfiles for the complete dependency closure; this table is an entry point, not a replacement lock file. Preserve optional Kafka, distribution and JetBrains dependencies when exercising those profiles. Credentials, active application data and unrelated host resources are outside cleanup deletion scope.

For IDE development, create a fresh Python 3.13 environment and install `.[desktop,test]`. The full Linux workflow also installs the pinned companion SDK and builds the offline execution image before `python -m pytest tests -q -W error`. See [fresh-checkout workflow](../.github/workflows/repository-verification.yml).

[Maintenance and recovery](REPOSITORY_MAINTENANCE.md) records the external archive and exact cleanup decisions.
