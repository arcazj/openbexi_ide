<!-- CURRENT QUALIFICATION -->
> **Current qualification — November 5, 2026:** IDE v1.2.1 and full SPELL v0.8 remain unqualified; all eleven release groups are open. See [current status, verified results and next work](CURRENT_STATUS.md). Earlier candidate IDs and bounded acceptance below apply to their recorded subjects.
<!-- END CURRENT QUALIFICATION -->

# IDE v1.2.1 and SPELL v0.8 qualification environments

Qualification targets and test budgets are recorded in the companion SPELL repository at `docs/v0.8/QUALIFICATION_ENVIRONMENTS.json`. This contract defines environments to test; it does not claim that these platforms or the full release have passed.

| Target | Required scope |
| --- | --- |
| Ubuntu 24.04 x86_64 hosted runner | SPELL services, actual native processes, installed IDE client, foundation and native suites |
| Debian 13 x86_64 Docker desktop | Installed Qt desktop, native runtime and noVNC; replace the current v0.7 native baseline with verified v0.8 bytes for joint acceptance |
| Windows 11 x64 and fresh hosted Windows installation | IDE desktop, CLI/debugger and remote SPELL client; Linux server acceptance remains separate |
| Pinned Chromium | Three authenticated users, controller/observer permissions, prompts, WSS recovery and the required viewer workload |
| IntelliJ IDEA and PyCharm on Windows x64 | Inherited host integrations at explicitly recorded IDE/plugin builds |
| Production-like Linux Kubernetes cluster | Required workload, admission, NetworkPolicy, node/storage faults and recovery |

The hosted reference pins CPython 3.13.17. Use CPython 3.13 and the declared PySide6-Essentials 6.10.3 dependency, recording actual Python patch, Qt dependency bytes and installed artifact hashes. Historical supported-host versions guide discovery, not qualification. macOS and ARM64 have no acceptance claim in this matrix; any broader inherited requirement remains open until reconciled explicitly.

The hosted reference workflow is `v08-qualification-resume.yml`. Its last successful native jobs recorded four CPUs and approximately 15.6 GiB memory. Those values are observations, not a production minimum. The local host has eight CPUs but Docker exposes approximately 7.75 GiB memory; it is a separate environment. Record OS/kernel, CPU/affinity, RAM/cgroup constraints, storage, Docker, compiler, Python and dependency identities before and after each run. Treat image/hardware changes as a new measured baseline.

Run one heavy qualification suite per reference runner. Preserve the workload's own required concurrency. The foundation suite retains its 600-second budget and the local helper's 512 PID limit. Native acceptance retains the original 45-second and 3,600-second workloads, ASan/UBSan/no-swap settings, 64 MiB growth and 1,792 MiB resident peak limits, original accounting and audit retention. No environment record is a workload pass.

Local failures remain failed evidence. A controlled isolated rerun can distinguish environmental contention from a defect, but a later pass alone does not explain an earlier failure. A reference-runner pass cannot hide a failure in a claimed supported deployment.

Published IDE v1.2.1 and SPELL v0.8-rc1 artifacts stay immutable and unqualified pending full acceptance. Changed runtime artifacts require a separate version. Windows offline bundle delivery is currently absent; historical bundles cannot establish v1.2.1 acceptance. The production-like cluster and independent implemented-system reviewer remain external prerequisites.

The latest verified hosted run is [41958849238](https://github.com/arcazj/openbexi_spell_plugin/actions/runs/41958849238): 1,818 foundation passes in 461.451 seconds and both original 45-second scenarios pass. Foundation and native jobs used different CPU models and two runner image revisions despite the common Python pin; their receipts remain distinct. Both local short native scenarios pass, while the local foundation timeout and 300-second memory failure remain open. See [current status](CURRENT_STATUS.md) for complete subjects, metrics and remaining work.
