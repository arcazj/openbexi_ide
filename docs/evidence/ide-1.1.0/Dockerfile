FROM openbexi-ide:1.1-build-base-fe526165
USER root
COPY openbexi_ide-1.1.0-py3-none-any.whl /opt/wheels/
RUN python -m pip install --no-index --no-deps --force-reinstall /opt/wheels/openbexi_ide-1.1.0-py3-none-any.whl
RUN rm -f /opt/wheels/openbexi_ide-1.2.0rc1-py3-none-any.whl /opt/wheels/openbexi_ide-1.2.0.dev1-py3-none-any.whl
COPY src /opt/openbexi/src
COPY tests /opt/openbexi/tests
COPY pyproject.toml README.md /opt/openbexi/
COPY checks /opt/v11-checks
LABEL org.openbexi.qualification="ide-v1.1" org.opencontainers.image.version="1.1.0" org.opencontainers.image.source="https://github.com/arcazj/openbexi_ide"
USER 10003:10003
