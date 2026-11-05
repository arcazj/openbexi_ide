# November 5 memory and foundation investigation

IDE v1.2.1 and full SPELL v0.8 remain unqualified. One measured test-build optimization is committed at `10283db843578c04ff4aa454e43abb041be605a9`. Memory acceptance and the local foundation deadline remain unresolved; all eleven release groups remain open.

The native subject is `c5529d02a49c89a8919b965ffb4eb43498eb0cdf`. Product runtime code, original concurrency, operation deadlines, ASan/UBSan options, no-swap accounting and audit retention were preserved. Published releases and previous failed evidence were not changed.

## Measured outcomes

| Run | Result |
| --- | --- |
| Fresh 300-second handoff baseline | Failed: 229,232,640-byte window growth in 303.135 seconds, versus 67,108,864 allowed. Peak 1,492,119,552 bytes; eight original processes; zero swap and memory-limit events. |
| 300-second sampled allocation diagnostic | Failed: 235,368,448-byte growth. Observer overhead makes this a diagnostic, not an improvement comparison. |
| Original foundation with external profiler | 600-second timeout: 1,224 completed passes, zero completed failures. |
| Foundation after compiler correction, original `/tmp` | 600-second timeout: 1,380 completed passes, zero completed failures. Lint, formatting and types pass. |
| Foundation with corrected short durable-volume path | 600-second timeout: 1,450 completed passes and three failed concurrency/deadline cases. Lint, formatting and types pass. This runner configuration is not accepted. |
| Original affected tests | All 245 cases in the 17 changed fixture files pass in the original-path rerun. Both new sanitizer regressions pass. |
| Original one-hour scenarios | Neither attempted: the completed shorter memory runs still exceed the original growth limit and no memory correction is validated. |

## Executors then Context and bridge

The baseline retained all eight original process identities throughout the completed soak. First/last ten-second anonymous-memory medians show:

| Process role and namespace PID | Anonymous growth | Live allocated-byte change |
| --- | ---: | ---: |
| Executor 108 | 121,688,064 | +3,112 |
| Executor 159 | 54,738,944 | 0 |
| Context 41 | 26,320,896 | -984 |
| Active bridge 90 | 13,299,712 | -2,179 |

Allocator observations are sparse and asynchronous. RSS, cgroup, allocator heap and quarantine values overlap; they are not added or subtracted from acceptance. The full process table and observation ages are in the receipt.

Executor allocation profiles repeatedly identify 4,096-byte buffers at exact `libpython3.13.so.1.0` offsets `0x179ef0`, `0x25012a`, `0x25f754`, and `0x18b7cb`. The three growing sampled sites end with 221,184, 143,360 and 192,512 allocated bytes respectively, all matched by observed frees. A separate embedded-Python control reproduces those four offsets using both ordinary text `open()` and explicit `BufferedWriter` construction; each mode records 16 allocations and 16 frees. The actual mapped library hash is `085a2b2227f39be171d5fd68967fba933adb37b7ab8b879d2a2565d4f7bb6b41` and matches the control library. Private symbols are stripped, so matching only the nearest exported symbol would have misidentified these frames.

This demonstrates correctly freed Python buffer churn alongside growing allocator/ASan retention, rather than a demonstrated growing live buffer leak. No conforming memory correction was established. The original 20 ms progress writers, buffering, Python allocator policy, sanitizer quarantine and whole-cgroup oracle remain unchanged.

Three additional observer attempts failed before the requested soak: native child/driver startup, native readiness with a Context heartbeat timeout, and handoff readiness with another heartbeat timeout. The last attempt retains 22 resource samples over 44.761 seconds of startup, 18 distinct ASan statistics records, and exact mapped ELF/process identities. Its roster grows from two to seven to eight processes; it is not a completed endurance cohort.

Those startup observations identify Context log4cplus formatting and `SPELLexecutorManager::buildExecutorInfo` string allocations, and bridge JSON DOM construction, mailbox preparation and event/mutex creation. The reported sampled sites have matching frees. Source-bound symbolization used the exact image ELFs. Context global quarantine rises from 137,816,470 to 138,887,664 bytes; the active bridge reaches 1,048,584 bytes. These startup counters demonstrate retention but do not quantify each site's contribution to the completed 300-second Context/bridge growth. A simultaneous full-soak decomposition remains open.

## Foundation cost and the validated correction

The profiled incomplete suite spent approximately 254.6 seconds in setup, 335.4 seconds in test calls and 5.6 seconds in teardown. Individual compiler subprocess durations total 256.3 seconds, overlapping each other and the phase totals; they must not be added again. Deliberate original timeout checks, including the 31-second retry case, remain intact.

A controlled four-build comparison changed only debug metadata from `-g` to `-g1`. Median compilation fell from 11.796 to 8.957 seconds, a 24.1% reduction; binary size fell from 6,473,000 to 3,338,600 bytes. The `.text`, `.rodata`, `.data` and `.eh_frame` sections were byte-identical in all four builds. This justified changing 23 flags in 17 native test files. Shipped runtime builds retain full `-g`; the test fixtures omit local-variable debug metadata while retaining tested function/source-line sanitizer backtraces.

The two new regressions deliberately trigger ASan use-after-free and UBSan signed overflow under both debug levels. Both retain the correct diagnostic, function and source line, and compare code/data/unwind section hashes. All 245 affected original checks also pass in the complete prefix of the original-path foundation rerun. This validates the optimization but does not turn the timed-out full suite into a pass.

Durable I/O is measured directly in the original line-audit test using a diagnostic wrapper that always calls the real `fdatasync` and preserves its return/errno. Its two binaries make 20,012 calls, spending 35.018 seconds in them out of 35.359 seconds of binary execution. The original test passes with all records, byte comparisons and durability assertions retained. Removing those calls would change the contract.

Four sequential storage controls pass the same 13 driver checks. Median JUnit time improves from 14.786 seconds on the container layer to 10.342 seconds on the durable volume. The first full-volume attempt exposed an overlong Unix-socket path and was stopped with failed journals retained. Mounting the same volume at `/q` and setting `TMPDIR=/q/t` passes the two original socket checks, but full acceptance still times out and fails both two-/three-second ten-request bursts and the 1.5-second ten-receipt barrier. The smaller storage result does not establish reliable full-suite performance. No SQLite durability mode, request deadline or concurrency was changed.

## Retained evidence and next action

[Machine-readable receipt](evidence/ide-1.2.1/root-cause-20261105/qualification.json) records source identities, per-run results, phase timings and limitations. Raw logs, native audits, failed fixture databases, profiler records, compiler inputs/binaries, allocation controls, source-bound symbols and wrappers remain under `F:/openbexi-builds/v08-qualification-20261104/root-cause-20261105/`. Earlier reference-runner inventories remain unchanged.

A separate demonstrated setup failure was Windows reserving TCP 64023 while the Linux helper selected it as free. The trusted wrapper now uses candidates bind-checked on Windows and actually bound on Linux; raw Docker errors and port-selection receipts are retained. It changes no worker isolation or deadline and does not explain the other startup failures.

Next, isolate the Context/DSS transaction and I/O latency behind the original concurrent deadlines, then collect a completed full-family Context/bridge retention trace. Keep the validated compiler change, preserve the failed storage experiment, and require a passing shorter original memory result before either original one-hour scenario. No runtime memory fix, full foundation pass, deployment qualification or release gate promotion is claimed.
