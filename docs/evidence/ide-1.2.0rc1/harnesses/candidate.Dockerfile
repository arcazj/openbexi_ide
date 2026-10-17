FROM openbexi-ide:1.2.0rc1-build-input
USER root
COPY openbexi_ide-1.2.0rc1-py3-none-any.whl /opt/wheels/openbexi_ide-1.2.0rc1-py3-none-any.whl
RUN rm /opt/wheels/openbexi_ide-1.2.0.dev1-py3-none-any.whl && python -m pip install --no-index --no-deps --force-reinstall /opt/wheels/openbexi_ide-1.2.0rc1-py3-none-any.whl
COPY pyproject.toml README.md /opt/openbexi/
COPY qualify_procedure_workspace.py distribution_desktop.py distribution_shared_debug.py /opt/rc1-checks/
LABEL org.opencontainers.image.version="1.2.0rc1" org.opencontainers.image.source="https://github.com/arcazj/openbexi_ide"
USER 10003:10003
