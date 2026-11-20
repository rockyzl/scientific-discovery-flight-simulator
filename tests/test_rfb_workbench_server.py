from __future__ import annotations

import importlib.util
import json
import os
import threading
from pathlib import Path
from queue import Queue
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "rfbzero_cell_v0.json"
_WORKBENCH_PATH = Path(__file__).resolve().parents[1] / "demo" / "rfb_workbench.py"
_WORKBENCH_SPEC = importlib.util.spec_from_file_location("rfb_workbench", _WORKBENCH_PATH)
assert _WORKBENCH_SPEC is not None and _WORKBENCH_SPEC.loader is not None
rfb_workbench = importlib.util.module_from_spec(_WORKBENCH_SPEC)
_WORKBENCH_SPEC.loader.exec_module(rfb_workbench)


def _request(
    base_url: str, path: str, *, method: str = "GET", payload: dict[str, Any] | None = None
) -> tuple[int, dict[str, str], bytes]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{base_url}{path}",
        data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method=method,
    )
    try:
        with urlopen(request, timeout=5) as response:  # noqa: S310 - local ephemeral server only
            return response.status, dict(response.headers.items()), response.read()
    except HTTPError as error:
        return error.code, dict(error.headers.items()), error.read()


def _start_server(
    scenario_path: Path, data_dir: Path
) -> tuple[rfb_workbench.RFBWorkbenchHTTPServer, threading.Thread]:
    ready: Queue[rfb_workbench.RFBWorkbenchHTTPServer | BaseException] = Queue()

    def serve() -> None:
        try:
            server = rfb_workbench.create_server(scenario_path, data_dir, port=0)
        except BaseException as exc:
            ready.put(exc)
            return
        ready.put(server)
        try:
            server.serve_forever()
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    server = ready.get(timeout=5)
    if isinstance(server, BaseException):
        thread.join(timeout=5)
        raise server
    return server, thread


