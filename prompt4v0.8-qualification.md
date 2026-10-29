# Complete OpenBEXI SPELL v0.8 and OpenBEXI IDE qualification

Execute the implementation, testing and release work needed to achieve a fully qualified OpenBEXI SPELL v0.8 with its compatible OpenBEXI IDE. Continue from the existing workspace, the published SPELL `v0.8-rc1` / IDE `v1.2.1` pair when available, and the durable evidence referenced below. Do not stop at a plan, diagnostic launch, documentation update or recommendations.

## How to use this prompt

First verify the actual publication state. If SPELL `v0.8-rc1` and IDE `v1.2.1` have already been published, preserve their tags and artifact bytes, record their exact identities, and proceed directly to qualification. If either is missing, complete the explicitly authorized unqualified publication in section 2 before starting lengthy qualification work. Do not repeat completed publication steps or delay these releases because full acceptance remains incomplete.

Treat all historical hashes, job results, counts and evidence pointers below as handoff information requiring reconciliation with current records. The age or detail of a checkpoint does not establish that it is the latest source or that a gate has passed.

## Authorization and changed publication policy

I authorize GitHub commits, necessary release-branch integration, annotated tags, artifact uploads and publication of:

- **OpenBEXI SPELL plugin: `v0.8-rc1`**, as a GitHub prerelease.
- **OpenBEXI IDE: `v1.2.1`**, as the requested release, with a prominent qualification disclosure.

**Publish these two versions even if mandatory qualification criteria remain failed, incomplete or blocked. This explicitly supersedes my earlier instruction to withhold these two releases until every mandatory criterion passes.** Do not ask for routine approval again.

This changes permission to publish; it does not change acceptance criteria or turn failures into passes. Mark both releases **“UNQUALIFIED — qualification incomplete”** and disclose their actual limitations. The IDE’s stable-form version number must not be presented as evidence of qualification or production readiness.

After publication, continue toward a fully qualified SPELL v0.8 and compatible IDE release. The final qualification claim still requires every mandatory criterion to pass at the exact delivered identities.

Production migration is not authorized. Respect authentication, repository protections and access controls. Do not bypass a required hardware-key sign-in, failed authorization or branch protection. Explain any genuinely required additional resource or permission precisely. Existing authorization covers routine implementation, testing and publication work.

## 1. Reconcile the real state and recover evidence

Start with:

- SPELL PR: https://github.com/arcazj/openbexi_spell_plugin/pull/4
- IDE PR: https://github.com/arcazj/openbexi_ide/pull/2

Read actual remote branches, PR heads and bases, immutable commits and trees, CI attempts, tags, releases and assets before changing anything. Check for delayed or partial effects of previous writes. Preserve newer work and determine its lineage. A newer diagnostic branch or synthetic PR merge is not automatically the latest coherent release source or tested evidence.

Recover the latest versions of:

- Main evidence: https://chatgpt.com/library?file_id=libfile_197158e41dbc8191b698c1788cca34bf&account_id=personal
- Main receipt: https://chatgpt.com/library?file_id=libfile_2c3dedf1d84c81919088e708e61ae798&account_id=personal
- Supplemental 79-volume index: https://chatgpt.com/library?file_id=libfile_262238f5f25481919ed442d27094d4e4&account_id=personal
- IDE packaging handoff: https://chatgpt.com/library?file_id=libfile_b4227a6b5e048191afbf03bcf7d6ae24&account_id=personal
- Task-wide job reconciliation: https://chatgpt.com/library?file_id=libfile_ba5b76e2ee3c819183c20be0f7b67ebb&account_id=personal

These are recovery pointers, not claims about current state. Check for newer versions and supplements first.

The last reported canonical main checkpoint was **v14**, 525,422,559 bytes, SHA-256 `63a18ded81f976af2b7e3f32304b20784fbb1534f9ca21e21c91913470b70aa9`. The 79-volume catalog was explicitly supplemental, not a completed main-v15 replacement. Its reported size was 2,038,284 bytes and SHA-256 `6dd0fecee78e0e9e87b0137e30934660a4d29ae8cd8f57455b5978a9103a207b`.

