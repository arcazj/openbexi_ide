FROM openbexi-v08-local-qualification-runner:20261104-durable
USER root
RUN printf '%s\n' '#10003 ALL=(root) NOPASSWD: /usr/bin/python3, /usr/local/bin/python3' > /etc/sudoers.d/openbexi-qualification-observer && chmod 0440 /etc/sudoers.d/openbexi-qualification-observer && visudo -cf /etc/sudoers.d/openbexi-qualification-observer
USER 10003:10003
