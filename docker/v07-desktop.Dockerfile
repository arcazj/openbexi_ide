# Offline integration of the published SPELL v0.7 runtime and host wheel.
ARG NATIVE_IMAGE=openbexi-v07-native-input:d99b095d65c7fef008f9e6c02ff95c678cff295ee85a129f7a62fc0b795b1283
ARG DESKTOP_IMAGE=openbexi-v07-desktop-input:aaf3d19d5a98a39c8b82c477e3fbbd2bfafc57ef627f31c0c0202c0c37e60d1d
FROM ${NATIVE_IMAGE} AS native
USER root
RUN mkdir /native-libs && python -c "import pathlib,subprocess,shutil; lines=subprocess.check_output(['ldd','/bridge/spell-host-ipc'],text=True).splitlines(); paths=[line.split('=>')[1].split()[0] for line in lines if '=>' in line]; [shutil.copy2(p,'/native-libs/'+pathlib.Path(p).name) for p in paths if p.startswith('/lib/') and pathlib.Path(p).name not in ('libc.so.6','libm.so.6','libresolv.so.2')]"

FROM ${DESKTOP_IMAGE}
USER root
ENV SOURCE_DATE_EPOCH=315532800
RUN rm -rf /opt/spell-native /opt/host /bridge /opt/native-host-package /opt/v11-checks \
    && python -m venv /opt/spell-native \
    && rm -f /opt/wheels/openbexi_spell_host-*.whl /opt/wheels/openbexi_ide-*.whl
COPY --from=native /usr/local/lib/python3.13/site-packages/ /opt/spell-native/lib/python3.13/site-packages/
COPY --from=native /native-libs/ /opt/spell-native/lib/
COPY --from=native /bridge/ /bridge/
COPY --from=native /opt/host/ /opt/host/
COPY --from=v07_artifacts openbexi_spell_host-0.7.0-py3-none-any.whl /opt/wheels/
COPY --from=v07_artifacts openbexi_spell_plugin-0.1.0-py3-none-any.whl /opt/wheels/
RUN python -m pip install --no-index --no-deps --force-reinstall /opt/wheels/openbexi_spell_host-0.7.0-py3-none-any.whl /opt/wheels/openbexi_spell_plugin-0.1.0-py3-none-any.whl \
    && cp -a /usr/local/lib/python3.13/site-packages/dss /opt/spell-native/lib/python3.13/site-packages/ \
    && printf '%s\n' '#!/opt/spell-native/bin/python' 'from spell_native.launcher import main' 'raise SystemExit(main())' > /opt/spell-native/bin/spell-native \
    && chmod 755 /opt/spell-native/bin/spell-native \
    && rm -rf /opt/openbexi/src /opt/openbexi/tests /opt/openbexi/examples /opt/openbexi/scripts
COPY pyproject.toml README.md LICENSE NOTICE run_cli.py run_ide.py /opt/openbexi/
COPY src/ /opt/openbexi/src/
COPY tests/ /opt/openbexi/tests/
COPY examples/ /opt/openbexi/examples/
COPY scripts/ /opt/openbexi/scripts/
COPY docker/ /opt/test-lab/
COPY docker/ /opt/openbexi/docker/
RUN python -m pip wheel --no-deps --no-build-isolation -w /opt/wheels /opt/openbexi \
    && python -m pip install --no-index --no-deps --force-reinstall /opt/wheels/openbexi_ide-1.2.0-py3-none-any.whl \
    && /opt/spell-native/bin/python -I /opt/test-lab/native_manifest.py
ENV OPENBEXI_SPELL_BACKEND=packaged-desktop \
    LD_LIBRARY_PATH=/opt/spell-native/lib:/opt/spell-native/lib/python3.13/site-packages/spell_native/bin \
    ASAN_OPTIONS=detect_leaks=0:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1
LABEL org.opencontainers.image.version="1.2.0" org.openbexi.spell.version="0.7.0" \
    org.opencontainers.image.source="https://github.com/arcazj/openbexi_ide"
USER 10003:10003
