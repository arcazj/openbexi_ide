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
                *panel.command_buttons.values(),
            )
        )
    finally:
        panel.worker.close()
        panel.close()


def test_native_command_uses_delivered_proof_once_even_after_response_loss():
    import threading
    import uuid

    client = object.__new__(SpellServerClient)
    client._lock = threading.RLock()
    client._controllers = {}
    eid = str(uuid.uuid4())
    original = dict(
        id=eid,
        connection_id=str(uuid.uuid4()),
        epoch=1,
        connection_generation=3,
        capability="a" * 64,
    )
    client.remember_controller("A", original)
    sent = []

    def lose_response(method, path, body=None, *, key=None):
        sent.append((method, path, dict(body), key))
        raise SpellServerError(503, "gateway_unavailable")

    client.request = lose_response
    with pytest.raises(SpellServerError):
        client.command("A", eid, "CMD_STEP", key="one-intent")
    assert len(sent) == 1
    assert sent[0][2]["expected_epoch"] == 1
    assert sent[0][2]["connection_generation"] == 3
    assert sent[0][3] == "one-intent"
    assert client._controllers[("A", eid)]["expected_epoch"] == 1
    with pytest.raises(ValueError):
        client.command("A", eid, "CMD_EVAL", key="arbitrary")
    client.forget()
    with pytest.raises(SpellServerError, match="controller_proof_required"):
        client.command("A", eid, "CMD_RUN", key="no-proof")
    assert len(sent) == 1


@pytest.mark.parametrize(
    "state,enabled",
    [
        ("OWNED", {"CMD_RUN", "CMD_STEP", "CMD_PAUSE", "CMD_ABORT", "CMD_CLOSE"}),
        ("HANDOFF_PAUSED", {"CMD_RUN"}),
        ("RECOVERY_REQUIRED", set()),
        ("PAUSING", set()),
    ],
)
def test_panel_commands_require_owner_proof_capability_and_live_state(
    app, state, enabled
):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTreeWidgetItem

    panel = SpellServerPanel()
    panel.client = type("Client", (), {"has_controller": lambda *args: True})()
    try:
        panel.context.blockSignals(True)
        panel.context.addItem("A")
        panel.context.blockSignals(False)
        panel.state = {
            "health": {
                "subject": "alice",
                "permissions": ["execution:control", "execution:start"],
                "native_commands": [
                    "CMD_RUN",
                    "CMD_STEP",
                    "CMD_PAUSE",
                    "CMD_ABORT",
                    "CMD_CLOSE",
                ],
            }
        }
        row = QTreeWidgetItem(["example", "alice", state, ""])
        row.setData(
            0,
            Qt.UserRole,
            dict(
                id="execution-1",
                owner="alice",
                lifecycle="STARTING",
                control_state=state,
            ),
        )
        panel.executions.addTopLevelItem(row)
        panel.executions.setCurrentItem(row)
        panel.update_buttons()
        assert {k for k, b in panel.command_buttons.items() if b.isEnabled()} == enabled
        panel.state["health"]["native_commands"] = []
        panel.update_buttons()
        assert not any(b.isEnabled() for b in panel.command_buttons.values())
        panel.state["health"]["native_commands"] = ["CMD_RUN"]
        panel.state["health"]["subject"] = "bob"
        panel.update_buttons()
        assert not any(b.isEnabled() for b in panel.command_buttons.values())
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


def test_pending_native_reconnect_discards_only_its_original_cached_proof():
    import threading

    client = object.__new__(SpellServerClient)
    client._lock = threading.RLock()
    client._controllers = {
        ("A", "one"): {"capability": "old"},
        ("A", "two"): {"capability": "other"},
    }
    assert not client.remember_controller("A", {"id": "one", "rebind_pending": True})
    assert not client.has_controller("A", "one")
    assert client.has_controller("A", "two")
    with pytest.raises(SpellServerError, match="controller_proof_required"):
        client.command("A", "one", "CMD_RUN", key="pending-must-not-run")