def _stop_server(server: rfb_workbench.RFBWorkbenchHTTPServer, thread: threading.Thread) -> None:
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture
def workbench(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<main>simulated RFB workbench</main>", encoding="utf-8")
    (ui_dir / "styles.css").write_text("main { color: #123456; }", encoding="utf-8")
    (ui_dir / "app.js").write_text("window.rfbWorkbench = true;", encoding="utf-8")
    monkeypatch.setattr(rfb_workbench, "STATIC_ROOT", ui_dir)

    state_dir = tmp_path / "state"
    server, thread = _start_server(SCENARIO_PATH, state_dir)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield base_url, state_dir, ui_dir, server, thread
    finally:
        if thread.is_alive():
            _stop_server(server, thread)


@pytest.fixture
def real_workbench(tmp_path: Path):
    state_dir = tmp_path / "state"
    server, thread = _start_server(SCENARIO_PATH, state_dir)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield base_url, state_dir, server, thread
    finally:
        if thread.is_alive():
            _stop_server(server, thread)


def test_static_bundle_and_unified_campaign_api(real_workbench) -> None:
    base_url, _state_dir, _server, _thread = real_workbench

    for path, expected_type, expected_body in (
        ("/", "text/html", b"Virtual RFB Cell Campaign"),
        ("/rfb-workbench.css", "text/css", b"--ink"),
        ("/rfb-workbench.js", "application/javascript", b"deriveContinuation"),
    ):
        status, headers, body = _request(base_url, path)
        assert status == 200
        assert headers["Content-Type"].startswith(expected_type)
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert expected_body in body

    status, _headers, body = _request(base_url, "/")
    assert status == 200
    assert b'<main id="workbench"' in body

    status, _headers, body = _request(
        base_url,
        "/api/rfb/campaigns",
        method="POST",
        payload={
            "campaign_id": "workbench-campaign",
            "scenario_id": "rfbzero_cell_v0",
            "policy_id": "fixed_grid",
        },
    )
    assert status == 201
    created = json.loads(body)
    assert created["campaign"]["phase"] == "awaiting_review"

    status, _headers, body = _request(base_url, "/api/rfb/campaigns/workbench-campaign")
    assert status == 200
    assert json.loads(body) == created


def test_restart_resumes_persisted_public_approval_once(real_workbench) -> None:
    base_url, state_dir, server, thread = real_workbench
    status, _headers, body = _request(
        base_url,
        "/api/rfb/campaigns",
        method="POST",
        payload={
            "campaign_id": "persisted-approval",
            "scenario_id": "rfbzero_cell_v0",
            "policy_id": "fixed_grid",
        },
    )
    assert status == 201
    created = json.loads(body)["campaign"]

    status, _headers, body = _request(
        base_url,
        "/api/rfb/campaigns/persisted-approval/approvals",
        method="POST",
        payload={"decision_id": "persisted-approval-1", "expected_revision": created["revision"], "decision": "approve"},
    )
    assert status == 200
    approved = json.loads(body)["campaign"]
    assert approved["phase"] == "approved"
    assert approved["executions"] == []
    assert approved["cumulative_costs"] == {"attempts": 0, "measurements": 0}

    _stop_server(server, thread)
    restarted, restarted_thread = _start_server(SCENARIO_PATH, state_dir)
    restarted_url = f"http://127.0.0.1:{restarted.server_address[1]}"
    try:
        status, _headers, body = _request(restarted_url, "/api/rfb/campaigns/persisted-approval")
        assert status == 200
        persisted = json.loads(body)["campaign"]
        assert persisted["phase"] == "approved"
        assert persisted["approved_decision"] is not None

        status, _headers, body = _request(
            restarted_url,
            "/api/rfb/campaigns/persisted-approval/resume",
            method="POST",
            payload={
                "decision_id": persisted["approved_decision"]["decision_id"],
                "expected_revision": persisted["revision"],
            },
        )
        assert status == 202
        resumed = json.loads(body)["campaign"]
        assert len(resumed["executions"]) == 1
        assert resumed["cumulative_costs"] == {"attempts": 1, "measurements": 1}
    finally:
        _stop_server(restarted, restarted_thread)


def test_static_paths_cannot_traverse_or_escape_symlinks(workbench) -> None:
    base_url, _state_dir, ui_dir, _server, _thread = workbench

    for path in ("/missing", "/../pyproject.toml", "/%2e%2e/pyproject.toml"):
        status, _headers, body = _request(base_url, path)
        assert status == 404
        assert b"[project]" not in body

    outside = ui_dir.parent / "outside.css"
    outside.write_text("private static escape", encoding="utf-8")
    (ui_dir / "styles.css").unlink()
    os.symlink(outside, ui_dir / "styles.css")
    status, _headers, body = _request(base_url, "/rfb-workbench.css")
    assert status == 404
    assert b"private static escape" not in body


def test_restart_preserves_campaign_and_hides_private_server_material(workbench) -> None:
    base_url, state_dir, _ui_dir, server, thread = workbench
    status, _headers, body = _request(
        base_url,
        "/api/rfb/campaigns",
        method="POST",
        payload={
            "campaign_id": "restart-campaign",
            "scenario_id": "rfbzero_cell_v0",
            "policy_id": "random",
        },
    )
    assert status == 201
    created = json.loads(body)

    key_path = state_dir / rfb_workbench._COMMITMENT_KEY_FILENAME
    key = key_path.read_bytes()
    assert key
    if os.name == "posix":
        assert key_path.stat().st_mode & 0o777 == 0o600

    _stop_server(server, thread)
    restarted, restarted_thread = _start_server(SCENARIO_PATH, state_dir)
    restarted_url = f"http://127.0.0.1:{restarted.server_address[1]}"
    try:
        status, _headers, body = _request(restarted_url, "/api/rfb/campaigns/restart-campaign")
        assert status == 200
        assert json.loads(body) == created

        status, _headers, body = _request(restarted_url, "/api/rfb/scenario")
        assert status == 200
        serialized = json.dumps(json.loads(body), sort_keys=True)
    finally:
        _stop_server(restarted, restarted_thread)

    for private_value in (
        key.hex(),
        str(key_path),
        str(state_dir),
        "model_parameters",
        "execution_identity",
        "lease_token",
        "private",
    ):
        assert private_value not in serialized
