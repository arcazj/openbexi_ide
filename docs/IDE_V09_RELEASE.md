# Release evidence candidate

Run the release dossier checker from the repository root:

```powershell
python scripts/check_release.py --manifest docs/IDE_RELEASE_DOSSIER.json
```

It requires the IDE wheel, Windows bundle and Docker image record, plus Windows
tests, Linux tests, installed Windows lifecycle, installed Docker workflow,
actual browser interaction and fresh Windows installation evidence. Referenced
files must stay within the evidence root and match their recorded SHA-256.
JSON reports must pass for the selected release version. JUnit reports require
executed tests, no failures/errors and an explanation for any skips.

The checker exits two and reports every open gate for incomplete evidence. It
does not reinterpret absent browser or fresh-machine observations as a pass.
The optional native SPELL plugin uses its own separate conformance and host
distribution records. Archive a release dossier together with its evidence;
the private `.qualification` files are intentionally not committed to Git.