Follow `CURRENT_EVIDENCE_CHECKPOINT.json`, its inventories, `CHECKPOINT_EVIDENCE_VOLUMES.json`, reconstruction descriptors and later supplements. Recover required source bundles and immutable base objects before running source verifiers. Preserve historical raw samples, Markdown bodies, JSON histories, audit records, uncertain tails, failed builds and unsuccessful transfer attempts.

Read at least:

- `docs/v0.8/RELEASE_GATES.json`
- `docs/v0.8/STATUS.json`
- `docs/v0.8/TEST_REPORT.md`
- `docs/v0.8/ACCEPTANCE_PLAN.md`
- `docs/v0.8/NATIVE_RESOURCE_ACCEPTANCE.md`
- `docs/v0.8/SPELL_COMPATIBILITY_MATRIX.md`
- `docs/v0.8/MEASURED_LINE_STACK_CORRECTIONS.md`
- `docs/v0.8/evidence/qualification-dev81-local-20261028.json`
- `agent-dev78/CURRENT_DEV80_CI_OUTCOMES.json`
- `memory-analysis/MEMORY_FOLLOWUP_CURRENT.json`
- `agent-dev78/final-dev81-release-preflight.json`
- All newer canonical records, implementation receipts and qualification summaries referenced by the current inventories.

Keep archive digest/CRC checks, source reconstruction, complete Git-blob verification, component tests and actual shipped-system qualification distinct.

## 2. Publish the requested unqualified versions first

Do not postpone this phase until memory, portability, cluster or independent-review qualification is complete.

1. Select the latest coherent, recoverable SPELL and IDE sources from verified lineage. Inventory completed fixes and unfinished experiments explicitly. Integrate completed relevant corrections only after checking their dependencies and conflicts. Do not blindly merge all diagnostic branches or choose a commit solely because its timestamp is newest.
2. Preserve implemented LINE, cancellation, callstack, request-ID, bridge ownership, STATUS ownership/race, live logical ACK, event-category, audit and graceful-shutdown corrections. Preserve synchronous borrowing into independently owned native strings. Retain ordered result journals and bounded compiler reuse.
3. Keep unfinished or known-defective experiments isolated. In particular, do not promote a CPython buffer candidate with an unresolved reproduced alias/use-after-free defect, or claim that a QtCore-only rebuild establishes whole-wheel portability. Unqualified publication does not require incorporating every experiment.
4. Make only the necessary version, packaging, lock, manifest and release-note changes to form the release pair. Use SPELL tag `v0.8-rc1`; use the repository’s valid package spelling, such as `0.8.0rc1` for Python packaging, with an explicit tag/package-version mapping. Use IDE version/tag `1.2.1` / `v1.2.1`.
5. Build the actual available source and binary artifacts. Record exact commit/tree, build inputs, compiler and dependency identities, image digests, artifact sizes and SHA-256 checksums. Include available notices, licenses, corresponding source, SBOM and installation/recovery instructions, with gaps stated accurately. Do not fabricate missing artifacts, provenance or compliance completion.
6. Run feasible release-integrity, packaging, import, public-launch and clean-install checks against those exact versioned artifacts. Record every outcome. A failed full qualification gate must not automatically block these explicitly authorized unqualified releases. If a binary cannot be built or installed, publish the available legitimate source/artifacts and clearly describe the missing or failing deliverable; do not claim a successful binary release.
7. Preserve repository protections and existing tag identities. If either requested tag already exists, inspect its target and assets before acting. Complete a matching partial publication idempotently. Never force-move an existing published tag or silently replace published artifact bytes. Report an incompatible pre-existing tag as a concrete conflict.
8. Commit the reviewed release state and integrate through the repositories’ permitted release workflow. Do not disable CI, forge statuses, bypass a protected merge or delete failing tests to obtain a merge. If permitted, publish from the authorized release branch without misrepresenting a blocked protected-branch merge.
9. Create annotated tags at the exact intended commits. Publish SPELL `v0.8-rc1` as a prerelease and IDE `v1.2.1` as requested. Cross-link both releases and their exact compatibility pairing.
10. Independently download the public release assets, verify their checksums and attempt clean installation/public launch in supported available environments. Collect actual results before reporting publication success. Post-publication failures must remain visible in release notes and qualification records.
11. Complete the project and branch cleanup in section 8 after preserving all required work and evidence. Leave only `main` locally and on GitHub in both repositories.

