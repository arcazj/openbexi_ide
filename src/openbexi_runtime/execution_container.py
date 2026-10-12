"""Owned Docker process and bounded private control transport."""
from __future__ import annotations

import json
import os
import subprocess
import threading

from .execution_release import docker, image_info, isolation_options
from .processes import start_owned_process


def container_name(session, procedure):
    return 'openbexi-execution-' + session + '-' + procedure


class ContainerOwner:
    def __init__(self, session, procedure, manifest):
        self.name = container_name(session, procedure.id)
        self.labels = {'org.openbexi.session': session, 'org.openbexi.procedure': procedure.id}
        self.closed = False
        self.started = False
        self.cli_owner = None
        self.lock = threading.RLock()
        image_info(manifest['image'])
        security = json.loads(docker('info', '--format', '{{json .SecurityOptions}}'))
        if not any('seccomp' in option for option in security):
            raise ValueError('Execution requires Docker seccomp support')
        bootstrap = "import sys;sys.path.insert(0,'/opt/openbexi-runtime');from openbexi_runtime.execution_transport import main;main()"
        command = ['create', '--interactive', '--name', self.name, *isolation_options(),
                   '--label', 'org.openbexi.session=' + session,
                   '--label', 'org.openbexi.procedure=' + procedure.id,
                   '--entrypoint=python', manifest['image'], '-I', '-B', '-u', '-c', bootstrap,
                   '/release', '/release/' + procedure.script, *procedure.spec.arguments]
        self.identifier = docker(*command).decode().strip()
        info = self.inspect()
        host = info['HostConfig']
        if (info['Mounts'] or not host['ReadonlyRootfs'] or host['Privileged']
                or host['NetworkMode'] != 'none' or info['Config']['User'] != '65532:65532'):
            self.close()
            raise ValueError('Container isolation configuration differs')

    def inspect(self):
        info = json.loads(docker('inspect', self.name, timeout=5))[0]
        labels = info['Config'].get('Labels') or {}
        if info['Id'] != self.identifier or any(labels.get(k) != v for k, v in self.labels.items()):
            raise ValueError('Execution container ownership differs')
        return info

    def start(self):
        self.started = True
        process, self.cli_owner = start_owned_process(
            ['docker', 'start', '--attach', '--interactive', self.identifier],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=os.name != 'nt',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        return process

    def process_ids(self):
        if self.closed:
            return set()
        try:
            lines = docker('top', self.identifier, '-eo', 'pid,stat', timeout=3).decode().splitlines()[1:]
            return {int(line.split()[0]) for line in lines if not line.split()[1].startswith('Z')}
        except (ValueError, OSError, subprocess.SubprocessError):
            return None

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.inspect()
            docker('rm', '--force', self.identifier, timeout=5)
            self.closed = True
            if self.cli_owner:
                self.cli_owner.close()


def recover_container(session, procedure):
    """Stop only the recorded container; retain the procedure's recovery hold."""
    name = container_name(session, procedure)
    rows = docker('ps', '-a', '--filter', 'name=^/' + name + '$', '--format', '{{.ID}}').decode().splitlines()
    if not rows:
        return
    info = json.loads(docker('inspect', name))[0]
    labels = info['Config'].get('Labels') or {}
    if labels.get('org.openbexi.session') != session or labels.get('org.openbexi.procedure') != procedure:
        raise ValueError('Recovery container ownership differs; maintenance required')
    docker('rm', '--force', info['Id'], timeout=5)


class ContainerChannel:
    def __init__(self, session, procedure):
        self.session, self.procedure = session, procedure
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.error = None

    def send(self, value):
        with self.lock:
            self.procedure.process.stdin.write((json.dumps(value, ensure_ascii=True) + '\n').encode())
            self.procedure.process.stdin.flush()

    def heartbeat(self):
        try:
            while not self.done.wait(0.5):
                if self.session.closed.is_set() or self.procedure.cancelled:
                    return
                self.send({'type': 'heartbeat'})
        except (OSError, ValueError):
            return

    def read(self):
        try:
            while raw := self.procedure.process.stdout.readline(262144):
                if not raw.endswith(b'\n'):
                    raise ValueError('Execution worker frame exceeds its bound')
                message = json.loads(raw)
                if message['type'] == 'output':
                    if message['stream'] not in {'stdout', 'stderr'} or len(message['text']) > 8192:
                        raise ValueError('Invalid execution output frame')
                    self.session.event('output', procedure=self.procedure.id,
                                       stream=message['stream'], text=message['text'])
                elif message['type'] == 'checkpoint':
                    action = self.session.checkpoint(message['body'], isolated=True)['action']
                    self.send({'type': 'reply', 'action': action})
                else:
                    raise ValueError('Invalid execution worker frame')
        except BaseException as error:
            if not self.session.closed.is_set() and not self.procedure.cancelled:
                self.error = str(error)
            try:
                self.procedure.owner.close()
            except (ValueError, OSError, subprocess.SubprocessError):
                pass  # The execution thread retries cleanup and retains a hold.
        finally:
            self.done.set()
