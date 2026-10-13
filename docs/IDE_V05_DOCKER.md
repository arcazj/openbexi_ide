# v0.5 Docker candidate

The local image `openbexi-ide:0.5.0rc2` contains the v0.5 Python collaborative
debugger, plugin manager, usability improvements and examples. Start it with:

```powershell
docker compose -f compose.v05.yaml up -d --wait
```

Open http://127.0.0.1:6086/vnc.html?autoconnect=1&resize=scale.
This deployment has its own workspace and preferences volumes. The existing
desktop on port 6080 and initial candidate on port 6085 remain independent.
Use `OPENBEXI_V05_PORT` to change the
new deployment's loopback port. `docker compose -f compose.v05.yaml stop` stops
this desktop while preserving its files; `start` resumes it.

The image ID built from the retained v0.5 source snapshot is
`sha256:286d3aa543de6a5e56363f6cec8ee1e6bade8b7150ddb134c042856b722dea7d`.
It is a local image, not a published registry download. On another machine,
build the v0.5 checkout with the sibling plugin repository present:

```powershell
docker build --build-context spell_plugin=../openbexi_spell_plugin -f docker/Dockerfile -t openbexi-ide:0.5.0rc2 .
```

Rebuilding can produce a different image ID because Debian packages and build
metadata are not fully reproducible. The source and locked Python dependencies
are retained separately in qualification evidence. The Docker lab includes a
bounded SPELL/DSS fixture; full original native SPELL conformance is a separate
plugin milestone. Shared debugging here supports Python/debugpy. The rc2
candidate fixes typing menu choices at the visible console prompt and tracks
the additional POSIX process group created by debugpy before reusing a slot.

Service health does not establish browser interaction acceptance. Actual noVNC
X-button closure and wheel scrolling remain pending until browser control is
available. This is a usable prerelease, not final v0.5 release acceptance.