Put this disclosure near the beginning of each release:

> **UNQUALIFIED — qualification incomplete.** Published at the owner’s explicit request before mandatory release acceptance is complete. This release has known failed or incomplete checks and is not claimed to be production-qualified. See the qualification report for exact source/artifact identities, results, limitations and recovery instructions.

Explain concrete unresolved issues rather than relying only on the banner. Keep release publication status separate from qualification status in canonical JSON and reports. Do not change gate results to “passed” merely to permit publication.

## 3. Resume qualification from the published baseline

Freeze the published pair as an immutable reference. Work on subsequent qualification branches and preserve a manifest distinguishing:

- Published source and artifact identities.
- New implementation changes.
- Tests completed at each identity.
- Failed, incomplete and externally blocked requirements.
- Historical evidence recovery versus fresh replacement evidence.

The following are reported handoff facts to verify, not substitutes for reading the latest receipts:

- Earlier dev80 original 45-second handoff and installed-IDE runs passed the unchanged 67,108,864-byte growth limit. Both original hour runs failed growth and peak budgets at roughly 1.08 GB growth.
- Later dev83 original hours at `5fe7e80ea14577ef9378889efa573fd632bdfbe8` also failed: handoff growth 1,039,757,312 bytes over 3,601.506 seconds; installed-IDE growth 1,038,614,528 bytes over 3,600.247 seconds. Preserve these failures.
- Integrated GUI workspace/startup-ACK source `f8475676fa8e165a80c54a53dddf92f034d703d7` passed scoped components and original 45-second workloads, while both 300-second comparisons still failed growth. Those comparisons do not replace the mandatory hours.
- The DSS graceful-stop candidate `eddd6758b16c7e6ef44b9cc605896d3143be2e30`, tree `09c2c4f06a7af74bfe81e839ec33a9ab5fb5bd90`, passed the full hosted foundation suite: 1,802 passes, no failures/skips, 593.739 seconds under the original 600-second limit, with a complete 7,210-record journal. It has little timing margin and does not establish other gates.
- Windows IDE source execution subsequently passed 275 tests with 17 unchanged exclusions and installed startup. The first run’s oversized pytest display-ID failure remains preserved; its 65,537-byte product input was not reduced.
- Native TIME/PY/DATA execution produced 680 checks covering 193 mapped IDs at an isolated source. This is overlapping, partial compatibility evidence, not all 763 native requirements.
- Native source-delivery correction `bcef4b6729c1fbfc98b47e26698fedccc49959f5` delivers the tracked legacy helper. Actual native before and after executions both passed the original positive case. Do not invent a pre-fix semantic failure from a different interpreter’s tokenizer behavior.
- The Qt baseline work has real component passes, including 129 CBOR cases and baseline-CPU controls, but the complete 285-ELF wheel rebuild, full dependency closure and fresh joint installed acceptance remain unfinished.
- A CPython smaller-buffer experiment measured substantial allocation-byte reduction, but candidate `66978a4c1159c54a5d07e8bb6d4a0a9813c20652` subsequently reproduced a retained-view use-after-free through custom `raw.write` lookup. Treat it as blocked unless a newer exact correction and complete regression evidence are recovered and verified.
- Libxml2 candidate source/package probes and reproducible DEBs do not establish complete security qualification. The latest reported full source job still failed on absent upstream test fixtures and the installed-security job was skipped.
- All eleven full mandatory release groups remained unqualified at the reported handoff. A later pass must be supported by fresh evidence.
- The last reported task-wide reconciliation found 20 recent runs and 35 jobs terminal, with no pending runs. Recheck current state; do not launch duplicates based on stale polling.

## 4. Fix memory growth using measured ownership and allocation paths

Prioritize experiments that distinguish causes, then implement targeted fixes. Avoid repeatedly running expensive hours when shorter original workloads already disprove the candidate.

