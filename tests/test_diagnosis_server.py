from __future__ import annotations

import http.client
import importlib.util
import json
import socket
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SERVE_PATH = ROOT / "demo" / "serve.py"


def load_server_module():
    spec = importlib.util.spec_from_file_location("diagnosis_demo_server", SERVE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecordingDiagnosisService:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.responses = {
            "scenario": (200, b'{"type":"scenario", "source":"core"}\n'),
            "create": (201, b'{"type":"state","status":"created"}\n'),
            "campaign": (200, b'{"type":"state","status":"ok"}\n'),
            "ledger": (200, b'{"type":"ledger","events":[]}\n'),
            "action": (200, b'{"type":"state","event":"action"}\n'),
            "stop": (422, b'{"type":"error","code":"STOP_RULE_NOT_SATISFIED"}\n'),
            "reveal": (409, b'{"type":"error","code":"REVEAL_NOT_AVAILABLE"}\n'),
        }

    def get_scenario(self) -> tuple[int, bytes]:
        self.calls.append(("scenario",))
        return self.responses["scenario"]

    def create_campaign(self, raw_body: bytes) -> tuple[int, bytes]:
        self.calls.append(("create", raw_body))
        if not raw_body:
            return 400, b'{"type":"error","code":"MALFORMED_JSON"}'
        return self.responses["create"]

    def get_campaign(self, campaign_id: str) -> tuple[int, bytes]:
        self.calls.append(("campaign", campaign_id))
        return self.responses["campaign"]

    def act(self, campaign_id: str, raw_body: bytes) -> tuple[int, bytes]:
        self.calls.append(("action", campaign_id, raw_body))
        return self.responses["action"]

    def stop(self, campaign_id: str, raw_body: bytes) -> tuple[int, bytes]:
        self.calls.append(("stop", campaign_id, raw_body))
        return self.responses["stop"]

    def get_ledger(self, campaign_id: str) -> tuple[int, bytes]:
        self.calls.append(("ledger", campaign_id))
        return self.responses["ledger"]

    def reveal(self, campaign_id: str, raw_body: bytes) -> tuple[int, bytes]:
        self.calls.append(("reveal", campaign_id, raw_body))
        return self.responses["reveal"]


@pytest.fixture
def running_server(tmp_path: Path):
    module = load_server_module()
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    module.validate_artifact_root = lambda path: path.resolve()
    service = RecordingDiagnosisService()
    server = module.create_server(artifact_root, port=0, diagnosis_service=service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], service
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request(
    port: int,
    method: str,
    path: str,
    body: bytes | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    headers = {} if body is None else {"Content-Type": "application/json"}
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def assert_private_truth_absent(body: bytes) -> None:
    lowered = body.lower()
    for forbidden in (
        b"world_seed",
        b"noise_seed",
        b"failure_seed",
        b"reveal_nonce",
        b"commitment_payload",
    ):
        assert forbidden not in lowered


def test_scenario_route_relays_core_bytes_and_disables_cache(running_server) -> None:
    port, service = running_server
    status, headers, body = request(port, "GET", "/api/v1/closed-loop/scenario")
    assert status == 200
    assert headers["Cache-Control"] == "no-store"
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert body == service.responses["scenario"][1]
    assert service.calls == [("scenario",)]
    assert_private_truth_absent(body)


def test_campaign_and_ledger_routes_preserve_campaign_identity(running_server) -> None:
    port, service = running_server
    for path, expected_call, response_name in (
        ("/api/v1/closed-loop/campaigns/campaign-17", ("campaign", "campaign-17"), "campaign"),
        (
            "/api/v1/closed-loop/campaigns/campaign-17/ledger",
            ("ledger", "campaign-17"),
            "ledger",
        ),
    ):
        status, headers, body = request(port, "GET", path)
        assert status == 200
        assert headers["Cache-Control"] == "no-store"
        assert body == service.responses[response_name][1]
        assert service.calls[-1] == expected_call


def test_post_routes_pass_exact_raw_bytes_and_relay_status_and_body(running_server) -> None:
    port, service = running_server
    raw = b'{ "request_id" : "same-id", "n":1.000 }\n'
    routes = (
        ("/api/v1/closed-loop/campaigns", "create", None, 201),
        ("/api/v1/closed-loop/campaigns/c-1/actions", "action", "c-1", 200),
        ("/api/v1/closed-loop/campaigns/c-1/stop", "stop", "c-1", 422),
        ("/api/v1/closed-loop/campaigns/c-1/reveal", "reveal", "c-1", 409),
    )
    for path, call_name, campaign_id, expected_status in routes:
        status, headers, body = request(port, "POST", path, raw)
        assert status == expected_status
        assert headers["Cache-Control"] == "no-store"
        assert body == service.responses[call_name][1]
        expected = (call_name, raw) if campaign_id is None else (call_name, campaign_id, raw)
        assert service.calls[-1] == expected


def test_identical_retry_is_not_reserialized_by_adapter(running_server) -> None:
    port, service = running_server
    raw = b'{"request_id":"retry-1", "expected_state_version":0}'
    first = request(port, "POST", "/api/v1/closed-loop/campaigns/c-1/actions", raw)
    second = request(port, "POST", "/api/v1/closed-loop/campaigns/c-1/actions", raw)
    assert (first[0], first[2]) == (second[0], second[2])
    assert first[1]["Cache-Control"] == second[1]["Cache-Control"] == "no-store"
    assert service.calls[-2:] == [("action", "c-1", raw), ("action", "c-1", raw)]


def test_core_owned_404_and_400_are_relayed_with_no_store(running_server) -> None:
    port, service = running_server
    service.responses["campaign"] = (404, b'{"type":"error","code":"NOT_FOUND"}\n')
    service.responses["create"] = (400, b'{"type":"error","code":"MALFORMED_JSON"}\n')

    missing = request(port, "GET", "/api/v1/closed-loop/campaigns/missing")
    malformed = request(port, "POST", "/api/v1/closed-loop/campaigns", b"{")
    assert (missing[0], missing[1]["Cache-Control"], missing[2]) == (
        404,
        "no-store",
        service.responses["campaign"][1],
    )
    assert (malformed[0], malformed[1]["Cache-Control"], malformed[2]) == (
        400,
        "no-store",
        service.responses["create"][1],
    )


def test_preterminal_reveal_response_contains_no_private_truth(running_server) -> None:
    port, service = running_server
    status, headers, body = request(
        port,
        "POST",
        "/api/v1/closed-loop/campaigns/c-1/reveal",
        b'{"request_id":"reveal-early","expected_state_version":0}',
    )
    assert status == 409
    assert headers["Cache-Control"] == "no-store"
    assert body == service.responses["reveal"][1]
    assert_private_truth_absent(body)


def test_unknown_diagnosis_route_is_closed_json_and_no_store(running_server) -> None:
    port, _ = running_server
    status, headers, body = request(port, "GET", "/api/v1/closed-loop/not-a-route")
    assert status == 404
    assert headers["Cache-Control"] == "no-store"
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    payload = json.loads(body)
    assert set(payload) == {
        "schema_version",
        "response_id",
        "response_hash",
        "request_id",
        "idempotency_input_hash",
        "scenario_id",
        "campaign_id",
        "previous_state_version",
        "state_version",
        "previous_ledger_hash",
        "ledger_hash",
        "status",
        "payload",
    }
    assert payload["payload"]["error"]["code"] == "NOT_FOUND"


def test_missing_content_length_reaches_core_as_exact_empty_body(running_server) -> None:
    port, service = running_server
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    connection.putrequest("POST", "/api/v1/closed-loop/campaigns")
    connection.putheader("Content-Type", "application/json")
    connection.endheaders()
    response = connection.getresponse()
    body = response.read()
    connection.close()
    assert response.status == 400
    assert response.getheader("Cache-Control") == "no-store"
    assert body == b'{"type":"error","code":"MALFORMED_JSON"}'
    assert service.calls[-1] == ("create", b"")


def test_truncated_body_returns_closed_transport_envelope(running_server) -> None:
    port, service = running_server
    with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
        client.sendall(
            b"POST /api/v1/closed-loop/campaigns HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\nContent-Type: application/json\r\n"
            b"Content-Length: 10\r\nConnection: close\r\n\r\n{}"
        )
        client.shutdown(socket.SHUT_WR)
        response = http.client.HTTPResponse(client)
        response.begin()
        body = response.read()
        assert response.status == 400
        assert response.getheader("Cache-Control") == "no-store"
    payload = json.loads(body)
    assert payload["payload"]["error"] == {
        "code": "INVALID_REQUEST_ENVELOPE",
        "message": "request body ended before Content-Length bytes were received",
    }
    assert not any(call[0] == "create" and call[-1] == b"{}" for call in service.calls)
