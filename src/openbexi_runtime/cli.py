"""Headless Python execution and shared local-development sessions."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler

from .launch import LaunchSpec, clean_environment, interpreter_info
from .processes import ProcessTree, own_worker_tree


def private_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.chmod(0o600)
    if os.name == 'nt':
        account = os.environ.get('USERDOMAIN', '.') + '\\' + os.environ['USERNAME']
        result = subprocess.run(['icacls', str(temporary), '/inheritance:r', '/grant:r', account + ':(F)'],
                                capture_output=True)
        if result.returncode:
            temporary.unlink(missing_ok=True)
            raise ValueError('Could not restrict the credential file to the current user')
    temporary.replace(path)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Session redirects are not accepted')


def request(url, path, body=None, token=None, *, tls=None):
    if tls is not None and (type(tls) is not dict or set(tls) - {'ca', 'certificate', 'key'}
                            or any(value is not None and not isinstance(value, str) for value in tls.values())):
        raise ValueError('Invalid session TLS configuration')
    parsed = urlsplit(url)
    if parsed.scheme not in {'http', 'https'} or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Use an HTTP(S) session URL without embedded credentials')
    if parsed.scheme == 'http' and parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise ValueError('Use HTTPS or a loopback authenticated tunnel for a remote session')
    if tls and parsed.scheme != 'https':
        raise ValueError('Certificate identities require HTTPS')
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    message = Request(url.rstrip('/') + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
    try:
        handlers = [NoRedirect()]
        if tls:
            from .session_identity import client_context
            handlers.append(HTTPSHandler(context=client_context(**tls)))
        with build_opener(*handlers).open(message, timeout=5) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            explanation = json.load(error).get('error', str(error))
        except ValueError:
            explanation = str(error)
        raise ValueError(explanation) from error


def emit(value):
    print(json.dumps(value, indent=2, ensure_ascii=False))


def parser():
    root = argparse.ArgumentParser(prog='openbexi', description=__doc__)
    root.add_argument('--connection', default='.session/client.json', help='Private connection credential file')
    root.add_argument('--version', action='version', version='openbexi_ide 0.3.0')
    commands = root.add_subparsers(dest='command', required=True)
    local = commands.add_parser('run', help='Run a local Python/SPELL file without a session')
    local.add_argument('script')
    local.add_argument('--project', default='.')
    local.add_argument('--python', default=sys.executable)
    local.add_argument('--language', default='python', help='Python or an installed runtime backend ID')
    local.add_argument('--dss-url')
    local.add_argument('--arguments', nargs=argparse.REMAINDER, default=[])
    server = commands.add_parser('serve', help='Start a shared Development session')
    server.add_argument('--project', default='.')
    server.add_argument('--python', default=sys.executable)
    server.add_argument('--host', default='127.0.0.1')
    server.add_argument('--port', type=int, default=9010)
    server.add_argument('--max-parallel', type=int, default=1)
    server.add_argument('--lease-seconds', type=float, default=30)
    server.add_argument('--dss-url')
    server.add_argument('--info', default='.session/server.json')
    server.add_argument('--state-directory', help='Durable authority directory; requires committed Git sources')
    server.add_argument('--execution-release', help='Approved release SHA-256; isolated offline Python Execution')
    server.add_argument('--tls-cert')
    server.add_argument('--tls-key')
    server.add_argument('--client-ca')
    server.add_argument('--identities', help='Server-owned certificate fingerprint/role JSON')
    connect = commands.add_parser('connect', help='Join as a developer or read-only monitor')
    connect.add_argument('--url')
    connect.add_argument('--user', required=True)
    connect.add_argument('--invite')
    connect.add_argument('--invite-file', help='Private server-info or invitation JSON')
    connect.add_argument('--role', choices=('developer', 'monitor'), default='developer')
    connect.add_argument('--tls-ca')
    connect.add_argument('--tls-cert')
    connect.add_argument('--tls-key')
    handoff = commands.add_parser('handoff', help='Pause work and offer controller handoff to a connected developer')
    handoff.add_argument('target')
    reconcile = commands.add_parser('reconcile', help='Offline maintenance after verifying worker shutdown and external effects')
    reconcile.add_argument('--state-directory', required=True)
    reconcile.add_argument('--receipt', required=True, help='Identity-bound JSON with shutdown and effect settlement evidence')
    prepare = commands.add_parser('release-prepare', help='Build an immutable runtime release without approving it')
    prepare.add_argument('script')
    prepare.add_argument('--project', required=True)
    prepare.add_argument('--runtime-image', required=True, help='Exact local Linux amd64 Docker image ID')
    prepare.add_argument('--backend', help='Installed shared provider for an isolated plugin release')
    prepare.add_argument('--output', required=True, help='New directory for retained source, recipe and manifest')
    prepare.add_argument('--procedure', action='append', default=[], help='Additional explicitly released Python procedure')
    approve = commands.add_parser('release-approve', help='Offline approval of reviewed source and runtime')
    approve.add_argument('--manifest', required=True)
    approve.add_argument('--expected-release', required=True, help='Reviewed manifest SHA-256')
    revoke = commands.add_parser('release-revoke', help='Offline revocation; queued work cannot bypass it')
    revoke.add_argument('--release', required=True)
    for command in (approve, revoke):
        command.add_argument('--state-directory', required=True)
        command.add_argument('--actor', required=True)
        command.add_argument('--evidence', required=True, help='Reference to retained review or revocation evidence')
    for name in ('claim', 'renew', 'release', 'disconnect', 'status', 'stack'):
        commands.add_parser(name)
    configure = commands.add_parser('configure', help='Change the controller-owned execution slot limit')
    configure.add_argument('--max-parallel', type=int, required=True)
    submit = commands.add_parser('submit', help='Queue a procedure in the connected session')
    submit.add_argument('script')
    submit.add_argument('--language', choices=('python', 'spell'), default='python')
    submit.add_argument('--arguments', nargs=argparse.REMAINDER, default=[])
    for name in ('pause', 'resume', 'stop'):
        item = commands.add_parser(name)
        item.add_argument('procedure', help='Procedure ID, or all')
    input_command = commands.add_parser('input')
    input_command.add_argument('procedure')
    input_command.add_argument('text', nargs='?')
    watch = commands.add_parser('watch', help='Stream output and procedure state')
    watch.add_argument('--renew', action='store_true', help='Keep this controller lease alive explicitly')
    watch.add_argument('--duration', type=float, default=0, help='Seconds, or zero until interrupted')
    return root


def run_local(args):
    info = interpreter_info(args.python)
    spec = LaunchSpec(Path(args.project), Path(args.project) / args.script,
                      Path(args.python), tuple(args.arguments)).validate()
    command, environment = spec.command(), clean_environment()
    installed = next((item for item in info.get('backends', []) if item['id'] == args.language), None)
    if installed:
        spec = LaunchSpec(spec.project, spec.script, spec.interpreter, spec.arguments, args.language)
        command = spec.command(installed)
    elif args.language == 'spell':
        from .languages import check_spell
        check_spell(spec.interpreter)
        command = [str(spec.interpreter), '-I', '-B', '-u', '-X', 'utf8', '-m',
                   'openbexi_spell_plugin.runner', str(spec.project), str(spec.script), *spec.arguments]
        if args.dss_url:
            environment['OPENBEXI_DSS_URL'] = args.dss_url
    elif args.language != 'python':
        raise ValueError(f'Install the {args.language} backend in the selected interpreter first')
    process = subprocess.Popen(command, cwd=spec.project, env=environment, start_new_session=os.name != 'nt')
    owner = None
    try:
        owner = ProcessTree(process.pid)
        return process.wait()
    finally:
        if owner:
            owner.close()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


def serve(args):
    from .session import Session
    from .session_http import SessionServer
    own_worker_tree()
    tls = None
    identities = None
    if any((args.tls_cert, args.tls_key, args.client_ca, args.identities)):
        if not all((args.tls_cert, args.tls_key, args.client_ca, args.identities, args.state_directory)):
            raise ValueError('Remote TLS requires certificate, key, client CA, identities and durable state directory')
        from .session_identity import server_context, CertificateIdentities
        tls = server_context(args.tls_cert, args.tls_key, args.client_ca)
        identities = CertificateIdentities(args.identities)
    session = Session(Path(args.project), max_parallel=args.max_parallel, lease_seconds=args.lease_seconds,
                      interpreter=Path(args.python), dss_url=args.dss_url, state_directory=args.state_directory,
                      execution_release=args.execution_release)
    server = worker_server = worker_thread = None
    try:
        if tls:
            import threading
            worker_server = SessionServer(('127.0.0.1', 0), session, worker_only=True)
            worker_thread = threading.Thread(target=worker_server.serve_forever, daemon=True)
            worker_thread.start()
        server = SessionServer((args.host, args.port), session, tls_context=tls, identities=identities)
        url = f'https://{args.host}:{server.server_port}' if tls else session.worker_url
        info = {'url': url, 'session': session.id, 'pid': os.getpid(), 'certificate_identity': bool(tls)}
        if not tls:
            info.update(developer_invite=session.developer_invite, monitor_invite=session.monitor_invite)
        private_json(args.info, info)
        print(f'Session ready: {url}\nPrivate connection information: {Path(args.info).resolve()}', flush=True)
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        session.close()
        if server:
            server.server_close()
        if worker_server:
            worker_server.shutdown()
            worker_server.server_close()
            worker_thread.join(timeout=5)
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    args = parser().parse_args(argv)
    try:
        if args.command == 'run':
            return run_local(args)
        if args.command == 'serve':
            return serve(args)
        if args.command == 'release-prepare':
            from .execution_release import prepare
            emit(prepare(args.project, args.script, args.runtime_image, args.output,
                         additional_procedures=args.procedure,backend=args.backend))
            return 0
        if args.command in {'release-approve', 'release-revoke'}:
            from .execution_release import ReleaseAuthority, read_manifest, digest
            from .session_store import SessionStore
            store = SessionStore(args.state_directory)
            try:
                authority = ReleaseAuthority(store)
                if args.command == 'release-approve':
                    manifest = read_manifest(args.manifest)
                    if digest(manifest) != args.expected_release:
                        raise ValueError('Reviewed release identity differs from the supplied manifest')
                else:
                    manifest = authority.require(args.release)
                emit(authority.decide(manifest, approved=args.command == 'release-approve',
                                      actor=args.actor, evidence=args.evidence))
            finally:
                store.close()
            return 0
        if args.command == 'reconcile':
            from .session_store import SessionStore
            receipt = Path(args.receipt)
            if receipt.stat().st_size > 8192:
                raise ValueError('Reconciliation receipt exceeds its bound')
            from .session_identity import unique_object
            value = json.loads(receipt.read_text(encoding='utf-8'), object_pairs_hook=unique_object)
            store = SessionStore(args.state_directory)
            try:
                emit(store.reconcile(value))
            finally:
                store.close()
            return 0
        if args.command == 'connect':
            info = json.loads(Path(args.invite_file).read_text(encoding='utf-8')) if args.invite_file else {}
            url, invite = args.url or info.get('url'), args.invite or info.get(args.role + '_invite')
            tls = ({'ca': args.tls_ca, 'certificate': args.tls_cert, 'key': args.tls_key}
                   if any((args.tls_ca, args.tls_cert, args.tls_key)) else info.get('tls'))
            if tls and not any((args.tls_ca, args.tls_cert, args.tls_key)):
                tls = {key: str((Path(args.invite_file).resolve().parent / value).resolve()) if value else None
                       for key, value in tls.items()}
            if not url or not (invite or tls):
                raise ValueError('Supply a URL and invitation, or --invite-file')
            result = request(url, '/connect', {'name': args.user, 'invite': invite}, tls=tls)
            if result.get('role') != args.role:
                request(url, '/disconnect', {}, result['token'], tls=tls)
                raise ValueError('Invitation role does not match the selected connection role')
            if tls:
                tls = {key: str(Path(value).resolve()) if value else None for key, value in tls.items()}
            private_json(args.connection, {'url': url, 'tls': tls, **result})
            emit({key: value for key, value in result.items() if key != 'token'})
            return 0
        connection = json.loads(Path(args.connection).read_text(encoding='utf-8'))
        url, token = connection['url'], connection['token']
        from functools import partial
        call = partial(request, tls=connection.get('tls'))
        if args.command in {'status', 'stack'}:
            result = call(url, '/session', token=token)
            emit(result if args.command == 'status' else [{'id': p['id'], 'script': p['script'], 'status': p['status'], 'threads': p['threads']} for p in result['procedures']])
        elif args.command == 'watch':
            cursor, started, last_renew, previous = 0, time.monotonic(), 0, None
            while not args.duration or time.monotonic()-started < args.duration:
                if args.renew and time.monotonic()-last_renew >= 0.2:
                    call(url, '/renew', {'epoch': connection.get('epoch')}, token)
                    last_renew = time.monotonic()
                result = call(url, f'/session?after={cursor}', token=token)
                if result['replay_gap']:
                    print('[Earlier session events are no longer retained]', flush=True)
                for event in result['events']:
                    if event['type'] == 'output':
                        print(event['text'], end='', flush=True)
                state = [(p['id'], p['status'], p['pause_reason']) for p in result['procedures']]
                if state != previous:
                    emit({'controller': result['controller'], 'procedures': state})
                    previous = state
                cursor = result['cursor']
                time.sleep(0.1)
        else:
            body = {'epoch': connection.get('epoch')}
            route = '/' + args.command
            if args.command == 'submit':
                route = '/run'
                body.update(script=args.script, language=args.language, arguments=args.arguments)
            elif args.command == 'configure':
                body['max_parallel'] = args.max_parallel
            elif args.command == 'handoff':
                body['target'] = args.target
            elif args.command in {'pause', 'resume', 'stop', 'input'}:
                body['procedure'] = args.procedure
                if args.command == 'input':
                    body['text'] = args.text
            result = call(url, route, body, token)
            if args.command == 'claim':
                connection['epoch'] = result['epoch']
                private_json(args.connection, connection)
            elif args.command == 'release':
                connection.pop('epoch', None)
                private_json(args.connection, connection)
            elif args.command == 'disconnect':
                private_json(args.connection, {'disconnected': True})
            emit(result)
        return 0
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        print(f'openbexi: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
