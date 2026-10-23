"""v0.8 client parser and desktop isolation; real TLS chain lives in plugin CI."""

import time

import pytest

from openbexi_runtime.spell_server_client import (
    SpellServerClient,
    SpellServerError,
    decode,
)
from openbexi_ide.spell_server_panel import SpellServerPanel


@pytest.mark.parametrize(
    "raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b"[" * 20 + b"0" + b"]" * 20, b"x" * 65537]
)
def test_client_rejects_ambiguous_or_unbounded_response(raw):
    with pytest.raises(SpellServerError):
        decode(raw)


@pytest.mark.parametrize(
    "url",
    ["http://localhost", "https://a/b", "https://u:p@a", "https://a?x", "https://a/#x"],
)
def test_client_rejects_unconfigured_origin_before_loading_keys(url):
    with pytest.raises(ValueError):
        SpellServerClient(
            url=url,
            fingerprint="a" * 64,
            ca="missing",
            certificate="missing",
            key="missing",
        )


def test_panel_worker_does_not_block_gui_and_drops_completion_after_close(app):
    panel = SpellServerPanel()
    try:
        panel.submit(lambda: (time.sleep(0.1), {"error": "unused"})[1])
        assert panel.busy and not panel.refresh_button.isEnabled()
        # Widget updates remain possible while network work is pending.
        panel.status.setText("responsive")
        assert panel.status.text() == "responsive"
        panel.close_connection()
        time.sleep(0.15)
        app.processEvents()
        assert panel.status.text() == "responsive"
    finally:
        panel.close()


def test_observer_panel_disables_every_mutation(app):
    panel = SpellServerPanel()
    try:
        panel.client = object()
        panel.state = {
            "health": {
                "subject": "observer",
                "permissions": ["context:read", "execution:read"],
            }
        }
        # No selected row: no controller proof can be guessed from read metadata.
        panel.client = type("ReadOnly", (), {"has_controller": lambda *args: False})()
        panel.update_buttons()
        assert panel.refresh_button.isEnabled()
        assert not any(
            button.isEnabled()
            for button in (
                panel.reserve_button,
                panel.rebind_button,
                panel.claim_button,
                panel.accept_button,
                panel.reject_button,
            )
        )
    finally:
        panel.worker.close()
        panel.close()


def test_window_detach_does_not_wait_for_pending_network_lock(app):
    import threading

    entered, release, forgotten = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    panel = SpellServerPanel()

    class Client:
        def has_controller(self, *args):
            return False

        def forget(self):
            forgotten.set()

    panel.client = Client()

    def pending():
        entered.set()
        assert release.wait(2)
        return {}

    try:
        panel.submit(pending)
        assert entered.wait(1)
        start = time.monotonic()
        panel.close_connection()
        assert time.monotonic() - start < 0.1
        assert not forgotten.is_set()
        release.set()
        assert forgotten.wait(1)
    finally:
        release.set()
        panel.close()


def test_busy_panel_never_waits_on_controller_network_lock(app):
    panel = SpellServerPanel()

    class PendingClient:
        def has_controller(self, *args):
            raise AssertionError(
                "GUI must not query a client lock while network work is pending"
            )

    panel.client = PendingClient()
    panel.busy = True
    try:
        panel.update_buttons()
        assert not panel.refresh_button.isEnabled()
    finally:
        panel.worker.close()
        panel.close()
