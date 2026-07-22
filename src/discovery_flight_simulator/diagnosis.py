"""Restricted-v1 closed-loop CV diagnosis service.

The service owns the synthetic world, inference, recommendation, ledger, idempotency, and truth
boundary.  Its public methods deliberately accept/return bytes so an HTTP adapter cannot alter the
bytes used for request identity or response verification.
"""

from __future__ import annotations

import base64
import hashlib
import itertools
import json
import math
import os
import random
import threading
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0.0"
SCENARIO_ID = "cv_diagnosis_v1"
SCENARIO_VERSION = "1.0.0"
PLANNER_ID = "expected_information_gain_v1"
PLANNER_VERSION = "1.0.0"
BELIEF_METHOD = "gaussian_log_bayes_v1"
HYPOTHESES = (
    "slow_kinetics",
    "uncompensated_resistance",
    "reference_drift",
    "electrode_fouling",
    "concentration_preparation_error",
)
HYPOTHESIS_LABELS = (
    "Slow electron-transfer kinetics",
    "Uncompensated resistance",
    "Reference-electrode drift",
    "Electrode fouling",
    "Concentration or preparation error",
)
PRIOR = [0.2] * 5
REASON_TEXT = (
    "This eligible experiment has the highest expected information gain under the public "
    "five-hypothesis model."
)
STOP_COPY = {
    "budget_exhausted": "Stopped · attempt or measurement budget exhausted.",
    "confident_diagnosis": "Stopped · confident diagnosis gate satisfied.",
    "low_expected_information": "Stopped · expected information is below the threshold.",
}
REJECTION_MESSAGES = {
    "INVALID_RECOMMENDATION": "Recommendation identity does not match the current campaign state.",
    "INVALID_OPERATION": "Operation is not allowed by this scenario.",
    "INVALID_CONTROLS": "Controls do not match the operation contract.",
    "INELIGIBLE_ACTION": "The requested experiment is not currently eligible.",
    "STOP_RULE_NOT_SATISFIED": "No stop rule is satisfied.",
}
Z_VALUES = (-2.0, -1.0, 0.0, 1.0, 2.0)
_RAW_WEIGHTS = (0.0544886845, 0.2442013420, 0.4026199469, 0.2442013420, 0.0544886845)
Z_WEIGHTS = tuple(value / sum(_RAW_WEIGHTS) for value in _RAW_WEIGHTS)
GENESIS_ZERO = "0" * 64

ACTION_SPECS: tuple[tuple[str, dict[str, float], str], ...] = (
    *(("repeat_cv", {"scan_rate_mv_s": float(rate)}, f"Repeat CV at {rate} mV/s") for rate in (5, 10, 25, 50, 100, 200)),
    ("measure_ru", {}, "Measure independent Ru"),
    ("check_reference", {}, "Check reference electrode"),
    ("run_blank", {}, "Run a blank"),
    ("dilute_and_repeat", {"dilution_factor": 0.5, "scan_rate_mv_s": 25.0}, "Dilute and repeat"),
    ("clean_and_repeat", {"scan_rate_mv_s": 25.0}, "Clean electrode and repeat"),
    ("run_control_sample", {"scan_rate_mv_s": 25.0}, "Run control sample"),
)
OPERATIONS = tuple(dict.fromkeys(operation for operation, _, _ in ACTION_SPECS))


