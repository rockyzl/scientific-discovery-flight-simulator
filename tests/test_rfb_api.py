from __future__ import annotations

import json
import threading
from pathlib import Path
from queue import Queue
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from discovery_flight_simulator.rfb.api import create_server
from discovery_flight_simulator.rfb.scenario import load_rfb_scenario
from discovery_flight_simulator.rfb.store import SQLiteRFBCampaignStore
from discovery_flight_simulator.rfb.workflow import RFBWorkflowService


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "rfbzero_cell_v0.json"


@pytest.fixture
def loaded_scenario():
    return load_rfb_scenario(
        SCENARIO_PATH,
        private_commitment_key=b"rfb-api-test-commitment-key",
    )


@pytest.fixture
def public_scenario(loaded_scenario) -> dict[str, Any]:
    return loaded_scenario.public_projection().to_dict()


@pytest.fixture
def running_server(tmp_path: Path, loaded_scenario, public_scenario: dict[str, Any]):
    ready: Queue[Any] = Queue()

    def serve() -> None:
        store = SQLiteRFBCampaignStore(tmp_path / "campaign.sqlite")
        service = RFBWorkflowService(
            store,
            {loaded_scenario.public_projection().scenario_id: loaded_scenario},
            tmp_path / "workflow-checkpoints.sqlite",
        )
        try:
            server = create_server(service, public_scenario, port=0)
            ready.put(server)
            server.serve_forever()
        except Exception as exc:  # noqa: BLE001 - report server setup failures to the fixture thread
            ready.put(exc)
        finally:
            service.close()
            store.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    server = ready.get(timeout=5)
    if isinstance(server, Exception):
        thread.join(timeout=2)
        raise server
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def request(url: str, *, method: str = "GET", body: bytes | None = None) -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json"} if body is not None else {}
    http_request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(http_request, timeout=2) as response:  # noqa: S310 - local server only
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def post(url: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    return request(url, method="POST", body=json.dumps(body).encode("utf-8"))


def assert_error(response: dict[str, Any], code: str) -> None:
    assert set(response) == {"error"}
    assert response["error"] == {
        "code": code,
        "message": response["error"]["message"],
        "details": {},
    }
    assert isinstance(response["error"]["message"], str)


def test_scenario_returns_only_the_public_projection(
    running_server: str, public_scenario: dict[str, Any]
) -> None:
    status, response = request(f"{running_server}/api/rfb/scenario")

    assert status == 200
    assert response == {"scenario": public_scenario}
    serialized = json.dumps(response, sort_keys=True)
    assert "model_parameters" not in serialized
    assert "execution_identity" not in serialized
    assert "lease_token" not in serialized


def test_create_review_approval_and_resume_are_separate_operations(
    running_server: str,
) -> None:
    status, created = post(
        f"{running_server}/api/rfb/campaigns",
        {
            "campaign_id": "campaign-1",
            "scenario_id": "rfbzero_cell_v0",
            "policy_id": "fixed_grid",
        },
    )
    assert status == 201
    assert created["campaign"]["phase"] == "awaiting_review"

    status, approved = post(
        f"{running_server}/api/rfb/campaigns/campaign-1/approvals",
        {"decision_id": "decision-1", "expected_revision": 1, "decision": "approve"},
    )
    assert status == 200
    assert approved["campaign"]["phase"] == "approved"
    assert approved["campaign"]["executions"] == []
    assert approved["campaign"]["cumulative_costs"] == {"attempts": 0, "measurements": 0}
    assert approved["campaign"]["reserved_costs"] == {"attempts": 0, "measurements": 0}

    status, resumed = post(
        f"{running_server}/api/rfb/campaigns/campaign-1/resume",
        {"decision_id": "decision-1", "expected_revision": 2},
    )
    assert status == 202
    assert resumed["campaign"]["phase"] == "awaiting_review"
    assert len(resumed["campaign"]["executions"]) == 1
    assert resumed["campaign"]["cumulative_costs"] == {"attempts": 1, "measurements": 1}

    status, repeated = post(
        f"{running_server}/api/rfb/campaigns/campaign-1/resume",
        {"decision_id": "decision-1", "expected_revision": 2},
    )
    assert status == 200
    assert repeated == resumed


def test_completed_resume_requires_the_durable_approval_revision(running_server: str) -> None:
    status, _ = post(
        f"{running_server}/api/rfb/campaigns",
        {
            "campaign_id": "campaign-completed-revision",
            "scenario_id": "rfbzero_cell_v0",
            "policy_id": "fixed_grid",
        },
    )
    assert status == 201

    status, approved = post(
        f"{running_server}/api/rfb/campaigns/campaign-completed-revision/approvals",
        {"decision_id": "decision-completed-1", "expected_revision": 1, "decision": "approve"},
    )
    assert status == 200

    status, completed = post(
        f"{running_server}/api/rfb/campaigns/campaign-completed-revision/resume",
        {"decision_id": "decision-completed-1", "expected_revision": approved["campaign"]["revision"]},
    )
    assert status == 202

    status, conflict = post(
        f"{running_server}/api/rfb/campaigns/campaign-completed-revision/resume",
        {"decision_id": "decision-completed-1", "expected_revision": completed["campaign"]["revision"]},
    )
    assert status == 409
    assert_error(conflict, "revision_conflict")

    status, repeated = post(
        f"{running_server}/api/rfb/campaigns/campaign-completed-revision/resume",
        {"decision_id": "decision-completed-1", "expected_revision": approved["campaign"]["revision"]},
    )
    assert status == 200
    assert repeated == completed


def test_request_validation_and_safe_errors(running_server: str) -> None:
    status, response = request(
        f"{running_server}/api/rfb/campaigns",
        method="POST",
        body=b'{"campaign_id":"secret-sentinel",',
    )
    assert status == 400
    assert_error(response, "malformed_json")
    assert "secret-sentinel" not in json.dumps(response)

    status, response = post(
        f"{running_server}/api/rfb/campaigns",
        {
            "campaign_id": "campaign-1",
            "scenario_id": "rfbzero_cell_v0",
            "policy_id": "fixed_grid",
            "private": "secret-sentinel",
        },
    )
    assert status == 400
    assert_error(response, "invalid_request")
    assert "secret-sentinel" not in json.dumps(response)

    status, response = post(
        f"{running_server}/api/rfb/campaigns",
        {
            "campaign_id": "campaign-1",
            "scenario_id": "rfbzero_cell_v0",
            "policy_id": "unknown-policy",
        },
    )
    assert status == 422
    assert_error(response, "invalid_policy")

    status, response = request(f"{running_server}/api/rfb/campaigns/missing")
    assert status == 404
    assert_error(response, "campaign_not_found")


def test_events_route_returns_only_workflow_public_events(
    running_server: str,
) -> None:
    post(
        f"{running_server}/api/rfb/campaigns",
        {
            "campaign_id": "campaign-events",
            "scenario_id": "rfbzero_cell_v0",
            "policy_id": "random",
        },
    )

    status, response = request(f"{running_server}/api/rfb/campaigns/campaign-events/events")
    assert status == 200
    assert response["campaign_id"] == "campaign-events"
    assert response["event_head_sha256"] == response["events"][-1]["event_sha256"]
    assert [event["event_type"] for event in response["events"]] == [
        "campaign_created",
        "recommendation_saved",
    ]
    assert response["events"][0]["previous_event_sha256"] == "0" * 64
    assert response["events"][1]["previous_event_sha256"] == response["events"][0]["event_sha256"]
    assert all(set(event) == {
        "schema_version",
        "sequence",
        "event_type",
        "payload",
        "previous_event_sha256",
        "event_sha256",
    } for event in response["events"])
    serialized = json.dumps(response, sort_keys=True)
    assert "model_parameters" not in serialized
    assert "execution_identity" not in serialized
    assert "lease_token" not in serialized
