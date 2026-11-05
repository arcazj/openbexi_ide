# IDE v1.2.1 and SPELL v0.8 current qualification status

Updated November 5, 2026 UTC, following the November 4 New York qualification session. **IDE v1.2.1 and full SPELL v0.8 remain unqualified. All eleven mandatory release groups remain open.** The latest evidence-backed decision is to continue qualification; stable SPELL v0.8 publication is blocked.

## Published artifacts and tested subjects

| Subject | Exact identity | Status |
| --- | --- | --- |
| Published IDE v1.2.1 | `08c314fb6b802b407cbabe01777072884d2b7504` | Immutable unqualified release |
| Published SPELL v0.8-rc1 | `ce45fa4fd31b77cb97a1ef3621aa3906d2c94dda` | Immutable unqualified prerelease |
| Hosted qualification subject | `efada98963a9d9debdbdca437b0e97246180a86f` | Bounded foundation and native passes |
| Local native subject | `c5529d02a49c89a8919b965ffb4eb43498eb0cdf` | Short native passes; 300-second memory failure |
| Verified IDE evidence commit | `9624c9009dcf70e0a7960de74763e9f64b0f1439` | Receipts verified against committed bytes |
| SPELL gate reconciliation | `039e4be9dd74f2626cde19c7f983735b717ba84f` | All eleven groups false |

