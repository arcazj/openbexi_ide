ARG NATIVE_IMAGE
ARG DESKTOP_IMAGE
FROM ${NATIVE_IMAGE} AS native
FROM ${DESKTOP_IMAGE}
USER root
RUN rm -rf /opt/qualification-inputs /opt/test-lab /opt/openbexi /evidence \
    && rm -f /opt/wheels/openbexi*.whl \
    && install -d -m 0755 -o 10003 -g 10003 /evidence
COPY --from=native /opt/v08-native-home/ /opt/v08-native-home/
COPY --from=native /usr/local/lib/python3.13/site-packages/spell_native/ /usr/local/lib/python3.13/site-packages/spell_native/
COPY --from=native /usr/local/lib/python3.13/site-packages/libSPELL_DTA_v3.py /usr/local/lib/python3.13/site-packages/
COPY --from=native /usr/local/lib/python3.13/site-packages/libSPELL_DTA_v3.py /opt/spell-native/lib/python3.13/site-packages/
COPY wheels/ /opt/qualification-inputs/wheels/
COPY published-pair.json verify_installed.py verify_v08_native.py /opt/qualification-inputs/
COPY ide/examples/ /opt/openbexi/examples/
COPY ide/scripts/distribution_desktop.py /opt/openbexi/scripts/
COPY v08_desktop.py /opt/test-lab/
RUN ln -s v08_desktop.py /opt/test-lab/health.py
ENV LD_LIBRARY_PATH=/opt/v08-native-home/bin:/opt/spell-native/lib \
    OPENBEXI_SPELL_BACKEND="" OPENBEXI_DSS_URL=""
RUN python -m pip install --no-index --no-deps --force-reinstall /opt/qualification-inputs/wheels/*.whl \
    && python -I /opt/qualification-inputs/verify_installed.py \
    && python -I /opt/qualification-inputs/verify_v08_native.py \
    && python -m pip check
LABEL org.opencontainers.image.version="1.2.2-spell-0.8.0-candidate" \
      org.openbexi.qualification="incomplete" org.openbexi.native-base.version="0.8.0-candidate" \
      org.openbexi.spell.version="0.8.0"
USER 10003:10003
HEALTHCHECK --interval=10s --start-period=35s CMD ["python","-I","/opt/test-lab/v08_desktop.py","health"]
ENTRYPOINT ["python","-I","/opt/test-lab/v08_desktop.py"]
CMD ["desktop"]
