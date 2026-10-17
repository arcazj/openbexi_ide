# Installed v0.5 native runtime plus the existing desktop, for learning-lab validation.
# Production v0.6 images are rebuilt separately from the locked dependency archive.
ARG NATIVE_IMAGE
ARG DESKTOP_IMAGE
FROM ${NATIVE_IMAGE} AS native
USER root
RUN mkdir /native-libs && python -c "import pathlib,subprocess,shutil; lines=subprocess.check_output(['ldd','/bridge/spell-host-ipc'],text=True).splitlines(); paths=[line.split('=>')[1].split()[0] for line in lines if '=>' in line]; [shutil.copy2(p,'/native-libs/'+pathlib.Path(p).name) for p in paths if p.startswith('/lib/') and pathlib.Path(p).name not in ('libc.so.6','libm.so.6','libresolv.so.2')]"

FROM ${DESKTOP_IMAGE}
USER root
ENV SOURCE_DATE_EPOCH=315532800
RUN python -m venv /opt/spell-native
COPY --from=native /usr/local/lib/python3.13/site-packages/ /opt/spell-native/lib/python3.13/site-packages/
COPY --from=native /native-libs/ /opt/spell-native/lib/
COPY --from=native /bridge/ /bridge/
COPY --from=spell_plugin host_runtime/python/ /opt/host/
COPY --from=spell_plugin src/dss/ /opt/spell-native/lib/python3.13/site-packages/dss/
COPY --from=spell_plugin host_plugin/ /opt/native-host-package/
RUN python -m pip wheel --no-deps --no-build-isolation -w /opt/wheels /opt/native-host-package \
    && python -m pip install --no-index --no-deps /opt/wheels/openbexi_spell_host-*.whl \
    && printf '%s\n' '#!/opt/spell-native/bin/python' 'from spell_native.launcher import main' 'raise SystemExit(main())' > /opt/spell-native/bin/spell-native \
    && chmod 755 /opt/spell-native/bin/spell-native
RUN rm -rf /opt/openbexi/examples
COPY examples/ /opt/openbexi/examples/
COPY pyproject.toml README.md LICENSE NOTICE run_cli.py run_ide.py /opt/openbexi/
COPY src/ /opt/openbexi/src/
COPY tests/ /opt/openbexi/tests/
RUN rm -f /opt/wheels/openbexi_ide-*.whl \
    && python -m pip wheel --no-deps --no-build-isolation -w /opt/wheels /opt/openbexi \
    && python -m pip install --no-index --no-deps --force-reinstall /opt/wheels/openbexi_ide-*.whl
COPY docker/ /opt/test-lab/
COPY docker/ /opt/openbexi/docker/
RUN /opt/spell-native/bin/python -I /opt/test-lab/native_manifest.py
ENV OPENBEXI_SPELL_BACKEND=packaged-desktop \
    LD_LIBRARY_PATH=/opt/spell-native/lib:/opt/spell-native/lib/python3.13/site-packages/spell_native/bin \
    ASAN_OPTIONS=detect_leaks=0:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1
USER 10003:10003