[IDE release](https://github.com/arcazj/openbexi_ide/releases/tag/v1.2.1) and [SPELL prerelease](https://github.com/arcazj/openbexi_spell_plugin/releases/tag/v0.8-rc1) deliver source archives, Python packages and recovery/checksum records. They do not deliver a newly qualified full v0.8 native image or v1.2.1 offline desktop bundle. Server, host, shared and DSS packages use `0.8.0rc1`; the separate root SDK remains `0.1.0`.

No IDE runtime change or successor version was introduced in the reference-runner followthrough. Later documentation commits do not inherit a new executed-runtime identity. A required IDE fix must use separately versioned artifacts.

## Latest verified results

| Check | Result | Acceptance boundary |
| --- | --- | --- |
| Hosted foundation, [run 41958849238](https://github.com/arcazj/openbexi_spell_plugin/actions/runs/41958849238) | **1,818 passed**, zero failures/errors/skips, 461.451 seconds | Original 600-second suite budget; host Python 3.13.17 |
| Original native handoff and installed-IDE scenarios | **Both 45-second scenarios passed locally and hosted** | Bounded private native acceptance |
| Published IDE wheel | Fresh download matches its published SHA-256; all **61 installed payload files** match | Artifact and installed-payload integrity |
| Isolated local foundation | **Failed** at 600 seconds after 1,150 completed call passes and zero completed call failures | Incomplete session remains failed |
| Local sanitizer/no-swap handoff diagnostic | **Failed**: 256,954,368-byte growth over 303.153 seconds, versus 67,108,864 allowed | All eight original processes observed; zero swap and no OOM events |
| Original 3,600-second sanitizer/no-swap scenarios | Historical failures remain open | Both original sustained scenarios still require passing evidence |
| Release preflight | **Not eligible for publication** | All eleven full-release groups remain false |

IDE wheel SHA-256: `43bbc5cdae4e6bff9cf258faf9c28f778c7e8617df304ca93436ddceeb4df96b`.

The local helper now observes Docker-host process IDs/cgroups and uses a shared durable temporary path. That corrects the demonstrated observation/setup failures. It does not explain every earlier startup failure or resolve sustained memory growth. The storage control improved one audit case but left another slow; the complete foundation timeout remains unexplained. Sparse allocator observations show nearly stable live-byte medians alongside growing heap mappings, with offsets up to about 12 seconds. They do not establish a complete simultaneous decomposition or allocation-site cause.

## Full release acceptance

The original G0–G9/A–L requirements, F1–F10 review oracles, all 763 compatibility requirements, required concurrency, operation deadlines, 600-second foundation budget and original 45/3,600-second memory workloads remain binding. Native growth remains limited to 64 MiB; the resident peak budget remains 1,792 MiB inside the original 2 GiB no-swap recovery limit.

| Group | Status | Remaining acceptance |
| --- | --- | --- |
| `services` | Open | Bounded hosted foundation and native cohorts pass. Full independent deployed service/process, tenant isolation, partition and required controller/viewer acceptance remains incomplete. |
| `native_family` | Open | Original 45-second handoff/installed-IDE checks pass locally and hosted. Fresh 300-second handoff fails growth: 256,954,368 bytes versus 67,108,864 allowed. Sustained sanitizer/no-swap hours remain failed historical evidence; current full native semantics and sustained acceptance remain open. |
| `compatibility` | Open | All 763 requirements need current native/driver acceptance. Historical 555 bindings, 546 matches/nine drift and 46 missing historical hashes remain unreconciled; partial TIME/PY/DATA coverage is insufficient. |
| `driver_faults` | Open | Bounded driver and native subsets pass. Complete deployed DSS fault, uncertain effect, crash/partition/reconnect/cancel and unrelated-worker survival acceptance remains incomplete. |
| `ide_browser` | Open | Published IDE v1.2.1 pairing passes bounded installed native checks. Public connection/launch, full debugger/workspace/source/results, three browser identities, 20 observers, WSS recovery and Git conflict acceptance remain incomplete. |
| `compose` | Open | Existing prelaunch and legacy-native desktop evidence is retained. Full v0.8 native image with ten executions/20 viewers, authorization/egress, component faults, storage restore and authority fencing remains incomplete. |
| `kubernetes` | Open | Production-like NetworkPolicy-enforced cluster is unavailable; local docker-desktop API refused connection. Required real Jobs, RBAC/admission, node/DNS/DSS faults, storage recovery, restore, upgrade/rollback remain open. |
| `recovery` | Open | Component audit/ENOSPC evidence remains limited. Whole-deployment restore, fencing of old authority, durable audit capacity and sustained acceptance remain incomplete. |
| `security` | Open | Exact delivered dependency/SBOM/source/license/advisory disposition and full auth/replay/integrity/load acceptance remain incomplete. Mandatory independent implemented-system reviewer is unavailable. |
| `ci` | Open | Pinned hosted run 41958849238 passes 1,818 foundation cases with zero skips/errors/failures in 461.451 seconds and both original 45-second jobs. Local foundation still times out at 600 seconds. Full final-pair release CI is incomplete. |
| `packaging` | Open | Immutable unqualified IDEv1.2.1 and SPELLv0.8-rc1 source/wheels remain distinct from candidate runtime and helper images. Qualified full native image, portable complete dependency closure, offline bundles and clean final installed/downloaded acceptance remain incomplete. |

Historical compatibility capture validation remains separate from current native acceptance: 555 bindings retain 546 matches/nine drift, and 46 historical hashes remain unresolved. Earlier all-763 acceptance belongs to its original release artifacts. It does not qualify the current v0.8 pair.

## Environment and operational state

The hosted reference is Ubuntu 24.04 x86_64 with host CPython **3.13.17** and recorded before/after environment receipts. The successful hosted run still used different runner image revisions; packaged native/desktop Python versions are separate inputs. The local Docker desktop is Debian 13 x86_64 with CPython 3.13.15 and PySide6-Essentials 6.10.3. The environment matrix defines qualification targets, not completed platform support.

| Hosted job | CPU model | Runner image |
| --- | --- | --- |
| native-handoff | INTEL(R) XEON(R) PLATINUM 8573C | 20261026.354.1 |
| foundation | AMD EPYC 9V45 96-Core Processor | 20261101.360.1 |
| native-ide | Intel(R) Xeon(R) Platinum 8370C CPU @ 2.80GHz | 20261026.354.1 |

All three expose four CPUs and approximately 15.6 GiB RAM. These are observations, not a production minimum. CPU/image differences prevent attributing the foundation timing improvement solely to the Python pin.


At the verified checkpoint, **no qualification jobs remained active**, both temporary helpers were stopped and their durable volume/evidence was retained. The existing IDE desktop remained healthy at `http://127.0.0.1:6088`, container `openbexi-ide-spell-v08-qualification-ide-1`, image `sha256:711eeb330a8291bbdca6fa31705f2b922610ad724d2f6654732b2b7fe40ab6cf`. It contains the **v0.7 native baseline**, so desktop health does not establish joint v0.8 acceptance. Recheck live state before starting or stopping work.

The public v0.8 provisioning/runtime boundary remains disabled. Private retained-worker tests and existing-execution IDE controls do not provide complete public launch, graphical debugger, browser/WSS or deployment acceptance.

## Next work and recovery

1. Diagnose the local foundation latency and sanitizer memory retention, implement measured corrections and repeat affected original checks. Run one heavy suite per runner while preserving its required internal concurrency.
2. Require a credible short result before rerunning both original 3,600-second ASan/UBSan/no-swap scenarios with exact dependency bytes and complete audits.
3. Complete public IDE/browser, all-763 native/driver compatibility, full v0.8 deployment, restore/fencing, dependency/security and final packaging acceptance.
4. Obtain the production-like **NetworkPolicy-enforced cluster** and **independent implemented-system security reviewer**. The local docker-desktop API refused connection at the checkpoint. Internal/static review does not replace these resources.

The current continuation receipt is `F:/openbexi-builds/v08-qualification-20261104/RESUME_QUALIFICATION.json`. The verified raw checkpoint is under `reference-runner-20261105/` beside the worktrees: 2,285 inventoried files, 23 selected receipts checked against committed bytes and 69 comparison-evidence hashes verified. Its original manifest and `FINAL_CHECKPOINT.json` remain unchanged; subsequent documentation synchronization is recorded separately.

Use `ide-followthrough-final.bundle` and `spell-followthrough.bundle` with their documented prerequisite commits. Preserve earlier failed runs, the local backup/stash and all unique work. Published tags/assets and original unqualified disclosure remain immutable. Production migration remains unauthorized. No further routine owner confirmation is needed to continue already-authorized qualification work.

## Evidence and documentation scope

[Detailed source-bound qualification receipt](https://github.com/arcazj/openbexi_ide/blob/9624c9009dcf70e0a7960de74763e9f64b0f1439/docs/evidence/ide-1.2.1/reference-runner-20261105/qualification.json) records every result's subject, command, artifact hashes and limits. Historical reports, raw evidence, release manifests, compatibility captures and original acceptance contracts retain their identities and requirements. Current guide notices point here so dated development checkpoints cannot be mistaken for today's release state.


See [qualification environments](IDE_1_2_1_QUALIFICATION_ENVIRONMENTS.md), [server integration](v0.8/SPELL_SERVER_INTEGRATION.md), [published release scope](UNQUALIFIED_RELEASE.md) and the [companion SPELL status](https://github.com/arcazj/openbexi_spell_plugin/blob/qualification/v08-resume-20261104/docs/v0.8/CURRENT_STATUS.md).