def _number(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("non-finite JSON number")
    if value == 0:
        return "0"
    raw = repr(value).lower()
    decimal = Decimal(raw)
    adjusted = decimal.adjusted()
    if -6 <= adjusted < 21:
        text = format(decimal, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    mantissa, exponent = format(decimal.normalize(), "e").split("e")
    mantissa = mantissa.rstrip("0").rstrip(".")
    exponent_value = int(exponent)
    sign = "+" if exponent_value >= 0 else "-"
    return f"{mantissa}e{sign}{abs(exponent_value)}"


def _jcs_text(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _number(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_jcs_text(item) for item in value) + "]"
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return "{" + ",".join(
            f"{_jcs_text(key)}:{_jcs_text(value[key])}" for key in sorted(value)
        ) + "}"
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def _jcs(value: Any) -> bytes:
    return _jcs_text(value).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_jcs(value)).hexdigest()


def transport_error_envelope(code: str, message: str) -> bytes:
    """Build the only adapter-owned error shape when no request bytes can reach the service."""

    payload = {
        "type": "error",
        "error": {"code": code, "message": message},
        "state": None,
        "event": None,
    }
    identity = {
        "status": "error",
        "request_id": None,
        "idempotency_input_hash": None,
        "campaign_id": None,
        "state_version": None,
        "payload": payload,
    }
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "response_id": "response-" + _sha(identity)[:24],
        "response_hash": "",
        "request_id": None,
        "idempotency_input_hash": None,
        "scenario_id": None,
        "campaign_id": None,
        "previous_state_version": None,
        "state_version": None,
        "previous_ledger_hash": None,
        "ledger_hash": None,
        "status": "error",
        "payload": payload,
    }
    envelope["response_hash"] = _sha(
        {key: value for key, value in envelope.items() if key != "response_hash"}
    )
    return _jcs(envelope)


def _curve(epa: float, epc: float, ipa: float, ipc: float) -> dict[str, Any]:
    forward = [0.650 + 0.005 * index for index in range(61)]
    reverse = [0.950 - 0.005 * index for index in range(61)]
    potentials = forward + reverse
    currents = [ipa * math.exp(-0.5 * ((potential - epa) / 0.025) ** 2) for potential in forward]
    currents += [ipc * math.exp(-0.5 * ((potential - epc) / 0.025) ** 2) for potential in reverse]
    unsigned = {
        "point_count": 122,
        "potential_reference": "synthetic_SHE",
        "potential_unit": "V",
        "current_unit": "A",
        "potential_v": potentials,
        "current_a": currents,
        "sweep_direction": ["forward"] * 61 + ["reverse"] * 61,
    }
    return {**unsigned, "curve_hash": _sha(unsigned)}


def _extract_peak(curve: dict[str, Any]) -> dict[str, float]:
    currents = curve["current_a"]
    potentials = curve["potential_v"]
    pa = max(range(61), key=lambda index: currents[index])
    pc = min(range(61, 122), key=lambda index: currents[index])
    epa, epc = potentials[pa], potentials[pc]
    ipa, ipc = currents[pa], currents[pc]
    return {
        "Epa_v": epa,
        "Epc_v": epc,
        "ipa_a": ipa,
        "ipc_a": ipc,
        "midpoint_v": (epa + epc) / 2.0,
        "delta_Ep_v": epa - epc,
        "ipa_abs_over_ipc_abs": abs(ipa) / abs(ipc),
    }


def _fixture(epa: float, epc: float, ipa: float, ipc: float) -> dict[str, Any]:
    curve = _curve(epa, epc, ipa, ipc)
    return {
        "provenance": "simulated",
        "likelihood_role": "excluded",
        "peak": _extract_peak(curve),
        "curve": curve,
    }


def _means(operation: str, controls: dict[str, float]) -> tuple[list[list[float]], list[float], list[str]]:
    if operation == "repeat_cv":
        x = math.sqrt(controls["scan_rate_mv_s"] / 25.0)
        current = 14.79847620154866e-6 * x
        return (
            [
                [0.800, 0.060 + 0.035 * x, current],
                [0.800, 0.060 + 0.024 * x, current],
                [0.835, 0.086, current],
                [0.800, 0.080 + 0.010 * x, 0.60 * current],
                [0.800, 0.085 + 0.004 * x, 0.55 * current],
            ],
            [0.004, 0.004, 1e-6],
            ["midpoint_v", "delta_Ep_v", "abs_ipa_a"],
        )
    table = {
        "measure_ru": ([12, 45, 12, 18, 12], 10.0, "ru_ohm"),
        "check_reference": ([0, 0, 0.035, 0.005, 0], 0.008, "reference_offset_v"),
        "run_blank": ([0.5e-6, 0.5e-6, 0.5e-6, 8e-6, 3e-6], 1e-6, "blank_current_a"),
        "dilute_and_repeat": ([1, 1, 1, 1, 1.45], 0.12, "recovery_ratio"),
        "clean_and_repeat": ([1, 1, 1, 1.55, 1], 0.12, "recovery_ratio"),
        "run_control_sample": ([0.060, 0.084, 0.085, 0.082, 0.060], 0.006, "control_delta_Ep_v"),
    }
    values, standard_error, feature = table[operation]
    return [[float(value)] for value in values], [standard_error], [feature]


def _posterior(prior: list[float], values: list[float], means: list[list[float]], se: list[float]) -> list[float]:
    logs: list[float] = []
    for probability, hypothesis_means in zip(prior, means, strict=True):
        likelihood = math.log(probability)
        for value, mean, sigma in zip(values, hypothesis_means, se, strict=True):
            likelihood += -0.5 * ((value - mean) / sigma) ** 2 - math.log(sigma * math.sqrt(2 * math.pi))
        logs.append(likelihood)
    maximum = max(logs)
    weights = [math.exp(value - maximum) for value in logs]
    total = sum(weights)
    result = [value / total for value in weights]
    if not all(math.isfinite(value) and 0 <= value <= 1 for value in result):
        raise RuntimeError("posterior is not finite")
    result[-1] += 1.0 - sum(result)
    if abs(sum(result) - 1.0) > 1e-12:
        raise RuntimeError("posterior is not normalized")
    return result


def _entropy(probabilities: list[float]) -> float:
    return -sum(value * math.log(value) for value in probabilities if value > 0)


def _eig(beliefs: list[float], operation: str, controls: dict[str, float]) -> float:
    means, standard_errors, _ = _means(operation, controls)
    expected_entropy = 0.0
    points = itertools.product(range(5), repeat=len(standard_errors))
    quadrature = list(points)
    for hypothesis_index, probability in enumerate(beliefs):
        for indices in quadrature:
            weight = probability
            values: list[float] = []
            for dimension, z_index in enumerate(indices):
                weight *= Z_WEIGHTS[z_index]
                values.append(
                    means[hypothesis_index][dimension]
                    + Z_VALUES[z_index] * standard_errors[dimension]
                )
            expected_entropy += weight * _entropy(
                _posterior(beliefs, values, means, standard_errors)
            )
    return max(0.0, _entropy(beliefs) - expected_entropy)


def _action_key(operation: str, controls: dict[str, float]) -> str:
    return _jcs_text({"operation": operation, "controls": controls})


def _validate_controls(operation: str, controls: Any) -> dict[str, float] | None:
    if not isinstance(controls, dict) or any(not isinstance(key, str) for key in controls):
        return None
    for candidate_operation, candidate_controls, _ in ACTION_SPECS:
        if operation == candidate_operation and controls == candidate_controls:
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in controls.values()):
                return None
            return deepcopy(candidate_controls)
    return None


