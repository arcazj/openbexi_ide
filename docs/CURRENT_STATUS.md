# Current qualification status

Updated November 6, 2026 UTC. **IDE v1.2.1 and SPELL v0.8-rc1 remain unqualified.** All eleven full-release groups are open. The reference Linux foundation passed **1,823 tests in 547.880 seconds**, with zero failures, errors or skips and the original 600-second limit. Matched concurrent requests and heartbeats pass under measured conditions; preserved storage-stall failures prevent an unconditional reliability claim.

The complete **303.491-second** Context/bridge diagnostic captured all eight processes and zero swap, but growth was **304.76 MiB** against **64 MiB** allowed. No conforming memory correction is established. Both original one-hour scenarios remain pending; cleanup and branch consolidation do not qualify a release.

## Exact subjects

| Subject | Identity / result |
| --- | --- |
| Published IDE v1.2.1 | `08c314fb6b802b407cbabe01777072884d2b7504`; unqualified |
| Published SPELL v0.8-rc1 | `ce45fa4fd31b77cb97a1ef3621aa3906d2c94dda`; unqualified prerelease |
| Latest preserved product runtime | SPELL `c5529d02a49c89a8919b965ffb4eb43498eb0cdf`; no cleanup runtime change |
| Reference foundation | `540c0e0ba957a82b98f3c13a416da28cd52acd65`; 1,823 passed / 547.880 s |
| Complete memory diagnostic | `47ebd1c091e0299213f9ee3978cf4e74d513fddf`; 319,567,872-byte growth / zero swap |
| Pre-cleanup latest commits | IDE `f14bd292e8dac77aa000c6590e16b503e831e113`; SPELL `d577d45455a56f4e355ab986ac15391f01a4191c` |

The [complete investigation](https://github.com/arcazj/openbexi_spell_plugin/blob/main/docs/v0.8/CONTEXT_DSS_DEADLINES_20261105.md) records identical-input local/Linux comparisons, individual lock/commit/durable-I/O/RPC timings, live heartbeat results, source hashes, exact ELF attribution and retained failures. Matched local and Linux sets passed 18/18 each. A contended local set failed 11/18 and an earlier Linux set failed one original two-second check; those results remain counterexamples.

The complete diagnostic retained 169 samples (143 soak), eight process identities and 178 successful heartbeats. Growth is predominantly anonymous retention with nearly flat live allocation totals and rising sanitizer quarantine. Executors dominate, followed by Context and bridge. This does not prove a growing live-object leak or establish a sufficient correction. Reducing workload, durability or sanitizer quarantine would change the experiment.

## Binding acceptance and next work

Follow the [SPELL acceptance plan](https://github.com/arcazj/openbexi_spell_plugin/blob/main/docs/v0.8/ACCEPTANCE_PLAN.md), [resource contract](https://github.com/arcazj/openbexi_spell_plugin/blob/main/docs/v0.8/NATIVE_RESOURCE_ACCEPTANCE.md) and [release gates](https://github.com/arcazj/openbexi_spell_plugin/blob/main/docs/v0.8/RELEASE_GATES.json) unchanged. Keep the original request deadlines, required concurrency, 600-second foundation budget, 45/300/3,600-second workloads, 64 MiB growth limit, 1,792 MiB resident peak, 2 GiB recovery limit and zero swap. All eleven release groups remain false. Historical short passes do not replace complete deployed, compatibility, security, recovery or sustained acceptance.

Establish and validate a measured memory correction, then pass the original 300-second gate before both original hours. The enforced-NetworkPolicy cluster and independent implemented-system reviewer remain external prerequisites. Public v0.8 provisioning remains disabled. The existing desktop uses the v0.7 native baseline.

The [roadmap](../ROADMAP.md) records the work order. [Repository maintenance](REPOSITORY_MAINTENANCE.md) records cleanup, fresh-checkout validation and archive recovery. Earlier reports are immutable evidence for their named subjects, including failures; documentation and merge commits do not inherit runtime qualification.
