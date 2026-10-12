"""Optional installed Development workers; no domain runtime is imported here."""
from importlib.metadata import entry_points
import json


def load_backend(name):
    matches = list(entry_points(group='openbexi.shared_backends.v1', name=name))
    if len(matches) != 1:
        raise ValueError('Durable shared backend requires exactly one installed provider: ' + name)
    provider = matches[0].load()
    if getattr(provider, 'api', None) != 1 or any(not callable(getattr(provider, method, None))
                              for method in ('bind', 'create', 'recover')):
        raise ValueError('Unsupported shared backend contract')
    return provider


def bind_backend(name):
    binding = load_backend(name).bind()
    # Bindings are persisted and form part of the procedure version identity.
    raw = json.dumps(binding, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if type(binding) is not dict or len(raw) > 8192:
        raise ValueError('Invalid shared backend runtime binding')
    return json.loads(raw)


def execute(session, procedure):
    """Own a plugin worker, retaining a slot until whole-worker pause is proven.

    start() leaves user code paused. resume() and pause() are synchronous; pause
    must confirm quiescence of every owned process before returning. A provider
    failure always retains an uncertain-effect hold. No plugin checkpoint can
    grant itself a slot. Providers run as trusted installed service extensions.
    """
    import queue
    import threading
    from .source_capture import verify_capture
    code = None
    owns_attempt = False
    try:
        with session.lock:
            if (not procedure.has_token or session.closed.is_set()
                    or procedure.thread is not threading.current_thread()):
                return
            owns_attempt = True
            verify_capture(procedure.spec.project, procedure.capture_digest)
            provider = load_backend(procedure.language)
            procedure.owner = provider.create(session.id, procedure.id, procedure.backend,
                procedure.spec.project, procedure.script, procedure.spec.arguments,
                results=session.store.directory / 'results')
            # Persist ownership before any external process/container is created.
            session.event('backend_starting', procedure=procedure.id, backend=procedure.backend)
        procedure.owner.start()
        with session.lock:
            procedure.process = procedure.owner.process
            session.event('started', procedure=procedure.id, pid=procedure.process.pid)
        while not session.closed.is_set() and not procedure.cancelled:
            with session.lock:
                session._expire()
                if procedure.status == 'PAUSING':
                    procedure.owner.pause()
                    procedure.status, procedure.has_token = 'PAUSED', False
                    session.event('paused', procedure=procedure.id, reason=procedure.reason)
                    session._dispatch()
                elif procedure.has_token and procedure.wants_run and session.controller:
                    procedure.owner.resume()
                    if procedure.status == 'STARTING':
                        procedure.status = 'RUNNING'
                        session.event('backend_running', procedure=procedure.id)
                    try:
                        chunk = procedure.input_queue.get_nowait()
                    except queue.Empty:
                        pass
                    else:
                        procedure.owner.input(None if chunk is None else chunk.decode('utf-8').removesuffix('\n'))
            # Idle polls return promptly; a terminal receipt may include bounded
            # native shutdown verification and artifact export.
            event = procedure.owner.poll()
            if event is None:
                continue
            if event.get('type') == 'output':
                if event.get('stream') not in {'stdout', 'stderr'} or not isinstance(event.get('text'), str) or len(event['text']) > 8192:
                    raise ValueError('Invalid shared backend output')
                session.event('output', procedure=procedure.id, stream=event['stream'], text=event['text'])
            elif event.get('type') == 'finished' and type(event.get('exit_code')) is int:
                code = event['exit_code']
                break
            else:
                raise ValueError('Invalid shared backend event')
    except BaseException as error:
        procedure.error = str(error)
    finally:
        if not owns_attempt:
            return  # A superseded launch attempt owns no worker or state.
        if procedure.owner:
            try:
                procedure.owner.close()
            except BaseException as error:
                procedure.error, code = str(error), None
        with session.lock:
            procedure.exit_code = code
            # A pre-launch cancellation is resumable. Once ownership has been
            # committed, anything short of confirmed completion requires review.
            if procedure.owner or procedure.error:
                procedure.has_token, procedure.wants_run = False, False
                procedure.uncertain = bool(procedure.owner and (code != 0 or procedure.cancelled or procedure.error))
                procedure.status = 'RECOVERY_REQUIRED' if procedure.uncertain else 'COMPLETED' if code == 0 else 'FAILED'
                procedure.reason = 'UNCERTAIN_EFFECTS' if procedure.uncertain else None
                session.event('finished', procedure=procedure.id, status=procedure.status, exit_code=code)
            session._expire()
            session._dispatch()