@pytest.mark.parametrize(
    "state,advertised,has_proof,subject,enabled",
    [
        ("CONTROLLER_DISCONNECTED", True, False, "alice", True),
        ("OWNED", True, False, "alice", True),
        ("OWNED", True, True, "alice", False),
        ("CONTROLLER_DISCONNECTED", False, False, "alice", False),
        ("CONTROLLER_DISCONNECTED", True, False, "observer", False),
        ("PAUSING", True, False, "alice", False),
        ("RECOVERY_REQUIRED", True, False, "alice", False),
    ],
)
def test_native_reconnect_button_requires_owner_and_configured_recovery(
    app, state, advertised, has_proof, subject, enabled
):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTreeWidgetItem

    panel = SpellServerPanel()
    panel.client = type("Client", (), {"has_controller": lambda *args: has_proof})()
    try:
        panel.context.blockSignals(True)
        panel.context.addItem("A")
        panel.context.blockSignals(False)
        panel.state = {
            "health": {
                "subject": subject,
                "permissions": ["execution:control", "execution:start"],
                "native_rebind": advertised,
            }
        }
        row = QTreeWidgetItem(["example", "alice", state, ""])
        row.setData(
            0,
            Qt.UserRole,
            dict(id="one", owner="alice", lifecycle="STARTING", control_state=state),
        )
        panel.executions.addTopLevelItem(row)
        panel.executions.setCurrentItem(row)
        panel.update_buttons()
        assert panel.rebind_button.isEnabled() is enabled
        assert not any(b.isEnabled() for b in panel.command_buttons.values())
    finally:
        panel.worker.close()
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


def test_server_connection_cannot_fall_back_to_local_run_or_debug(app, tmp_path):
    from PySide6.QtCore import QSettings
    from openbexi_ide.app import MainWindow

    project = tmp_path / "project"
    project.mkdir()
    script = project / "main.py"
    script.write_text("raise RuntimeError('must not run locally from server mode')\n")
    window = MainWindow(
        project, QSettings(str(tmp_path / "test.ini"), QSettings.IniFormat)
    )
    errors = []
    window.report_error = errors.append
    try:
        window.open_file(script)
        window.spell_server_panel.client = type(
            "Client", (), {"forget": lambda self: None}
        )()
        window.refresh_busy()
        assert not window.run_action.isEnabled() and not window.debug_action.isEnabled()
        window.run_script()
        window.debug_script()
        assert len(errors) == 2 and all("Server" in error for error in errors)
        assert not window.run_controller.running and not window.debug_controller.running
        window.spell_server_panel.client = None
    finally:
        window.close()


def test_read_only_monitoring_uses_exact_pinned_gateway_request():
    import uuid

    client = object.__new__(SpellServerClient)
    log = []
    instance = str(uuid.uuid4())

    def fake(method, path, body=None, *, key=None):
        log.append((method, path, body, key))
        return {
            "schema": "openbexi.listener/1",
            "result": {
                "context_id": "A",
                "after_sequence": 0,
                "next_sequence": 3,
                "latest_sequence": 3,
                "has_more": False,
                "runtime_enabled": False,
                "events": [
                    {
                        "sequence": 2,
                        "type": "CONTROL_OWNER_CHANGED",
                        "execution_id": instance,
                    },
                ],
            },
        }

    client.request = fake
    response = client.events("A")
    assert response["events"][0]["execution_id"] == instance
    assert log == [
        ("POST", "/v1/contexts/A/events", {"after_sequence": 0, "limit": 32}, None)
    ]
    assert not client.__dict__.get("_controllers")


@pytest.mark.parametrize(
    "after,limit",
    [
        (-1, 1),
        (True, 1),
        (2**63, 1),
        (1.5, 1),
        (0, 0),
        (0, 33),
        (0, True),
    ],
)
def test_invalid_monitoring_cursor_never_sends_any_request(after, limit):
    client = object.__new__(SpellServerClient)
    client.request = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("Network request must not occur")
    )
    with pytest.raises(ValueError):
        client.events("A", after_sequence=after, limit=limit)


@pytest.mark.parametrize(
    "changed",
    [
        {"runtime_enabled": True},
        {"has_more": True},
        {"context_id": "B"},
        {"after_sequence": 1},
        {"next_sequence": -1},
        {
            "events": [
                {"sequence": 3, "type": "CONTROL_OWNER_CHANGED", "token": "SECRET"}
            ]
        },
        {"events": [{"sequence": 1, "type": "NATIVE_DRIVER_EVENT"}]},
        {"events": [{"sequence": True, "type": "EXECUTION_RESERVED"}]},
        {"events": [{"sequence": 0, "type": "EXECUTION_RESERVED"}]},
        {"events": [{"sequence": 4, "type": "EXECUTION_RESERVED"}]},
    ],
)
def test_monitoring_rejects_bogus_or_secret_bearing_gateway_result(changed):
    client = object.__new__(SpellServerClient)
    expected = {
        "context_id": "A",
        "after_sequence": 0,
        "next_sequence": 3,
        "latest_sequence": 3,
        "has_more": False,
        "runtime_enabled": False,
        "events": [{"sequence": 2, "type": "CONTROL_OWNER_CHANGED"}],
    }
    client.request = lambda *a, **k: {
        "schema": "openbexi.listener/1",
        "result": dict(expected, **changed),
    }
    with pytest.raises(SpellServerError):
        client.events("A")
