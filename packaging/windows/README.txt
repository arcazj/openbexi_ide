OpenBEXI IDE offline Windows x64 bundle

Extract the complete ZIP and double-click Install.cmd. Installation is per user
under %LOCALAPPDATA%\OpenBEXI\IDE. Python and the desktop dependencies are bundled;
no administrator access, machine Python, or Internet connection is needed.
Use the OpenBEXI IDE Start menu shortcut to launch it.

When supplied with the release, examples live in the active version's examples
directory. Copy that directory to a project folder before editing or running the
examples. Upgrades never overwrite an existing project or your edited examples.
The menu example links to the deep Python, graphics and optional SPELL demos.

To select an installation directory or avoid shortcuts:
  powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 -Root "C:\My IDE" -NoShortcuts

Run a newer bundle's installer with the same Root to upgrade. Activation changes
only after verifying every payload file. Previous version directories remain
available. Running processes retain their original interpreter and files.

Uninstall with:
  powershell -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\OpenBEXI\IDE\uninstall.ps1"

Uninstall deletes only unchanged files listed in the installation manifest.
Modified files and unknown files are preserved. An active bundled interpreter
blocks uninstall before any file is removed; close it and rerun uninstall.
Projects, QSettings preferences, and
external Python installations are never installation-owned files.

The desktop is usable offline. The optional SPELL host plugin and its qualified
Docker execution image are separate artifacts; Docker and that image must be
installed before SPELL execution. See provenance.json for exact dependency and
runtime versions, upstream URL, and SHA-256 hashes. Third-party license files
remain in the bundled runtime and package dist-info directories.

This ZIP is not Authenticode signed. Check the release's published ZIP SHA-256
before installation. Installation scripts may be blocked by managed Windows
policy; the bundle does not change system policy.
