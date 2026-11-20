"""Standard-library HTTP API for simulated RFB V1 campaigns.

This module is intentionally a thin transport adapter.  ``RFBWorkflowService``
owns campaign transitions, durable state, public events, and execution.  The
HTTP layer validates only its closed request schemas and never receives private
oracle, lease, reviewer, or execution material.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlsplit


_MAX_REQUEST_BYTES = 1_048_576
_RFB_PREFIX = "/api/rfb"
_CAMPAIGNS_PATH = f"{_RFB_PREFIX}/campaigns"
_SCENARIO_PATH = f"{_RFB_PREFIX}/scenario"
_POLICY_IDS = frozenset(("fixed_grid", "random", "constrained_bo"))
_DECISIONS = frozenset(("approve", "reject", "approve_with_edit"))
_GENESIS_EVENT_SHA256 = "0" * 64


class RFBWorkflowProtocol(Protocol):
    """The frozen public workflow surface consumed by the HTTP adapter."""

    def create_campaign(self, campaign_id: str, scenario_id: str, policy_id: str) -> Any:
        """Create a campaign and return a result with ``state`` and ``disposition``."""

    def record_decision(
        self,
        campaign_id: str,
        decision_id: str,
        expected_revision: int,
        decision: str,
        reason_code: str | None = None,
        edited_recommendation: Mapping[str, Any] | None = None,
    ) -> Any:
        """Record a human decision without starting execution."""

    def resume(self, campaign_id: str, decision_id: str, expected_revision: int) -> Any:
        """Resume one approved logical execution."""

    def campaign_state(self, campaign_id: str) -> Any:
        """Return the verified public campaign state."""

    def public_events(self, campaign_id: str) -> Sequence[Any]:
        """Return canonical public campaign events."""


@dataclass(frozen=True)
class _APIError(Exception):
    status: HTTPStatus
    code: str
    message: str


class RFBAPIService:
    """Validate HTTP payloads and delegate all campaign behavior to a workflow."""

    def __init__(self, workflow: RFBWorkflowProtocol, public_scenario: Any) -> None:
        self._workflow = workflow
        self._scenario = _public_scenario_dict(public_scenario)
        scenario_id = self._scenario.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise ValueError("public_scenario must include a non-empty scenario_id")
        self._scenario_id = scenario_id

    def scenario(self) -> dict[str, Any]:
        return {"scenario": copy.deepcopy(self._scenario)}

    def create_campaign(self, payload: Any) -> dict[str, Any]:
        request = _exact_object(payload, {"campaign_id", "scenario_id", "policy_id"})
        campaign_id = _required_string(request, "campaign_id")
        scenario_id = _required_string(request, "scenario_id")
        policy_id = request["policy_id"]
        if not isinstance(policy_id, str):
            raise _APIError(HTTPStatus.BAD_REQUEST, "invalid_request", "Request has an invalid shape.")
        if scenario_id != self._scenario_id:
            raise _APIError(HTTPStatus.NOT_FOUND, "scenario_not_found", "Scenario was not found.")
        if policy_id not in _POLICY_IDS:
            raise _APIError(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_policy", "Policy is not supported.")
        try:
            result = self._workflow.create_campaign(campaign_id, scenario_id, policy_id)
        except Exception as exc:  # noqa: BLE001 - boundary maps workflow errors to public errors
            raise _workflow_error(exc, operation="create") from exc
        state, _disposition = _workflow_result(result)
        return self._campaign_envelope(campaign_id, state)

    def campaign(self, campaign_id: str) -> dict[str, Any]:
        try:
            state = self._workflow.campaign_state(campaign_id)
        except Exception as exc:  # noqa: BLE001 - boundary maps workflow errors to public errors
            raise _workflow_error(exc, operation="campaign") from exc
        return self._campaign_envelope(campaign_id, state)

    def events(self, campaign_id: str) -> dict[str, Any]:
        events = self._events(campaign_id)
        return {
            "campaign_id": campaign_id,
            "event_head_sha256": _event_head(events),
            "events": events,
        }

    def record_approval(self, campaign_id: str, payload: Any) -> dict[str, Any]:
        request = _approval_request(payload)
        decision_id = _required_string(request, "decision_id")
        expected_revision = _required_revision(request)
        decision = request["decision"]
        if not isinstance(decision, str):
            raise _APIError(HTTPStatus.BAD_REQUEST, "invalid_request", "Request has an invalid shape.")
        if decision not in _DECISIONS:
            raise _APIError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "invalid_decision",
                "Decision is not supported.",
            )

        reason_code: str | None = None
        edited_recommendation: Mapping[str, Any] | None = None
        if decision == "reject":
            reason_code = _required_string(request, "reason_code", semantic=True)
        elif decision == "approve_with_edit":
            edited_recommendation = request["edited_recommendation"]
            if not isinstance(edited_recommendation, Mapping):
                raise _APIError(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "invalid_recommendation",
                    "Edited recommendation is invalid.",
                )

        try:
            state = self._workflow.record_decision(
                campaign_id,
                decision_id,
                expected_revision,
                decision,
                reason_code=reason_code,
                edited_recommendation=edited_recommendation,
            )
        except Exception as exc:  # noqa: BLE001 - boundary maps workflow errors to public errors
            operation = "recommendation" if decision == "approve_with_edit" else "decision"
            raise _workflow_error(exc, operation=operation) from exc
        return self._campaign_envelope(campaign_id, state)

    def resume(self, campaign_id: str, payload: Any) -> tuple[HTTPStatus, dict[str, Any]]:
        request = _exact_object(payload, {"decision_id", "expected_revision"})
        decision_id = _required_string(request, "decision_id")
        expected_revision = _required_revision(request)
        try:
            result = self._workflow.resume(campaign_id, decision_id, expected_revision)
        except Exception as exc:  # noqa: BLE001 - boundary maps workflow errors to public errors
            raise _workflow_error(exc, operation="resume") from exc
        state, disposition = _workflow_result(result)
        if disposition == "advanced":
            status = HTTPStatus.ACCEPTED
        elif disposition == "already_applied":
            status = HTTPStatus.OK
        else:
            raise _APIError(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "integrity_failure",
                "Campaign state could not be verified.",
            )
        return status, self._campaign_envelope(campaign_id, state)

    def _campaign_envelope(self, campaign_id: str, state: Any) -> dict[str, Any]:
        campaign = _state_dict(state)
        if campaign.get("campaign_id") != campaign_id:
            raise _APIError(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "integrity_failure",
                "Campaign state could not be verified.",
            )
        return {
            "campaign": campaign,
            "event_head_sha256": _event_head(self._events(campaign_id)),
        }

    def _events(self, campaign_id: str) -> list[dict[str, Any]]:
        try:
            raw_events = self._workflow.public_events(campaign_id)
        except Exception as exc:  # noqa: BLE001 - boundary maps workflow errors to public errors
            raise _workflow_error(exc, operation="events") from exc
        return _public_events(raw_events)


class RFBAPIRequestHandler(BaseHTTPRequestHandler):
    """Serve only the closed RFB JSON API routes."""

    api_service: RFBAPIService
    server_version = "RFBAPI"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlsplit(self.path).path
        try:
            if path == _SCENARIO_PATH:
                self._send_json(HTTPStatus.OK, self.api_service.scenario())
                return
            campaign_id = _campaign_path_parameter(path, suffix="")
            if campaign_id is not None:
                self._send_json(HTTPStatus.OK, self.api_service.campaign(campaign_id))
                return
            campaign_id = _campaign_path_parameter(path, suffix="/events")
            if campaign_id is not None:
                self._send_json(HTTPStatus.OK, self.api_service.events(campaign_id))
                return
            self._raise_not_found()
        except _APIError as error:
            self._send_error(error)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlsplit(self.path).path
        try:
            if path == _CAMPAIGNS_PATH:
                payload = self._read_json()
                self._send_json(HTTPStatus.CREATED, self.api_service.create_campaign(payload))
                return
            campaign_id = _campaign_path_parameter(path, suffix="/approvals")
            if campaign_id is not None:
                payload = self._read_json()
                self._send_json(HTTPStatus.OK, self.api_service.record_approval(campaign_id, payload))
                return
            campaign_id = _campaign_path_parameter(path, suffix="/resume")
            if campaign_id is not None:
                payload = self._read_json()
                status, body = self.api_service.resume(campaign_id, payload)
                self._send_json(status, body)
                return
            self._raise_not_found()
        except _APIError as error:
            self._send_error(error)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
        self._send_error(_APIError(HTTPStatus.NOT_FOUND, "not_found", "Route was not found."))

    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib handler API
        self._send_error(_APIError(HTTPStatus.NOT_FOUND, "not_found", "Route was not found."))

    def do_PUT(self) -> None:  # noqa: N802 - stdlib handler API
        self._send_error(_APIError(HTTPStatus.NOT_FOUND, "not_found", "Route was not found."))

    def do_PATCH(self) -> None:  # noqa: N802 - stdlib handler API
        self._send_error(_APIError(HTTPStatus.NOT_FOUND, "not_found", "Route was not found."))

    def do_DELETE(self) -> None:  # noqa: N802 - stdlib handler API
        self._send_error(_APIError(HTTPStatus.NOT_FOUND, "not_found", "Route was not found."))

    def send_error(
        self, _code: int, _message: str | None = None, _explain: str | None = None
    ) -> None:
        """Keep unsupported HTTP methods from falling back to stdlib HTML errors."""

        self._send_error(_APIError(HTTPStatus.NOT_FOUND, "not_found", "Route was not found."))

    def _read_json(self) -> Any:
        header = self.headers.get("Content-Length")
        if header is None:
            raise _APIError(HTTPStatus.BAD_REQUEST, "malformed_json", "Request body must be JSON.")
        try:
            length = int(header, 10)
        except ValueError as exc:
            raise _APIError(HTTPStatus.BAD_REQUEST, "malformed_json", "Request body must be JSON.") from exc
        if length < 0 or length > _MAX_REQUEST_BYTES:
            raise _APIError(HTTPStatus.BAD_REQUEST, "malformed_json", "Request body must be JSON.")
        try:
            text = self.rfile.read(length).decode("utf-8")
            return json.loads(text, object_pairs_hook=_reject_duplicate_json_keys)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise _APIError(HTTPStatus.BAD_REQUEST, "malformed_json", "Request body must be JSON.") from exc

    def _raise_not_found(self) -> None:
        raise _APIError(HTTPStatus.NOT_FOUND, "not_found", "Route was not found.")

    def _send_error(self, error: _APIError) -> None:
        self._send_json(
            error.status,
            {"error": {"code": error.code, "message": error.message, "details": {}}},
        )

    def _send_json(self, status: HTTPStatus, body: Mapping[str, Any]) -> None:
        payload = json.dumps(body, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        """Avoid logging request payloads or paths that might contain sensitive input."""


def create_server(
    workflow_or_service: RFBWorkflowProtocol | RFBAPIService,
    public_scenario: Any | None = None,
    host: str = "127.0.0.1",
    port: int = 0,
) -> HTTPServer:
    """Create an RFB API server, normally bound to an ephemeral local port in tests."""

    if isinstance(workflow_or_service, RFBAPIService):
        if public_scenario is not None:
            raise ValueError("public_scenario is not accepted with an RFBAPIService")
        service = workflow_or_service
    else:
        if public_scenario is None:
            raise ValueError("public_scenario is required with a workflow service")
        service = RFBAPIService(workflow_or_service, public_scenario)
    handler = type("ConfiguredRFBAPIRequestHandler", (RFBAPIRequestHandler,), {"api_service": service})
    return HTTPServer((host, port), handler)


def _public_scenario_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        scenario = copy.deepcopy(dict(value))
    else:
        to_dict = getattr(value, "to_dict", None)
        if not callable(to_dict):
            raise ValueError("public_scenario must be a public RFB scenario or mapping")
        scenario = to_dict()
        if not isinstance(scenario, Mapping):
            raise ValueError("public_scenario.to_dict() must return a mapping")
        scenario = copy.deepcopy(dict(scenario))
    if _contains_private_key(scenario):
        raise ValueError("public_scenario must not contain private material")
    return scenario


def _contains_private_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).lower()
            if normalized in {
                "audit_timestamp",
                "execution_identity_sha256",
                "execution_identity",
                "execution_oracle_spec",
                "lease_generation",
                "lease_token",
                "lease_expires_at",
                "model_parameters",
                "oracle",
                "oracle_config",
                "private",
                "private_config",
                "reviewer_identity",
                "reviewer_id",
                "worker_id",
            }:
                return True
            if _contains_private_key(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_private_key(item) for item in value)
    return False


def _exact_object(value: Any, expected: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise _APIError(HTTPStatus.BAD_REQUEST, "invalid_request", "Request has an invalid shape.")
    return dict(value)


def _approval_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _APIError(HTTPStatus.BAD_REQUEST, "invalid_request", "Request has an invalid shape.")
    request = dict(value)
    decision = request.get("decision")
    expected = {
        "approve": {"decision_id", "expected_revision", "decision"},
        "reject": {"decision_id", "expected_revision", "decision", "reason_code"},
        "approve_with_edit": {
            "decision_id",
            "expected_revision",
            "decision",
            "edited_recommendation",
        },
    }.get(decision)
    if expected is None:
        common = {"decision_id", "expected_revision", "decision"}
        if set(request) != common:
            raise _APIError(HTTPStatus.BAD_REQUEST, "invalid_request", "Request has an invalid shape.")
        return request
    if set(request) != expected:
        raise _APIError(HTTPStatus.BAD_REQUEST, "invalid_request", "Request has an invalid shape.")
    return request


def _required_string(
    value: Mapping[str, Any], name: str, *, semantic: bool = False
) -> str:
    item = value.get(name)
    if not isinstance(item, str):
        raise _APIError(HTTPStatus.BAD_REQUEST, "invalid_request", "Request has an invalid shape.")
    if not item.strip():
        code = "invalid_decision" if semantic else "invalid_request"
        message = "Decision is invalid." if semantic else "Request has an invalid shape."
        raise _APIError(HTTPStatus.UNPROCESSABLE_ENTITY if semantic else HTTPStatus.BAD_REQUEST, code, message)
    return item


def _required_revision(value: Mapping[str, Any]) -> int:
    revision = value.get("expected_revision")
    if isinstance(revision, bool) or not isinstance(revision, int):
        raise _APIError(HTTPStatus.BAD_REQUEST, "invalid_request", "Request has an invalid shape.")
    if revision < 0:
        raise _APIError(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "invalid_decision",
            "Expected revision is invalid.",
        )
    return revision


def _workflow_result(result: Any) -> tuple[Any, str]:
    if isinstance(result, Mapping):
        state = result.get("state")
        disposition = result.get("disposition")
    else:
        state = getattr(result, "state", None)
        disposition = getattr(result, "disposition", None)
    if state is None or disposition is None:
        raise _APIError(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "integrity_failure",
            "Campaign state could not be verified.",
        )
    value = getattr(disposition, "value", disposition)
    if not isinstance(value, str):
        raise _APIError(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "integrity_failure",
            "Campaign state could not be verified.",
        )
    return state, value


def _state_dict(state: Any) -> dict[str, Any]:
    if isinstance(state, Mapping):
        payload = state
    else:
        to_dict = getattr(state, "to_dict", None)
        if not callable(to_dict):
            raise _APIError(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "integrity_failure",
                "Campaign state could not be verified.",
            )
        payload = to_dict()
    if not isinstance(payload, Mapping) or _contains_private_key(payload):
        raise _APIError(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "integrity_failure",
            "Campaign state could not be verified.",
        )
    return copy.deepcopy(dict(payload))


def _public_events(events: Any) -> list[dict[str, Any]]:
    if isinstance(events, (str, bytes)) or not isinstance(events, Sequence):
        raise _APIError(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "integrity_failure",
            "Campaign events could not be verified.",
        )
    serialized: list[dict[str, Any]] = []
    for event in events:
        if isinstance(event, Mapping):
            payload = event
        else:
            to_dict = getattr(event, "to_dict", None)
            if not callable(to_dict):
                raise _APIError(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "integrity_failure",
                    "Campaign events could not be verified.",
                )
            payload = to_dict()
        if not isinstance(payload, Mapping) or _contains_private_key(payload):
            raise _APIError(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "integrity_failure",
                "Campaign events could not be verified.",
            )
        serialized.append(copy.deepcopy(dict(payload)))
    return serialized


def _event_head(events: Sequence[Mapping[str, Any]]) -> str:
    if not events:
        return _GENESIS_EVENT_SHA256
    head = events[-1].get("event_sha256")
    if not isinstance(head, str) or len(head) != 64 or any(char not in "0123456789abcdef" for char in head):
        raise _APIError(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "integrity_failure",
            "Campaign events could not be verified.",
        )
    return head


def _campaign_path_parameter(path: str, *, suffix: str) -> str | None:
    prefix = f"{_CAMPAIGNS_PATH}/"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    remaining = path[len(prefix) :]
    if suffix:
        remaining = remaining[: -len(suffix)]
    if not remaining or "/" in remaining:
        return None
    return remaining


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _workflow_error(exc: Exception, *, operation: str) -> _APIError:
    """Map known workflow failures without exposing exception text or values."""

    name = type(exc).__name__
    if name == "CampaignNotFoundError":
        return _APIError(HTTPStatus.NOT_FOUND, "campaign_not_found", "Campaign was not found.")
    if name == "UnknownRFBScenarioError":
        return _APIError(HTTPStatus.NOT_FOUND, "scenario_not_found", "Scenario was not found.")
    if name == "CampaignAlreadyExistsError":
        return _APIError(HTTPStatus.CONFLICT, "duplicate_campaign", "Campaign already exists.")
    if name == "UnknownRFBPolicyError":
        return _APIError(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_policy", "Policy is not supported.")
    if name in {"RevisionConflictError", "StaleRevisionError"}:
        return _APIError(HTTPStatus.CONFLICT, "revision_conflict", "Campaign revision conflicts.")
    if name == "RFBWorkflowResumeConflictError":
        return _APIError(HTTPStatus.CONFLICT, "revision_conflict", "Campaign revision conflicts.")
    if name in {"DuplicateResumeError", "DuplicateDecisionError"}:
        return _APIError(HTTPStatus.CONFLICT, "duplicate_decision", "Decision was already recorded.")
    if name in {"ExecutionInProgressError", "ExecutionLeaseError"}:
        return _APIError(
            HTTPStatus.CONFLICT,
            "execution_in_progress",
            "Execution is already in progress.",
        )
    if name in {
        "InvalidPhaseError",
        "NoPendingRecommendationError",
        "ApprovalRequiredError",
        "RFBWorkflowExhaustedError",
        "RFBWorkflowPhaseConflictError",
    }:
        return _APIError(HTTPStatus.CONFLICT, "invalid_phase", "Campaign is not ready for this operation.")
    if name in {"HashChainIntegrityError", "IntegrityFailureError", "IntegrityError"}:
        return _APIError(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "integrity_failure",
            "Campaign integrity verification failed.",
        )
    if name in {"ProtocolConsumptionError", "BudgetExceededError"}:
        return _APIError(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "invalid_protocol",
            "Protocol is invalid.",
        )
    if isinstance(exc, (TypeError, ValueError)):
        code = "invalid_recommendation" if operation == "recommendation" else "invalid_decision"
        message = "Recommendation is invalid." if operation == "recommendation" else "Request is invalid."
        if operation == "create":
            code, message = "invalid_policy", "Campaign request is invalid."
        return _APIError(HTTPStatus.UNPROCESSABLE_ENTITY, code, message)
    return _APIError(
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "integrity_failure",
        "Campaign request could not be completed.",
    )


__all__ = ["RFBAPIRequestHandler", "RFBAPIService", "RFBWorkflowProtocol", "create_server"]