class DiagnosisService:
    """Thread-safe persisted service for one frozen synthetic scenario."""

    def __init__(self, state_dir: Path):
        self._state_dir = Path(state_dir).expanduser().resolve()
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = self._state_dir / "diagnosis-private-state.json"
        self._lock = threading.RLock()
        self._data = self._load_or_initialize()
        self._scenario = self._build_scenario()

    def _load_or_initialize(self) -> dict[str, Any]:
        if self._state_path.exists():
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            if raw.get("schema_version") != SCHEMA_VERSION:
                raise ValueError("diagnosis private state schema mismatch")
            return raw
        nonce = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
        commitment_payload = {
            "scenario_id": SCENARIO_ID,
            "scenario_version": SCENARIO_VERSION,
            "hidden_truth": {"cause": "uncompensated_resistance"},
            "seed_bundle": {"world_seed": 1701, "noise_seed": 2718, "failure_seed": 3141},
            "reveal_nonce": nonce,
        }
        data = {
            "schema_version": SCHEMA_VERSION,
            "commitment_payload": commitment_payload,
            "commitment": _sha(commitment_payload),
            "campaigns": {},
            "create_idempotency": {},
        }
        self._persist(data)
        return data

    def _persist(self, data: dict[str, Any] | None = None) -> None:
        value = data if data is not None else self._data
        temporary = self._state_path.with_suffix(".tmp")
        temporary.write_bytes(_jcs(value))
        os.chmod(temporary, 0o600)
        temporary.replace(self._state_path)

    def _build_scenario(self) -> dict[str, Any]:
        ipa = 14.79847620154866e-6
        ipc = -14.508310001518294e-6
        return {
            "scenario_id": SCENARIO_ID,
            "scenario_version": SCENARIO_VERSION,
            "planner_id": PLANNER_ID,
            "planner_version": PLANNER_VERSION,
            "belief_method": BELIEF_METHOD,
            "prior": deepcopy(PRIOR),
            "attempt_limit": 12,
            "measurement_limit": 10,
            "hypotheses": [
                {"id": identifier, "label": label, "order": order}
                for order, (identifier, label) in enumerate(zip(HYPOTHESES, HYPOTHESIS_LABELS, strict=True))
            ],
            "actions": [
                {
                    "operation": operation,
                    "controls": deepcopy(controls),
                    "display_label": label,
                    "attempt_cost": 1,
                    "measurement_cost": 1,
                }
                for operation, controls, label in ACTION_SPECS
            ],
            "comparator": _fixture(0.830, 0.770, ipa, ipc),
            "initial_trigger": _fixture(0.850, 0.750, ipa, ipc),
            "commitment": self._data["commitment"],
        }

    def _input_hash(self, method: str, path: str, campaign_id: str | None, request_id: str, raw: bytes) -> str:
        return _sha(
            {
                "method": method,
                "canonical_path": path,
                "campaign_id": campaign_id,
                "request_id": request_id,
                "request_body_hash": hashlib.sha256(raw).hexdigest(),
            }
        )

    def _genesis(self, campaign_id: str) -> str:
        return _sha(
            {"campaign_id": campaign_id, "scenario_id": SCENARIO_ID, "scenario_version": SCENARIO_VERSION}
        )

    def _recommendation(self, campaign: dict[str, Any]) -> dict[str, Any] | None:
        if campaign["status"] != "active" or campaign["measurement_used"] >= 10:
            return None
        eligible: list[tuple[float, str, dict[str, float]]] = []
        for operation, controls, _ in ACTION_SPECS:
            if campaign["successful_action_counts"].get(_action_key(operation, controls), 0) < 2:
                eligible.append((_eig(campaign["beliefs"], operation, controls), operation, controls))
        if not eligible:
            return None
        best_eig = max(item[0] for item in eligible)
        _, operation, controls = next(item for item in eligible if best_eig - item[0] <= 1e-12)
        input_value = {
            "operation": operation,
            "controls": controls,
            "state_version": campaign["state_version"],
            "planner_id": PLANNER_ID,
            "planner_version": PLANNER_VERSION,
        }
        action_hash = _sha(input_value)
        return {
            "recommendation_id": action_hash,
            "state_version": campaign["state_version"],
            "planner_id": PLANNER_ID,
            "planner_version": PLANNER_VERSION,
            "operation": operation,
            "controls": deepcopy(controls),
            "reason_code": "max_expected_information",
            "reason_text": REASON_TEXT,
            "attempt_cost": 1,
            "measurement_cost": 1,
            "expected_information_gain_nats": best_eig,
            "action_input_hash": action_hash,
        }

    def _state(self, campaign: dict[str, Any]) -> dict[str, Any]:
        recommendation = self._recommendation(campaign)
        return {
            "campaign_id": campaign["campaign_id"],
            "scenario_id": SCENARIO_ID,
            "scenario_version": SCENARIO_VERSION,
            "state_version": campaign["state_version"],
            "status": campaign["status"],
            "beliefs": deepcopy(campaign["beliefs"]),
            "budget": {
                "attempt_limit": 12,
                "attempt_used": campaign["attempt_used"],
                "measurement_limit": 10,
                "measurement_used": campaign["measurement_used"],
            },
            "success_count": campaign["success_count"],
            "successful_operations": deepcopy(campaign["successful_operations"]),
            "recommendation": recommendation,
            "last_valid_curve_hash": campaign["last_valid_curve_hash"],
            "ledger_head_hash": campaign["ledger_head_hash"],
            "stop": {"terminal": campaign["status"] != "active", "reason": campaign["stop_reason"]},
        }

    def _envelope(
        self,
        *,
        status: str,
        payload: dict[str, Any],
        request_id: str | None = None,
        input_hash: str | None = None,
        campaign: dict[str, Any] | None = None,
        previous_version: int | None = None,
        previous_ledger_hash: str | None = None,
    ) -> bytes:
        state_version = campaign["state_version"] if campaign else None
        ledger_hash = campaign["ledger_head_hash"] if campaign else None
        identity = {
            "status": status,
            "request_id": request_id,
            "idempotency_input_hash": input_hash,
            "campaign_id": campaign["campaign_id"] if campaign else None,
            "state_version": state_version,
            "payload": payload,
        }
        envelope = {
            "schema_version": SCHEMA_VERSION,
            "response_id": "response-" + _sha(identity)[:24],
            "response_hash": "",
            "request_id": request_id,
            "idempotency_input_hash": input_hash,
            "scenario_id": SCENARIO_ID if payload["type"] != "error" or campaign else None,
            "campaign_id": campaign["campaign_id"] if campaign else None,
            "previous_state_version": previous_version,
            "state_version": state_version,
            "previous_ledger_hash": previous_ledger_hash,
            "ledger_hash": ledger_hash,
            "status": status,
            "payload": payload,
        }
        unsigned = {key: value for key, value in envelope.items() if key != "response_hash"}
        envelope["response_hash"] = _sha(unsigned)
        return _jcs(envelope)

    def _error(
        self,
        code: str,
        message: str,
        *,
        request_id: str | None = None,
        input_hash: str | None = None,
        campaign: dict[str, Any] | None = None,
        event: dict[str, Any] | None = None,
        previous_version: int | None = None,
        previous_ledger_hash: str | None = None,
    ) -> bytes:
        return self._envelope(
            status="rejected" if code in REJECTION_MESSAGES else "error",
            payload={
                "type": "error",
                "error": {"code": code, "message": message},
                "state": self._state(campaign) if campaign else None,
                "event": event,
            },
            request_id=request_id,
            input_hash=input_hash,
            campaign=campaign,
            previous_version=previous_version,
            previous_ledger_hash=previous_ledger_hash,
        )

    @staticmethod
    def _parse(raw: bytes) -> tuple[dict[str, Any] | None, str | None]:
        try:
            value = json.loads(raw.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return None, "MALFORMED_JSON"
        return (value, None) if isinstance(value, dict) else (None, "INVALID_REQUEST_ENVELOPE")

    @staticmethod
    def _valid_request_id(value: Any) -> bool:
        return isinstance(value, str) and 1 <= len(value) <= 128 and "\x00" not in value

    @staticmethod
    def _scope_key(
        method: str,
        canonical_path: str,
        campaign_id: str | None,
        request_id: str,
    ) -> str:
        return _jcs_text(
            {
                "method": method.upper(),
                "canonical_path": canonical_path,
                "campaign_id": campaign_id,
                "request_id": request_id,
            }
        )

    def _cached(self, cache: dict[str, Any], scope_key: str, raw: bytes) -> tuple[int, bytes] | None:
        record = cache.get(scope_key)
        if record is None:
            return None
        if base64.b64decode(record["raw_body"]) != raw:
            return 409, b""
        return int(record["http_status"]), base64.b64decode(record["response"])

    def _cache(self, cache: dict[str, Any], scope_key: str, raw: bytes, status: int, response: bytes) -> None:
        cache[scope_key] = {
            "raw_body": base64.b64encode(raw).decode("ascii"),
            "http_status": status,
            "response": base64.b64encode(response).decode("ascii"),
        }
        self._persist()

    def _cache_campaign_response(
        self,
        campaign: dict[str, Any],
        path_suffix: str,
        request_id: str,
        raw: bytes,
        status: int,
        response: bytes,
    ) -> None:
        canonical_path = (
            f"/api/v1/closed-loop/campaigns/{campaign['campaign_id']}/{path_suffix}"
        )
        scope_key = self._scope_key(
            "POST", canonical_path, campaign["campaign_id"], request_id
        )
        self._cache(campaign["idempotency"], scope_key, raw, status, response)

    def get_scenario(self) -> tuple[int, bytes]:
        with self._lock:
            return 200, self._envelope(status="ok", payload={"type": "scenario", "scenario": self._scenario})

    def create_campaign(self, raw_body: bytes) -> tuple[int, bytes]:
        with self._lock:
            request, error = self._parse(raw_body)
            if error:
                return 400, self._error(error, "Request body must be a closed UTF-8 JSON object.")
            request_id = request.get("request_id")
            if not self._valid_request_id(request_id):
                return 400, self._error("INVALID_REQUEST_ENVELOPE", "request_id is required.")
            path = "/api/v1/closed-loop/campaigns"
            scope_key = self._scope_key("POST", path, None, request_id)
            input_hash = self._input_hash("POST", path, None, request_id, raw_body)
            cached = self._cached(self._data["create_idempotency"], scope_key, raw_body)
            if cached:
                if cached[1]:
                    return cached
                body = self._error(
                    "IDEMPOTENCY_CONFLICT",
                    "Request ID was reused with different bytes.",
                    request_id=request_id,
                    input_hash=input_hash,
                )
                return 409, body
            if set(request) != {"request_id", "scenario_id", "scenario_version"} or request.get("scenario_id") != SCENARIO_ID or request.get("scenario_version") != SCENARIO_VERSION:
                body = self._error(
                    "INVALID_REQUEST_ENVELOPE",
                    "Campaign request does not match the frozen scenario.",
                    request_id=request_id,
                    input_hash=input_hash,
                )
                self._cache(self._data["create_idempotency"], scope_key, raw_body, 400, body)
                return 400, body
            campaign_id = "campaign-" + hashlib.sha256(raw_body + str(len(self._data["campaigns"])).encode()).hexdigest()[:24]
            genesis = self._genesis(campaign_id)
            campaign = {
                "campaign_id": campaign_id,
                "state_version": 0,
                "status": "active",
                "stop_reason": None,
                "beliefs": deepcopy(PRIOR),
                "attempt_used": 0,
                "measurement_used": 0,
                "accepted_execution_attempt": 0,
                "success_count": 0,
                "successful_operations": [],
                "successful_action_counts": {},
                "last_valid_curve_hash": None,
                "ledger_head_hash": genesis,
                "events": [],
                "idempotency": {},
                "revealed": False,
            }
            self._data["campaigns"][campaign_id] = campaign
            body = self._envelope(
                status="created",
                payload={"type": "state", "state": self._state(campaign), "event": None},
                request_id=request_id,
                input_hash=input_hash,
                campaign=campaign,
            )
            self._cache(self._data["create_idempotency"], scope_key, raw_body, 201, body)
            return 201, body

    def _campaign_or_error(self, campaign_id: str) -> tuple[dict[str, Any] | None, tuple[int, bytes] | None]:
        campaign = self._data["campaigns"].get(campaign_id)
        if campaign is None:
            return None, (404, self._error("NOT_FOUND", "Campaign was not found."))
        return campaign, None

    def get_campaign(self, campaign_id: str) -> tuple[int, bytes]:
        with self._lock:
            campaign, error = self._campaign_or_error(campaign_id)
            if error:
                return error
            return 200, self._envelope(
                status="ok",
                payload={"type": "state", "state": self._state(campaign), "event": None},
                campaign=campaign,
                previous_version=campaign["state_version"],
                previous_ledger_hash=campaign["ledger_head_hash"],
            )

    def get_ledger(self, campaign_id: str) -> tuple[int, bytes]:
        with self._lock:
            campaign, error = self._campaign_or_error(campaign_id)
            if error:
                return error
            return 200, self._envelope(
                status="ok",
                payload={"type": "ledger", "state": self._state(campaign), "events": deepcopy(campaign["events"])},
                campaign=campaign,
                previous_version=campaign["state_version"],
                previous_ledger_hash=campaign["ledger_head_hash"],
            )

    def _post_base(
        self,
        campaign_id: str,
        raw_body: bytes,
        required: set[str],
        path_suffix: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None, tuple[int, bytes] | None]:
        campaign, not_found = self._campaign_or_error(campaign_id)
        if not_found:
            return None, None, None, not_found
        request, parse_error = self._parse(raw_body)
        if parse_error:
            return campaign, None, None, (400, self._error(parse_error, "Request body must be a closed UTF-8 JSON object.", campaign=campaign))
        request_id = request.get("request_id")
        if not self._valid_request_id(request_id):
            return campaign, request, None, (400, self._error("INVALID_REQUEST_ENVELOPE", "request_id is required.", campaign=campaign))
        canonical_path = f"/api/v1/closed-loop/campaigns/{campaign_id}/{path_suffix}"
        scope_key = self._scope_key("POST", canonical_path, campaign_id, request_id)
        cached = self._cached(campaign["idempotency"], scope_key, raw_body)
        if cached:
            if cached[1]:
                return campaign, request, None, cached
            input_hash = self._input_hash("POST", canonical_path, campaign_id, request_id, raw_body)
            return campaign, request, input_hash, (409, self._error("IDEMPOTENCY_CONFLICT", "Request ID was reused with different bytes.", request_id=request_id, input_hash=input_hash, campaign=campaign, previous_version=campaign["state_version"], previous_ledger_hash=campaign["ledger_head_hash"]))
        input_hash = self._input_hash("POST", canonical_path, campaign_id, request_id, raw_body)
        if set(request) != required or isinstance(request.get("expected_state_version"), bool) or not isinstance(request.get("expected_state_version"), int):
            body = self._error("INVALID_REQUEST_ENVELOPE", "Request fields do not match the closed endpoint schema.", request_id=request_id, input_hash=input_hash, campaign=campaign, previous_version=campaign["state_version"], previous_ledger_hash=campaign["ledger_head_hash"])
            self._cache(campaign["idempotency"], scope_key, raw_body, 400, body)
            return campaign, request, input_hash, (400, body)
        if request["expected_state_version"] != campaign["state_version"]:
            body = self._error("STALE_STATE", "expected_state_version does not match current state.", request_id=request_id, input_hash=input_hash, campaign=campaign, previous_version=campaign["state_version"], previous_ledger_hash=campaign["ledger_head_hash"])
            self._cache(campaign["idempotency"], scope_key, raw_body, 409, body)
            return campaign, request, input_hash, (409, body)
        return campaign, request, input_hash, None

    def _append_event(self, campaign: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
        unsigned = {**event, "event_hash": ""}
        unsigned_without_hash = {key: value for key, value in unsigned.items() if key != "event_hash"}
        event = {**unsigned_without_hash, "event_hash": _sha(unsigned_without_hash)}
        campaign["events"].append(event)
        campaign["ledger_head_hash"] = event["event_hash"]
        campaign["state_version"] = event["state_version_after"]
        return event

    def _apply_terminal_rules(self, campaign: dict[str, Any]) -> None:
        reason = None
        if campaign["attempt_used"] >= 12 or campaign["measurement_used"] >= 10:
            reason = "budget_exhausted"
        elif campaign["success_count"] >= 3 and len(campaign["successful_operations"]) >= 2:
            ordered = sorted(campaign["beliefs"], reverse=True)
            if ordered[0] >= 0.90 and ordered[0] - ordered[1] >= 0.25:
                reason = "confident_diagnosis"
        if reason is None and campaign["success_count"] >= 4:
            recommendation = self._recommendation(campaign)
            if recommendation and recommendation["expected_information_gain_nats"] < 0.01:
                reason = "low_expected_information"
        if reason:
            campaign["stop_reason"] = reason
            campaign["status"] = "budget_exhausted" if reason == "budget_exhausted" else "stopped"

    def _rejected_event(
        self,
        campaign: dict[str, Any],
        request: dict[str, Any],
        input_hash: str,
        code: str,
        *,
        event_type: str = "action",
    ) -> tuple[dict[str, Any], int, str]:
        previous_version = campaign["state_version"]
        previous_hash = campaign["ledger_head_hash"]
        operation = request.get("operation") if request.get("operation") in OPERATIONS else None
        controls = _validate_controls(operation, request.get("controls")) if operation else None
        campaign["attempt_used"] += 1
        event = self._append_event(
            campaign,
            {
                "event_id": f"event-{len(campaign['events']) + 1}",
                "event_index": len(campaign["events"]),
                "event_type": event_type,
                "request_id": request["request_id"],
                "idempotency_input_hash": input_hash,
                "state_version_before": previous_version,
                "state_version_after": previous_version + 1,
                "recommendation_id": request.get("recommendation_id") if isinstance(request.get("recommendation_id"), str) else None,
                "operation": operation,
                "controls": controls,
                "status": "rejected",
                "failure_code": None,
                "failure_message": None,
                "rejection_code": code,
                "rejection_message": REJECTION_MESSAGES[code],
                "attempt_cost": 1,
                "measurement_cost": 0,
                "observation": None,
                "beliefs_before": deepcopy(campaign["beliefs"]),
                "beliefs_after": deepcopy(campaign["beliefs"]),
                "previous_event_hash": previous_hash,
            },
        )
        self._apply_terminal_rules(campaign)
        return event, previous_version, previous_hash

    def _noise(self, operation: str, controls: dict[str, float], repeat: int, dimension: int) -> float:
        key = _jcs({"seed": 2718, "operation": operation, "controls": controls, "repeat": repeat, "dimension": dimension})
        seed = int.from_bytes(hashlib.sha256(key).digest()[:8], "big")
        return random.Random(seed).gauss(0.0, 1.0)

    def _observation(self, operation: str, controls: dict[str, float], repeat: int) -> tuple[dict[str, Any], list[float]]:
        means, standard_errors, features = _means(operation, controls)
        truth_means = means[1]
        values = [
            mean + self._noise(operation, controls, repeat, dimension) * standard_errors[dimension]
            for dimension, mean in enumerate(truth_means)
        ]
        if operation == "repeat_cv":
            midpoint, delta_ep, absolute_ipa = values
            curve = _curve(midpoint + delta_ep / 2, midpoint - delta_ep / 2, absolute_ipa, -absolute_ipa / 1.02)
            peak = _extract_peak(curve)
            likelihood_values = [peak["midpoint_v"], peak["delta_Ep_v"], abs(peak["ipa_a"])]
            unsigned = {
                "kind": "cv",
                "feature_name": None,
                "value": None,
                "unit": None,
                "peak": peak,
                "curve": curve,
                "qc_status": "passed",
            }
        else:
            feature = features[0]
            unit = {
                "ru_ohm": "ohm",
                "reference_offset_v": "V",
                "blank_current_a": "A",
                "recovery_ratio": "ratio",
                "control_delta_Ep_v": "V",
            }[feature]
            likelihood_values = values
            unsigned = {
                "kind": "scalar",
                "feature_name": feature,
                "value": values[0],
                "unit": unit,
                "peak": None,
                "curve": None,
                "qc_status": "passed",
            }
        return {**unsigned, "evidence_hash": _sha(unsigned)}, likelihood_values

    def act(self, campaign_id: str, raw_body: bytes) -> tuple[int, bytes]:
        with self._lock:
            required = {"request_id", "expected_state_version", "recommendation_id", "action_input_hash", "operation", "controls"}
            campaign, request, input_hash, early = self._post_base(campaign_id, raw_body, required, "actions")
            if early:
                return early
            assert campaign is not None and request is not None and input_hash is not None
            if campaign["status"] != "active":
                body = self._error("TERMINAL_STATE", "Campaign is already terminal.", request_id=request["request_id"], input_hash=input_hash, campaign=campaign, previous_version=campaign["state_version"], previous_ledger_hash=campaign["ledger_head_hash"])
                self._cache_campaign_response(
                    campaign, "actions", request["request_id"], raw_body, 409, body
                )
                return 409, body
            operation = request.get("operation")
            if operation not in OPERATIONS:
                rejection = "INVALID_OPERATION"
            else:
                controls = _validate_controls(operation, request.get("controls"))
                recommendation = self._recommendation(campaign)
                if controls is None:
                    rejection = "INVALID_CONTROLS"
                elif not recommendation or campaign["successful_action_counts"].get(_action_key(operation, controls), 0) >= 2:
                    rejection = "INELIGIBLE_ACTION"
                elif any(request.get(key) != recommendation[key] for key in ("recommendation_id", "action_input_hash", "operation", "controls")):
                    rejection = "INVALID_RECOMMENDATION"
                else:
                    rejection = None
            if rejection:
                event, previous_version, previous_hash = self._rejected_event(campaign, request, input_hash, rejection)
                body = self._error(rejection, REJECTION_MESSAGES[rejection], request_id=request["request_id"], input_hash=input_hash, campaign=campaign, event=event, previous_version=previous_version, previous_ledger_hash=previous_hash)
                self._cache_campaign_response(
                    campaign, "actions", request["request_id"], raw_body, 422, body
                )
                return 422, body
            previous_version = campaign["state_version"]
            previous_hash = campaign["ledger_head_hash"]
            beliefs_before = deepcopy(campaign["beliefs"])
            campaign["attempt_used"] += 1
            campaign["measurement_used"] += 1
            campaign["accepted_execution_attempt"] += 1
            status = "timeout" if campaign["accepted_execution_attempt"] == 2 else "success"
            observation = None
            failure_code = failure_message = None
            if status == "timeout":
                failure_code = "TIMEOUT"
                failure_message = "Operation timed out; no observation was created."
            else:
                key = _action_key(operation, controls)
                repeat = campaign["successful_action_counts"].get(key, 0)
                observation, likelihood_values = self._observation(operation, controls, repeat)
                means, standard_errors, _ = _means(operation, controls)
                campaign["beliefs"] = _posterior(campaign["beliefs"], likelihood_values, means, standard_errors)
                campaign["successful_action_counts"][key] = repeat + 1
                campaign["success_count"] += 1
                if operation not in campaign["successful_operations"]:
                    campaign["successful_operations"].append(operation)
                if operation == "repeat_cv":
                    campaign["last_valid_curve_hash"] = observation["curve"]["curve_hash"]
            event = self._append_event(
                campaign,
                {
                    "event_id": f"event-{len(campaign['events']) + 1}",
                    "event_index": len(campaign["events"]),
                    "event_type": "action",
                    "request_id": request["request_id"],
                    "idempotency_input_hash": input_hash,
                    "state_version_before": previous_version,
                    "state_version_after": previous_version + 1,
                    "recommendation_id": request["recommendation_id"],
                    "operation": operation,
                    "controls": controls,
                    "status": status,
                    "failure_code": failure_code,
                    "failure_message": failure_message,
                    "rejection_code": None,
                    "rejection_message": None,
                    "attempt_cost": 1,
                    "measurement_cost": 1,
                    "observation": observation,
                    "beliefs_before": beliefs_before,
                    "beliefs_after": deepcopy(campaign["beliefs"]),
                    "previous_event_hash": previous_hash,
                },
            )
            self._apply_terminal_rules(campaign)
            body = self._envelope(
                status="ok",
                payload={"type": "state", "state": self._state(campaign), "event": event},
                request_id=request["request_id"],
                input_hash=input_hash,
                campaign=campaign,
                previous_version=previous_version,
                previous_ledger_hash=previous_hash,
            )
            self._cache_campaign_response(
                campaign, "actions", request["request_id"], raw_body, 200, body
            )
            return 200, body

    def stop(self, campaign_id: str, raw_body: bytes) -> tuple[int, bytes]:
        with self._lock:
            campaign, request, input_hash, early = self._post_base(campaign_id, raw_body, {"request_id", "expected_state_version"}, "stop")
            if early:
                return early
            assert campaign is not None and request is not None and input_hash is not None
            if campaign["status"] != "active":
                body = self._envelope(status="ok", payload={"type": "state", "state": self._state(campaign), "event": None}, request_id=request["request_id"], input_hash=input_hash, campaign=campaign, previous_version=campaign["state_version"], previous_ledger_hash=campaign["ledger_head_hash"])
                self._cache_campaign_response(
                    campaign, "stop", request["request_id"], raw_body, 200, body
                )
                return 200, body
            event, previous_version, previous_hash = self._rejected_event(campaign, request, input_hash, "STOP_RULE_NOT_SATISFIED", event_type="stop")
            body = self._error("STOP_RULE_NOT_SATISFIED", REJECTION_MESSAGES["STOP_RULE_NOT_SATISFIED"], request_id=request["request_id"], input_hash=input_hash, campaign=campaign, event=event, previous_version=previous_version, previous_ledger_hash=previous_hash)
            self._cache_campaign_response(
                campaign, "stop", request["request_id"], raw_body, 422, body
            )
            return 422, body

    def reveal(self, campaign_id: str, raw_body: bytes) -> tuple[int, bytes]:
        with self._lock:
            campaign, request, input_hash, early = self._post_base(campaign_id, raw_body, {"request_id", "expected_state_version"}, "reveal")
            if early:
                return early
            assert campaign is not None and request is not None and input_hash is not None
            if campaign["status"] == "active":
                status = 409
                body = self._error("REVEAL_NOT_AVAILABLE", "Reveal is available only after terminal state.", request_id=request["request_id"], input_hash=input_hash, campaign=campaign, previous_version=campaign["state_version"], previous_ledger_hash=campaign["ledger_head_hash"])
            elif campaign["revealed"]:
                status = 409
                body = self._error("REVEAL_ALREADY_COMPLETED", "Synthetic truth was already revealed.", request_id=request["request_id"], input_hash=input_hash, campaign=campaign, previous_version=campaign["state_version"], previous_ledger_hash=campaign["ledger_head_hash"])
            else:
                status = 200
                campaign["revealed"] = True
                body = self._envelope(
                    status="ok",
                    payload={"type": "reveal", "reveal": {"commitment": self._data["commitment"], "commitment_payload": deepcopy(self._data["commitment_payload"])}},
                    request_id=request["request_id"],
                    input_hash=input_hash,
                    campaign=campaign,
                    previous_version=campaign["state_version"],
                    previous_ledger_hash=campaign["ledger_head_hash"],
                )
            self._cache_campaign_response(
                campaign, "reveal", request["request_id"], raw_body, status, body
            )
            return status, body
