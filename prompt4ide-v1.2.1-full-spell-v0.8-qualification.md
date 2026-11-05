# Qualify OpenBEXI IDE v1.2.1 and full SPELL v0.8

Continue the implementation and qualification of **OpenBEXI IDE v1.2.1 with full OpenBEXI SPELL v0.8** from the latest verified worktrees and evidence. Complete the actual native, installed IDE, browser, deployment, recovery, compatibility and security acceptance. Do not stop at a plan, another assessment, a desktop launch, short native tests or documentation updates.

The requested unqualified releases already have recorded publication and download receipts. Preserve them and resume qualification. The objective is an evidence-backed qualification decision for the exact IDE v1.2.1 artifacts and a fully qualified SPELL v0.8 release. If completing mandatory functionality requires changing IDE runtime or dependency bytes, retain an honest v1.2.1 result and qualify a separately versioned compatible successor. Never label changed artifacts as the original v1.2.1 release.

## 1. Resume from the latest checkpoint

Start with these local locations:

- Published IDE checkout: `C:/projects/openbexi_ide`.
- Published SPELL checkout: `C:/projects/openbexi_spell_plugin`.
- Active IDE worktree: `F:/openbexi-builds/v08-qualification-20261104/ide`, branch `qualification/v121-resume-20261104`.
- Active SPELL worktree: `F:/openbexi-builds/v08-qualification-20261104/spell`, branch `qualification/v08-resume-20261104`.
- Current continuation receipt: `F:/openbexi-builds/v08-qualification-20261104/RESUME_QUALIFICATION.json`.
- Detailed report: `docs/evidence/ide-1.2.1/local-docker-20261104/qualification.json` in the active IDE worktree.
- Hosted job receipts and downloaded artifacts: `ci/`, `ci-d73b619/`, `ci-337f7336/` and `ci-c5529d02/` under the same qualification directory.
- Earlier release synchronization: `C:/projects/openbexi_ide/.qualification/github-v1.2.1-sync-20261104222747/SYNC_COMPLETE.json`.

The following identities come from the checkpoint recorded at **2026-11-05 00:24:48 UTC**, the evening of November 4 in New York. Reconcile them with current local and remote state before making changes; do not treat a checkpoint as a live job or branch inventory.

| Subject | Recorded identity | Scope |
| --- | --- | --- |
| Published IDE `v1.2.1` | `08c314fb6b802b407cbabe01777072884d2b7504` | Immutable unqualified source and artifacts |
| Published SPELL `v0.8-rc1` | `ce45fa4fd31b77cb97a1ef3621aa3906d2c94dda` | Immutable unqualified source and artifacts |
| SPELL qualification candidate | `c5529d02a49c89a8919b965ffb4eb43498eb0cdf` | Later qualification corrections and heartbeat diagnostics |
| IDE Docker build commit | `1eeff792bd105b0e3aaed6f926ff7c024e1a2493` | Qualification packaging using published wheels |
| IDE evidence commit | `b43756f36f1ff2ee04815b22d203b931944680b1` | Latest recorded local Docker and hosted evidence |

Reference links:

- [IDE v1.2.1 release](https://github.com/arcazj/openbexi_ide/releases/tag/v1.2.1).
- [SPELL v0.8-rc1 prerelease](https://github.com/arcazj/openbexi_spell_plugin/releases/tag/v0.8-rc1).
- [Recorded qualification report](https://github.com/arcazj/openbexi_ide/blob/b43756f36f1ff2ee04815b22d203b931944680b1/docs/evidence/ide-1.2.1/local-docker-20261104/qualification.json).
- [Latest recorded hosted run 41937866009](https://github.com/arcazj/openbexi_spell_plugin/actions/runs/41937866009).

Inspect repository instructions, worktree status, unique local changes, branch lineage, remote heads, PRs, tags, release assets and active jobs. Reuse the active qualification worktrees when they remain valid. The primary checkouts were detached at the published tags; do not overwrite them with candidate work. Preserve `C:/projects/openbexi_spell_plugin_local_backup_20261104`, its recorded stash and all unique JetBrains changes. Do not blindly merge archived experiments or restart completed publication work.

Read the actual gate contracts in the SPELL worktree: `docs/v0.8/RELEASE_GATES.json`, `STATUS.json`, `TEST_REPORT.md`, `ACCEPTANCE_PLAN.md`, `NATIVE_RESOURCE_ACCEPTANCE.md`, `SPELL_COMPATIBILITY_MATRIX.md`, `DRIVER_COMPATIBILITY.md`, `IDE_PAIR.json` and their current receipts. Read the IDE's `docs/v0.8/SPELL_SERVER_INTEGRATION.md` and relevant installed-workspace qualification documentation. Some documents contain older dev snapshots; reconcile their status text with newer receipts while preserving their acceptance requirements.

Use `prompt4v0.8-qualification.md` for historical evidence recovery pointers, including the Library main checkpoint, receipt and supplemental volume index. Recover historical material needed for a concrete investigation; do not spend the entire continuation re-inventorying archives. Keep historical recovery separate from fresh replacement evidence, and preserve missing-hash findings until actually resolved.

## 2. Preserve the established scope and authorization

Continue the previously authorized implementation, tests, qualification CI, commits and permitted release integration. Existing authorization permits qualified SPELL `v0.8` publication and its compatible IDE release only after every mandatory criterion passes at the delivered identities. Production migration remains unauthorized. Respect repository protections and authentication requirements.

Keep published tags, original assets and their original **UNQUALIFIED — qualification incomplete** disclosure immutable. The recorded IDE wheel SHA-256 is `43bbc5cdae4e6bff9cf258faf9c28f778c7e8617df304ca93436ddceeb4df96b`; re-download and verify it against the release manifest before installed acceptance. SPELL `v0.8-rc1` maps to server/host/shared/DSS package version `0.8.0rc1`. The separate root SDK remains `0.1.0` and is not the native runtime.

Keep four subjects distinct in every report: published artifacts, candidate implementation, qualification tooling, and deployed native/dependency bytes. Source-only evidence, package import, offscreen startup and component tests each have limited scope. A gate passes only when its real required boundary passes.

## 3. Retain the current results and address the actual failures

Verify the raw receipts behind these recorded results before reusing them:

| Evidence | Recorded outcome | What remains open |
| --- | --- | --- |
| Hosted SPELL candidate `c5529d02…` with published IDE | 1,815 foundation tests passed; original native handoff and installed-IDE 45-second jobs passed | Sustained hours and all eleven full-release groups |
| IDE Windows source suite | 305 collected, 31 skipped, no failures or errors; 274 passed | Skips retain their reasons and cross-platform evidence |
| IDE Linux full suite | 304 passed, one Windows Job ownership skip, no failures or errors | Full joint v0.8 installed acceptance |
| Local desktop checks | Eight checks passed; installed published Python wheel bytes verified | Image uses the packaged **v0.7 native baseline**, not a qualified v0.8 native runtime |
| Local Compose prelaunch | Passed | Actual native workload, failure, authority and recovery acceptance |
| Final local foundation run | 600-second timeout; 1,148 completed call passes and two completed call failures | Complete successful run under the unchanged budget |
| Isolated driver follow-up | Two cases passed after competing suites stopped | Does not replace or explain the complete failed run by itself |
| Instrumented local native attempt | Failed before `native-child-running`; Context requests timed out; five heartbeat renewals and zero heartbeat failures | Root cause and full native acceptance |

The failed local foundation run overlapped the complete IDE Linux suite. Treat contention as a hypothesis requiring measurement. Healthy controller heartbeats do not establish healthy Context or DSS request processing. Preserve earlier tmpfs audit rejection, network-pool exhaustion, ownership-restoration failure, DNS failure, session-loss/member-binding rejection and all subsequent failures with their original identities.

The recorded local desktop is at `http://127.0.0.1:6088`, container `openbexi-ide-spell-v08-qualification-ide-1`, image `sha256:711eeb330a8291bbdca6fa31705f2b922610ad724d2f6654732b2b7fe40ab6cf`. Verify its current state and ownership before using or stopping it. The durable native helper was `openbexi-v08-qualification-durable2-20261104`, with workspace `/var/lib/docker/volumes/openbexi-v08-qualification-20261104/_data/spell`. Do not assume that helper is still running. The checkpoint recorded no active qualification sessions; query again before launching duplicates.

## 4. Resolve local native startup and foundation latency first

1. Establish reproducible input identities and runner prerequisites: installed Python/Qt/native libraries, image digest, source hashes, Docker storage backing, available CPU/RAM/PIDs, filesystem permissions, DNS and networks. Preserve durable audit storage. Reuse the verified helper fixes, including descendant reaping with Docker `--init`, without changing the original 512 PID limit or 600-second foundation budget.
2. Reproduce the local child-startup failure on the exact candidate. Capture timestamped Context, Listener, Executor, bridge and DSS events, request IDs, queues, stacks, controller epochs, process lifetimes and service latencies. Identify where the first delayed or rejected operation occurs. Separate admission, service scheduling, controller liveness, worker identity and transport failures.
3. Compare an idle runner with a controlled IDE workload using the same inputs and limits. Record CPU, memory, I/O, scheduling and request latency together. Avoid accidental simultaneous heavy suites during the isolation experiment. Then exercise the concurrency required by the acceptance contract; an idle-only pass does not establish load acceptance.
4. Fix the demonstrated product or harness defect, add a regression that reproduces it, and rerun the affected original checks. Do not increase timeouts, reduce workloads, remove assertions or convert failures into skips. Label harness changes separately from product changes.
5. Complete a successful local foundation run and actual v0.8 native handoff/installed-IDE acceptance. Retain full journals and unsuccessful attempts. Revalidate hosted behavior after relevant corrections instead of transferring the old hosted pass to a new candidate.

Use existing entry points after checking their current options and prerequisites: SPELL `scripts/qualify_v08_server.py`, `scripts/qualify_v08_native_launch.py --native-handoff`, `scripts/qualify_v08_native_launch.py --native-ide`, and `.github/workflows/v08-qualification-resume.yml`. Do not run Linux-only server suites directly on Windows or mistake missing Qt prerequisites for a product result.

## 5. Close the sustained memory gate with measured fixes

Both original sustained native scenarios still require acceptance. Prior sanitizer/no-swap hours grew by roughly 1 GB and failed the unchanged **67,108,864-byte growth limit** and applicable peak budgets. Short native passes, optimized-hour passes and allocator diagnostics do not close this gate.

Measure synchronized process, mapping, allocator and cgroup samples for the actual Context, bridge and Executors. Distinguish live allocations, allocation/free churn, allocator or sanitizer retention, thread resources, shared mappings, filesystem cache and durable audit growth. Verify observer attachment and coverage. Do not sum overlapping categories or samples taken at different times.

Use short original workloads to reject candidates before spending an hour on a known failure. Implement fixes at measured ownership/allocation paths, with bounded retention, correct lifetime, reentrancy, threading and failure behavior. Preserve the LINE, cancellation, callstack, request-ID, bridge ownership, STATUS race, live ACK, event-category, startup ACK and graceful-shutdown corrections already integrated.

Do not promote the archived CPython smaller-buffer experiment unless its reproduced escaped-view/use-after-free defect is fixed and verified, including custom method lookup, retained views, partial writes, retries, reentrancy, allocator domains and allocation failure. Component allocation reductions do not prove whole-runtime stability. Likewise, a QtCore-only rebuild does not qualify a complete Qt/PySide dependency distribution.

Once the candidate merits sustained testing, run both original **3,600-second ASan/UBSan, no-swap** scenarios, native handoff and installed IDE, against the exact candidate and actual delivered dependency bytes. Inspect `scripts/qualify_v08_memory_comparison.py` and the hour workflow source pins before dispatch. Preserve original workloads, concurrency, deadlines, samples, audit retention, growth and peak limits. No forced allocator purges, reduced sanitizers, unaccounted relocation or discarded samples may create a pass. Validate complete audit and result journals as well as memory outcomes.

## 6. Complete all mandatory release groups

Use the eleven keys in `RELEASE_GATES.json` as the acceptance ledger. For every group record the requirement, implementation status, exact test subject, command/workflow, outcome, receipt and remaining work. Preserve the underlying G0–G9/A–L requirements and F1–F10 review oracles in `ACCEPTANCE_PLAN.md`; the table below summarizes them without narrowing them.

| Group | Required acceptance |
| --- | --- |
| `services` | Independent Listener, Context, Executor and DSS processes; authenticated discovery; tenant/configuration/credential isolation; reconnect and service restart; ten distinct native procedures and 100 competing starts of one logical procedure; one active instance per logical procedure with actual process/Pod proof |
| `native_family` | Original native and child-procedure semantics; pause/quiescence, step, prompts, abort/close and terminal cleanup; ownership through child/double-fork/setsid cases; both sustained memory scenarios and complete audits |
| `compatibility` | All **763** inherited requirements mapped to immutable source and fresh native/driver evidence; historical capture validation kept separate; unsupported or unimplemented required behavior remains a gap |
| `driver_faults` | Original Driver contract, independent DSS endpoints, TC/TM/ACK correlation, cancellation, reconnect/reset, delayed commands, crash/partition handling, unrelated-worker survival and uncertain effects held without replay |
| `ide_browser` | Actual installed IDE v1.2.1 and exact SPELL pairing; public native launch, source/workspace state, debugger stacks/variables/breakpoints, prompts and results; three authenticated browser identities, controller plus read-only observers, 20 observers, accept/reject/expiry/races, A-to-B-to-A control transfer, WSS gap recovery and Git conflicts |
| `compose` | Clean joint deployment with the real v0.8 native image; ten executions/20 viewers; secrets and negative authorization/egress tests; worker/Listener/Context/DSS loss, storage failure, backup/restore and authority fencing |
| `kubernetes` | Local smoke plus production-like enforced NetworkPolicy cluster; real Jobs and observers, RBAC/admission/secret isolation denials, duplicate/recreated workers, node drain/loss, partitions, DNS/DSS loss, storage recovery, restore, upgrade and rollback |
| `recovery` | Audit ordering, concurrent writes, durable acknowledgment, incomplete tails, restart/full-disk/long-duration capacity; whole-deployment restore and proof that old authority is fenced before replacement execution authority is granted |
| `security` | Authentication/authorization/replay/source integrity, secret protection, bounded load and 100+ viewers where required capacity allows; exact delivered SBOM, license/notices/corresponding source and advisory disposition; mandatory independent implemented-system security review |
| `ci` | Required format/lint/types/unit/Python 3.13/native/protocol/driver/DSS/isolation/ownership/recovery/Git/API/browser/deployment checks on final paired identities; complete terminal outcomes, logs, journals and downloadable evidence |
| `packaging` | Reproducible and portable delivered dependencies, native images and supported installation artifacts; consistent versions/locks/manifests; clean installed and public-launch acceptance, offline/recovery instructions, checksums, provenance and downloaded-artifact verification |

For IDE acceptance, test the public user path through the v0.8 server connection and actual native services. Keep the legacy Session/v0.7 path separate. Prove there is no local Run/Debug fallback while connected, observers cannot mutate, stale controllers cannot act, handoff requires explicit reconnection and does not silently resume, and displayed source/results match the execution identity. Exercise light/dark desktop views and relevant IntelliJ/PyCharm hosts where the delivered support matrix requires them.

Replace the qualification desktop's v0.7 native baseline with a separately identified image built from the verified v0.8 candidate for full joint tests. Verify installed and mapped binary hashes; wheel version strings and Docker labels are insufficient. Complete the actual Qt/PySide/shiboken/ICU/plugin/helper dependency closure for the selected build. Do not promote experimental dependencies merely because they exist in an archive.

Keep historical failures and evidence gaps visible: partial TIME/PY/DATA coverage is not all-763 acceptance; the recorded 555 bindings, 546 matches/nine drift and 46 unresolved historical hashes need reconciliation; package counts, vulnerability matches and advisory IDs are different measures. Recompute inventories and dispositions for delivered artifacts and use authoritative current advisory/license sources.

Verify access to the production-like NetworkPolicy cluster and the independent implemented-system reviewer early. State the exact missing resource and the gate it blocks. Continue feasible implementation and qualification while awaiting access. Internal agent review, static manifests and local Docker limitations cannot substitute for or redefine those required boundaries.

## 7. Preserve evidence and finish the qualification decision

Keep a current execution ledger with job ownership, candidate/source/dependency identities, runner configuration, command, start/end times, exit status, tests/passes/failures/skips, raw logs, ordered journals, audit files, screenshots and SHA-256 inventories. Collect every launched job's terminal outcome. Reconcile delayed remote writes and job completions before retrying or dispatching another run.

Update canonical qualification records with source-bound receipts. Preserve the distinction between an original failure, a subsequent fix and a later passing run. Do not overwrite published manifests or historical failed reports. Save incremental recovery checkpoints with verified inventories, required source bundles, reconstruction instructions and active-job state. Archive checksums and CRCs prove archive integrity, not runtime qualification.

Completion requires all eleven mandatory groups to pass at the exact final pairing, with no required test silently skipped, no missing implementation hidden by a scope change, and the required external review completed. Freeze the final sources and artifacts and repeat affected acceptance after every version, code, dependency or packaging change. Publish qualified SPELL `v0.8` only under that condition.

If unchanged IDE v1.2.1 artifacts pass, append dated qualification evidence identifying their exact bytes and supported pairing while preserving the original unqualified-publication history. If fixes require changed IDE artifacts, use the next appropriate unused version and report v1.2.1's remaining limitation. Verify independently downloaded final artifacts and clean installed operation before claiming release completion.

Preserve existing cleanup authorization and recovery requirements, but do not delete active qualification worktrees, unique branches, required evidence or the local desktop's persistent data while they are in use. Reconcile whether prior cleanup actually completed. After integration or verified archival, apply the prior project-scoped cleanup policy through permitted repository workflows; do not assume all remaining branches are disposable or rename the default branch without resolving the recorded policy and current state.

The final report must state separately: IDE v1.2.1 qualification status; exact compatible SPELL identity; full SPELL v0.8 gate results; any successor IDE version required; published release links and artifact hashes; preserved failed attempts; unresolved implementation versus external resource blockers; active jobs; and the latest verified recovery checkpoint. Continue through fixes and retesting while meaningful work remains. If an external prerequisite prevents completion, leave that gate explicitly open and provide the smallest concrete action needed to unblock it.
