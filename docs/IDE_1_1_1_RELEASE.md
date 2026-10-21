# OpenBEXI IDE 1.1.1

The Docker desktop now uses the accepted SPELL v0.6 native runtime, DSS bridge
and host wheel. Code rows remain white, with a soft highlight only on the
current line. Result cells keep success/failure/warning colors in Qt and browser
views. Completion clears the cursor before artifact export finishes, and an
explicit Abort remains recorded as aborted after clean adapter shutdown.

The image excludes cached example results. Offline builds use exact accepted
image and wheel hashes. The default Compose deployment retains the previous
desktop's workspace and preferences volumes.

See [installation and commands](IDE_SPELL_V06.md) and the
[qualification record](IDE_SPELL_V06_QUALIFICATION.json) for exact artifacts,
checks, retained diagnostics and cleanup. This patch does not replace the
published SPELL v0.6 tag or claim v0.7 operational qualification. No new Windows
offline bundle or JetBrains ZIP is included.
