# OpenBEXI IDE 1.0

Final 1.0.0 Windows and Docker artifacts are prepared from `0091150`, which
changes rc4 release metadata without changing the Python application sources.
The release is published from `master` with Git tag `1.0` and package version
`1.0.0`, at the user's explicit request after the pending fresh-Windows check
was disclosed. That validation remains outstanding; publication does not
change its test status.
The [release dossier](IDE_1_0_0_RELEASE_DOSSIER.json) records the exact artifacts
and all five completed gates. The published rc4 prerelease remains available.

## Downloads

- [Windows x64 offline ZIP](https://github.com/arcazj/openbexi_ide/releases/download/1.0/OpenBEXI-IDE-1.0.0-windows-x64.zip): extract and run `Install.cmd`; includes CPython and desktop dependencies.
- [Linux amd64 Docker image tar.gz](https://github.com/arcazj/openbexi_ide/releases/download/1.0/openbexi-ide-1.0.0-linux-amd64.tar.gz): load the exact tested image with Docker.
- [SHA-256 checksums](https://github.com/arcazj/openbexi_ide/releases/download/1.0/SHA256SUMS.txt).
- [All release assets](https://github.com/arcazj/openbexi_ide/releases/tag/1.0), including the Python wheel and qualification records.

## Verification

Windows passes 176 source tests, including all eight Docker Execution checks;
one symlink-permission test is skipped. Linux passes 168 tests with nine
documented platform/profile skips. Installed Linux headless and X11 workflows,
actual Edge/noVNC interaction, and all 14 rc4-to-1.0 Windows lifecycle checks
pass. Eight installer ownership/tamper checks pass. Two offline Windows builds
produce the identical ZIP SHA-256:

`3f4cc40490bfc128f79949bbb5d030484a2a2e82a773f1638bdeb51dd3906a56`

The final Docker image is
`sha256:6206c08b3beb7bc3bca5cd348fb6f9164ce1de53ac9853121025f821a4c149e7`.
It derives offline from the exact qualified rc4 image and installs the final
1.0.0 wheel. The running desktop is at <http://127.0.0.1:6080/vnc.html>.
The downloadable image archive can be loaded with
`docker load --input openbexi-ide-1.0.0-linux-amd64.tar.gz`.

## Complete fresh Windows qualification

Use a freshly provisioned Windows x64 VM or machine, with no prior OpenBEXI IDE
installation. Download the final ZIP and the standalone qualification script.
No machine Python or administrator installation is required. Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\qualify_fresh_windows.ps1 -Archive .\OpenBEXI-IDE-1.0.0-windows-x64.zip -ExpectedSha256 3f4cc40490bfc128f79949bbb5d030484a2a2e82a773f1638bdeb51dd3906a56 -FreshWindows
```

The script verifies every payload file and runs installation, Run/Debug,
console menus, shared debugging, removal, and user-file preservation using the
bundled runtime. It rejects the existing development machine and retains all
logs. Return the resulting evidence directory, including `fresh-windows.json`.
That result must match this ZIP before the outstanding fresh-Windows gate can
be recorded as passed. The release dossier retains its pending status.

The IDE and native SPELL plugin have separate release gates. SPELL work resumes
after this IDE publication, as requested. Review of
`access_programs.cyber` is deferred to SPELL's operational 1.0 release.
