# Qualify OpenBEXI IDE v1.2.1 and OpenBEXI SPELL Plugin v0.8

Begin only after I explicitly approve this prompt. Then implement the missing functionality, fix demonstrated defects, and complete qualification against the artifacts users will actually install.

## Release targets

| Product | Version to qualify |
|---|---|
| **OpenBEXI IDE** | Qualify the published **`v1.2.1`** artifacts if they pass as delivered. If qualification requires changing the IDE wheel, runtime, or shipped dependencies, use **`v1.2.2`** and record a separate verdict for `v1.2.1`. |
| **OpenBEXI SPELL Plugin** | Qualify the stable release **`v0.8`**, with Python package version **`0.8.0`** for the server, host, shared, and DSS packages. The published `v0.8-rc1` is the baseline. The separately versioned simulator SDK is `0.1.0`. |

## Start from the verified work

Use `C:\projects\openbexi_ide` and `C:\projects\openbexi_spell_plugin`. Reconcile both `main` branches and published tags with the saved master prompts, `prompt4v0.8-qualification.md`, the IDE’s `prompt4ide-v1.2.1-full-spell-v0.8-qualification.md`, both current-status reports, and the SPELL acceptance plan, environment contract, and release-gate ledger. Preserve published artifacts, their original disclosures, and the recovery archive.

The recorded Linux foundation result is **1,823 passes in 423.326 seconds** within the 600-second budget. All eleven full-release groups were still open. Reuse evidence where its source, artifacts, environment, and test scope match. Rerun affected checks on the final pair. Preserve the existing 2-second, 3-second, and 1.5-second request and heartbeat deadlines.

## Resolve the 64 MiB question before repeating expensive tests

The **64 MiB growth limit** originated in a **45-second recovery test**. My November 5 prompt explicitly carried it into the five-minute qualification step. The complete five-minute diagnostic grew **304.76 MiB with zero swap**. On an earlier build, optimized one-hour runs grew approximately **5–7 MiB**, while the required sanitizer runs grew about **1 GiB** and also exceeded the separate peak-memory limit.

1. Keep the original 45-second test. Use the saved traces to determine where growth occurs, whether it levels off, and how much comes from live allocations, allocator or sanitizer retention, and filesystem cache. Start with the Executors, then examine Context and the bridge.
2. Evaluate the five-minute and one-hour criteria against the intended deployment’s memory capacity and comparable reference runs. Preserve the **1,792 MiB resident peak**, **2 GiB container limit**, **zero swap**, original workloads, sanitizer settings, and audit records. Evaluate both the shipped build and the instrumented build.
3. If the evidence supports a different sustained-growth limit, bring me **one specific amendment** with the proposed number, measurement windows, deployment headroom, and evidence showing what failure it would catch. Obtain my approval before using it for qualification. Report results against the original rule as well. Continue the other release work while that decision is pending.
4. Repeat a failed run when a fix or a new measurement can answer a specific question. Once the applicable five-minute criterion passes, run **both original one-hour scenarios** with ASan/UBSan and zero swap, covering native controller handoff and operation through the installed IDE.

## Complete joint qualification

Close all eleven groups in `docs/v0.8/RELEASE_GATES.json`, including their underlying G0–G9, A–L, and F1–F10 requirements.

- **Services, native execution, compatibility, and driver faults.** Run the real Listener, Context, Executors, and independent GENERIC DSS. Demonstrate ten concurrent distinct procedures and one admitted instance from 100 competing starts of the same logical procedure. Verify all **763 inherited SPELL requirements** against the manuals, upstream source, and native runtime. Exercise child procedures, prompts, pause, step, abort, cleanup, and command-to-acknowledgment-to-telemetry behavior. Preserve uncertain command outcomes without automatic replay.
- **Installed IDE and browser.** Verify ordinary Python Run/Debug with SPELL absent, then install the exact plugin and launch a native procedure through the user-facing v0.8 connection. Exercise Development, Monitoring, and Execution modes, debugger state, prompts, results, and Git collaboration. Verify IntelliJ IDEA and PyCharm installation and Run/Debug on Windows. Test three authenticated browser users, 20 observers, explicit A→B→A control transfer, stale-controller rejection, and reconnect without automatic resume. Confirm that server actions cannot fall back to local execution.
- **Compose, Kubernetes, recovery, and security.** Build the joint desktop with the actual v0.8 native runtime. Exercise clean deployment, service and node loss, durable audit, storage failure, restore, upgrade, rollback, and revocation of old execution authority before recovery. Verify access early to a production-like Kubernetes cluster that enforces NetworkPolicy and to an independent security reviewer who can assess the implemented system.
- **CI and packaging.** Use the local workstation for diagnosis and Windows desktop checks. Run the required hosted Ubuntu and Windows checks, Debian desktop, pinned Chromium, and JetBrains tests. Verify clean installs, dependency versions, native image digests, checksums, software bill of materials, licenses, and advisory dispositions for the delivered artifacts.

## Release decision

For each gate, record **PASS, FAIL, BLOCKED, or NOT RUN**, with the exact IDE and SPELL identities, command or CI run, and supporting evidence. Collect every launched job’s outcome. If a resource is missing, identify the affected gate and the smallest action needed to unblock it while completing independent work.

Publish the qualified pair under the existing conditional release authorization only after every mandatory gate passes against the approved criteria. Verify fresh downloads and a clean installation. If the original IDE `v1.2.1` qualifies, append dated evidence to its release history. Update both READMEs and roadmaps concisely with the exact supported pairing, remaining limitations, and links to the detailed results. Production migration requires separate authorization.