1. Bind each measurement to exact SPELL/IDE source, image and native binary hashes, process PID/start time, runtime dependencies and workload parameters.
2. Measure synchronized time series for Context, bridge, Executors and other processes. Separate live allocations, allocation/free churn, allocator and sanitizer retention, thread stacks/resources, shared memory, filesystem cache and durable audit growth. Do not add non-simultaneous samples into a supposedly coeval RSS ledger.
3. Execute the repaired actual-Context observer where prerequisites work. Record observer discovery, process lifetime and coverage failures explicitly. Investigate historical admission denials, driver bursts, delayed registration and worker exits separately from memory growth.
4. Rank observed allocation paths by bytes per workload event and sustained contribution. Compare predictions against measured counts and growth slopes. Optimized-versus-sanitized results are diagnostic evidence, not interchangeable acceptance results.
5. Prefer bounded, exclusively owned reusable storage and removal of redundant allocation/copying where semantics are preserved. Prove lifetime, reentrancy, thread ownership, maximum retained capacity, failure behavior and destructor release.
6. For any CPython buffer correction, resolve the reproduced escaped-view defect first. Cover custom method lookup, retained slices, GC-visible views, retries, reentrancy, allocation failure, partial writes, flush/seek behavior, custom/debug/tracing allocators and matched allocation/free domains. Preserve logical buffering and output. Disclose any changed allocation-failure timing.
7. Build the corrected dependency with pinned source/toolchain/flags for the actual native runtime. Verify the installed and mapped library bytes. A local substitute interpreter, preload interposer or component-only binary does not qualify the delivered image.
8. Add deterministic regressions for each demonstrated defect and retain the original failing evidence. Run scoped checks, then original bounded workloads, then both original sustained workloads once the candidate merits that cost.
9. Preserve sanitizers, accounting, concurrency, fixtures, deadlines, acceptance limits and audit retention. Do not create passes through discarded samples, reduced workload, allocator/sanitizer tuning that hides measured usage, forced purges, moving allocations outside accounting, or deleting audits.
10. Preserve the original dev81 unprotected-memory-read positive-control failure and separate ENOSYS probes. Later capable-host passes do not retroactively convert that failure into a skip or a protection pass.

Component allocation reductions do not by themselves close sustained-family qualification. Do not claim complete wire-byte identity for the live ACK ownership correction: sequence values intentionally change under interleaving.

## 5. Complete dependency packaging, audit and all mandatory gates

Finish the actual implementation and qualification, not merely the records.

- Complete portable, reproducible IDE dependency builds across the delivered Qt, PySide, shiboken, ICU, plugins, helper executables and other native objects. Preserve source/feature attribution and previous graphics SIGBUS, heap corruption, failed builds, no-op installs and diagnostic preload evidence. Do not inherit an official wheel’s portability claim for a derivative without proof.
- Update source, lock and build definitions only to actual deliverable candidates. Rebuild clean joint images and re-run affected source and installed-system tests against exact final bytes.
- Finish native, OS, Python, IDE, plugin and vendored SBOM, notices, licenses, corresponding-source and advisory dispositions using authoritative sources and delivered objects. The historical 243 packages, 376 vulnerability matches and 187 advisory IDs are different counts, not unique CVEs. Recompute for each actual candidate.
- Complete durable audit completeness, ordering, concurrent writes, durable acknowledgment, restart recovery, uncertain tails, explicit failures, full disk and long-duration capacity.
- Qualify whole-deployment restore, old-authority fencing and execution-authority recovery. Component ENOSPC/audit passes are insufficient.
- Cover all 763 compatibility requirements and original native/driver semantics. Preserve the historical 555 bindings, 546 matches/nine drift, 47 reports and 46 unresolved missing hashes unless genuinely recovered or superseded by separately labeled fresh evidence.
- Cover independent Listener, Context, Executor and DSS; parallel procedures with one active instance per procedure; one controller and read-only observers; pause, step, prompts, abort/close, terminal cleanup, A→B→A handoff and observer continuity.
- Cover installed IDE, public native launch, debugger, authenticated browser/WSS recovery and Git collaboration.
- Cover complete Compose and Kubernetes workloads, policy denials, process/node loss, partitions, storage failure, restore, upgrade, rollback, security and bounded load.
- Obtain the mandatory independent implemented-system security review. Internal agent review is useful technical review, not a substitute.

Keep missing external resources separate from unfinished implementation and failed tests. Verify access to a production-like cluster enforcing NetworkPolicy, suitable native runners, supported Windows execution and the independent reviewer. Local Docker/Kubernetes or syscall limitations must not be generalized to capable hosted runners. Continue unrelated feasible work while a resource is missing.

