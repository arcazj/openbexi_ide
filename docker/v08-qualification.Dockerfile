ARG DESKTOP_IMAGE
FROM ${DESKTOP_IMAGE}
USER root
# Remove inherited source/test outputs and obsolete wheel caches in this new image.
RUN rm -rf /opt/openbexi /opt/test-lab /evidence \
    && rm -f /opt/wheels/openbexi_ide-*.whl /opt/wheels/openbexi_spell_host-*.whl \
    && install -d -m 0755 -o 10003 -g 10003 /evidence
COPY wheels/ /opt/qualification-inputs/wheels/
COPY wheels/ /opt/wheels/
COPY published-pair.json verify_installed.py /opt/qualification-inputs/
COPY ide/ /opt/openbexi/
COPY ide/docker/ /opt/test-lab/
RUN python -m pip install --no-index --no-deps --force-reinstall /opt/qualification-inputs/wheels/*.whl \
    && python -I /opt/qualification-inputs/verify_installed.py \
    && python -m pip check
LABEL org.opencontainers.image.version="1.2.1-spell-0.8.0rc1-local-qualification" \
      org.openbexi.qualification="incomplete" \
      org.openbexi.native-base.version="0.7.0"
USER 10003:10003
