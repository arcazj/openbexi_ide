# OpenBEXI IDE roadmap

The November 22 qualification pairs IDE 1.2.2 (`fadac70d`) and SPELL 0.8.0 (`47e0cb37`). Close the original sanitizer and driver failures, finish inherited compatibility, run project-level checks in both JetBrains hosts, and obtain the representative deployment and independent security review before publication. [Gate owners, remaining checks and evidence](https://github.com/arcazj/openbexi_spell_plugin/blob/qualification/ide-spell-20261122/docs/v0.8/evidence/qualification-20261122/README.md)

1. Preserve reliable concurrent requests and heartbeats within the original **2 s, 3 s and 1.5 s** checks. Retain paired local/reference evidence and storage-contention failures. Correct a runner or code path only when measurements establish its cause.
2. Keep the validated native test compiler optimization (`-g1`). Require the complete foundation suite to pass within **600 seconds**, with zero failures, errors or skips.
3. Keep the original 45-second check and preserve the **64 MiB** first/last ten-second median rule, **1,792 MiB** resident peak, **2 GiB** container and **zero swap**. Both five-minute sanitizer scenarios exceeded the growth limit. Establish a conforming fix or obtain owner approval for a specific deployment-backed amendment before either original 3,600-second run.
4. Complete all eleven release groups: services, native family, all-763 compatibility, driver faults, IDE/browser, Compose, Kubernetes, recovery, security, CI and packaging. Preserve the original G0–G9/A–L requirements and F1–F10 review oracles.
5. Obtain the production-like NetworkPolicy-enforced cluster and independent implemented-system reviewer. Publish qualified artifacts only after the exact final pair satisfies every original gate; production migration remains unauthorized.

Repository consolidation and cleanup preserve the latest product code, acceptance limits and failed evidence. [Maintenance and archive recovery](docs/REPOSITORY_MAINTENANCE.md) describe retained dependencies and historical material. The supplied architecture diagrams are reference material, not release acceptance.