## 6. Publish the qualified successor only on actual evidence

Once every mandatory gate passes:

1. Freeze final source, dependency, build, image and artifact identities.
2. Complete clean installation and full end-to-end acceptance on the exact final artifacts. Revalidate affected checks after every code, version, dependency or packaging change.
3. Publish the qualified SPELL `v0.8` release according to repository conventions and the compatible IDE release at the next appropriate unused version.
4. Preserve `v0.8-rc1` and IDE `v1.2.1` tags/assets unchanged. If the IDE’s runtime or artifact bytes change, use a new version rather than replacing `v1.2.1`. If exactly the previously published bytes later qualify, append dated qualification evidence while preserving the original publication disclosure and history.
5. Cross-link releases, verify independently downloaded checksums and complete clean installation of the published artifacts.
6. Claim “qualified” only for the exact identities and scope actually accepted.

## 7. Execution, persistence and reporting

Use parallel agents for independent implementation, memory attribution, packaging, audit/recovery, compatibility and evidence collection, with clear ownership and no conflicting edits.

Wait for every launched qualification job and collect its terminal outcome, logs, journals and artifacts. Preserve unsuccessful attempts and exact source identities. Do not repeatedly retry a known broken write route or confuse a transport failure with an approval rejection.

Keep canonical records, PR metadata and durable evidence current. Save incremental checkpoints with inventories, digests, reconstruction instructions, source bundles and active-job ownership. Preserve old records and explicitly label supplemental catalogs. Do not claim a new canonical checkpoint version before it is successfully saved and verified.

Report two distinct milestones:

- **Requested unqualified publication:** actual SPELL `v0.8-rc1` and IDE `v1.2.1` release links, exact tags/commits, downloadable assets, independent checksum/install outcomes and remaining limitations.
- **Final qualification:** precise gate outcomes and qualified successor release links only after acceptance is complete.

If work is ultimately blocked, state exactly what was published, committed remotely and retained locally; which checks failed; what implementation remains; which resources or permissions are missing; whether any jobs remain active; and where the latest verified recovery checkpoint is saved. Do not treat known qualification failures as a reason to withhold the two explicitly authorized unqualified releases.

## 8. Clean up caches, temporary files and branches

Cleanup is explicitly authorized for both `arcazj/openbexi_spell_plugin` and `arcazj/openbexi_ide`. Complete it after the requested releases are published and verified, and repeat it after the final qualified releases. Do not postpone the first cleanup until full qualification is complete.

1. Inventory local and GitHub branches, worktrees, uncommitted files and active jobs. Finish or safely hand off active work and collect its logs and artifacts before removing anything it uses.
2. Integrate completed release work into `main` through the permitted repository workflow. Before deleting any branch, preserve its unique commits and any unfinished work in a verified, durable recovery archive with exact branch-to-commit mappings. Preserve required source bundles, qualification evidence and the continuation prompt.
3. Verify that `main` contains the intended integrated work, is synchronized with GitHub, and is the default branch in both repositories. Remove obsolete worktrees after preserving their contents and switch the retained working copies to `main`.
4. Delete every other local branch and every other GitHub branch in both repositories, including feature, development, test, diagnostic and release branches. Prune stale remote-tracking references and resolve superseded PRs with an explanation. Preserve Git history, published tags, release assets and their immutable identities. Do not force-push or rewrite `main`, or bypass repository protections.
5. Remove all project-owned caches and temporary files, including Python/test/lint caches, disposable build and packaging intermediates, temporary downloads and extraction directories, obsolete diagnostic outputs already preserved as evidence, and GitHub Actions caches belonging to these two repositories. Limit cleanup to these projects; preserve final deliverables, required dependencies, configuration, credentials, persistent application data, logs and evidence needed for recovery or qualification. Do not delete GitHub Actions run history or evidence artifacts as though they were caches.
6. Verify that only `main` remains in the local branch list and the GitHub branch list for each repository, that the retained working trees are clean, and that both published releases remain accessible. Report the branches and cache categories removed, space reclaimed where measurable, and anything that could not be removed with its exact reason. Do not claim cleanup is complete if a protection rule or unresolved preservation step prevents it.

Subsequent qualification may use temporary branches when required by the repository workflow. Integrate or archive their work and remove them before final handoff, leaving only `main` again.

