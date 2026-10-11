# syntax=docker/dockerfile:1
FROM python:3.13.15-slim@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git openssl xvfb x11vnc novnc websockify openbox xterm x11-utils \
    fonts-dejavu-core fonts-liberation libgl1 libegl1 libopengl0 libglib2.0-0 \
    libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-render-util0 libxcb-xinerama0 libxcb-randr0 libxcb-shape0 libxcb-xfixes0 \
    libdbus-1-3 tk8.6 libtk8.6 \
    && rm -rf /var/lib/apt/lists/*

COPY build-requirements.lock /opt/build-requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /opt/build-requirements.lock
COPY docker/requirements-linux.lock /opt/requirements-linux.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /opt/requirements-linux.lock

# Named context is the sibling plugin, not the parent projects/archive directory.
# Only the bounded distribution sources are copied, never private qualification data.
COPY --from=spell_plugin pyproject.toml README.md LICENSE NOTICE /opt/spell-plugin/
COPY --from=spell_plugin src /opt/spell-plugin/src
RUN python -m pip wheel --no-deps --no-build-isolation --wheel-dir /opt/wheels /opt/spell-plugin \
    && python -m pip install --no-index --no-deps /opt/wheels/openbexi_spell_plugin-*.whl

COPY pyproject.toml README.md LICENSE NOTICE run_cli.py run_ide.py /opt/openbexi/
COPY src /opt/openbexi/src
COPY tests /opt/openbexi/tests
COPY examples /opt/openbexi/examples
COPY scripts /opt/openbexi/scripts
RUN python -m pip wheel --no-deps --no-build-isolation --wheel-dir /opt/wheels /opt/openbexi \
    && python -m pip install --no-index --no-deps /opt/wheels/openbexi_ide-*.whl

COPY docker /opt/test-lab
COPY docker/index.html /usr/share/novnc/index.html
RUN groupadd --gid 10003 tester \
    && useradd --uid 10003 --gid 10003 --create-home --shell /bin/bash tester \
    && mkdir -p /workspace /evidence \
    && chown -R tester:tester /workspace /evidence /opt/openbexi \
    && printf '%s\n' '#!/bin/sh' 'exec python -I /opt/test-lab/launch.py "$@"' > /usr/local/bin/openbexi-lab \
    && chmod 755 /usr/local/bin/openbexi-lab
ENV DISPLAY=:0 QT_X11_NO_MITSHM=1 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    OPENBEXI_DSS_URL=http://127.0.0.1:8085 LANG=C.UTF-8 LC_ALL=C.UTF-8
USER 10003:10003
WORKDIR /workspace
EXPOSE 6080
LABEL org.opencontainers.image.title="OpenBEXI IDE test desktop" \
      org.openbexi.scope="Development and Monitoring test fixture; v0.3 incomplete"
ENTRYPOINT ["python", "-I", "/opt/test-lab/start.py"]
CMD ["desktop"]
