# Installation diagnostics candidate

`openbexi doctor` reports installed package/runtime metadata without a session
connection. `openbexi doctor --desktop` also requires the locked Qt, debugpy and
Pygments versions. Exit zero means the requested installation prerequisites are
present; exit two identifies a missing or unsupported prerequisite.

The report omits environment values, file paths, project contents, invitations,
keys and backend entry-point targets. Plugin discovery reads distribution
metadata without importing or running optional backend code. Invalid version
metadata is bounded before it is included in output. Tests install temporary
metadata referencing a side-effecting module and verify that diagnostics never
import it; the public CLI also works with a nonexistent credential file.

The [operations guide](OPERATIONS.md) covers supported candidate profiles,
versioned installation, preservation of projects/settings, historical backups,
authority recovery, explicit reconciliation and the danger of rolling back
fences or approvals. It does not treat restoration of an old database as proof
that external effects are safe to repeat.
