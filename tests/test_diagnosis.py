from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import pytest

from discovery_flight_simulator.diagnosis import DiagnosisService, _sha


PRIVATE_FIELDS = {"hidden_truth", "seed_bundle", "reveal_nonce", "world_seed", "noise_seed", "failure_seed"}


def _raw(value: dict[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _decoded(result: tuple[int, bytes]) -> tuple[int, dict[str, Any], bytes]:
    status, raw = result
    return status, json.loads(raw), raw


def _new_campaign(service: DiagnosisService, request_id: str = "create-1") -> tuple[str, dict[str, Any], bytes]:
    status, envelope, raw = _decoded(
        service.create_campaign(
            _raw(
                {
                    "request_id": request_id,
                    "scenario_id": "cv_diagnosis_v1",
                    "scenario_version": "1.0.0",
                }
            )
        )
    )
    assert status == 201
    return envelope["campaign_id"], envelope["payload"]["state"], raw


def _recommended_action(state: dict[str, Any], request_id: str) -> bytes:
    recommendation = state["recommendation"]
    assert recommendation is not None
    return _raw(
        {
            "request_id": request_id,
            "expected_state_version": state["state_version"],
            "recommendation_id": recommendation["recommendation_id"],
            "action_input_hash": recommendation["action_input_hash"],
            "operation": recommendation["operation"],
            "controls": recommendation["controls"],
        }
    )


def _private_keys(value: Any) -> set[str]:
    if isinstance(value, list):
        return set().union(*(_private_keys(item) for item in value), set())
    if not isinstance(value, dict):
        return set()
    found = PRIVATE_FIELDS.intersection(value)
    return found.union(*(_private_keys(item) for item in value.values()), set())


def _verify_envelope_hash(envelope: dict[str, Any]) -> None:
    unsigned = {key: value for key, value in envelope.items() if key != "response_hash"}
    assert envelope["response_hash"] == _sha(unsigned)


def _verify_curve(curve: dict[str, Any], peak: dict[str, float]) -> None:
    assert curve["point_count"] == 122
    assert len(curve["potential_v"]) == len(curve["current_a"]) == len(curve["sweep_direction"]) == 122
    assert curve["sweep_direction"] == ["forward"] * 61 + ["reverse"] * 61
    expected_grid = [0.650 + 0.005 * index for index in range(61)]
    expected_grid += [0.950 - 0.005 * index for index in range(61)]
    assert curve["potential_v"] == expected_grid
    assert all(math.isfinite(value) for value in curve["current_a"])
    unsigned_curve = {key: value for key, value in curve.items() if key != "curve_hash"}
    assert curve["curve_hash"] == _sha(unsigned_curve)

    pa = max(range(61), key=lambda index: curve["current_a"][index])
    pc = min(range(61, 122), key=lambda index: curve["current_a"][index])
    epa, epc = curve["potential_v"][pa], curve["potential_v"][pc]
    ipa, ipc = curve["current_a"][pa], curve["current_a"][pc]
    assert peak == pytest.approx(
        {
            "Epa_v": epa,
            "Epc_v": epc,
            "ipa_a": ipa,
            "ipc_a": ipc,
            "midpoint_v": (epa + epc) / 2,
            "delta_Ep_v": epa - epc,
            "ipa_abs_over_ipc_abs": abs(ipa) / abs(ipc),
        },
        rel=0,
        abs=1e-18,
    )


def test_scenario_commitment_and_preterminal_responses_do_not_leak_truth(tmp_path) -> None:
    service = DiagnosisService(tmp_path)
    scenario_status, scenario, _ = _decoded(service.get_scenario())
    assert scenario_status == 200
    public_scenario = scenario["payload"]["scenario"]
    assert len(public_scenario["commitment"]) == 64
    assert [item["id"] for item in public_scenario["hypotheses"]] == [
        "slow_kinetics",
        "uncompensated_resistance",
        "reference_drift",
        "electrode_fouling",
        "concentration_preparation_error",
    ]
    assert len(public_scenario["actions"]) == 12

    campaign_id, state, create_raw = _new_campaign(service)
    _, campaign, campaign_raw = _decoded(service.get_campaign(campaign_id))
    _, ledger, ledger_raw = _decoded(service.get_ledger(campaign_id))
    _, action, action_raw = _decoded(service.act(campaign_id, _recommended_action(state, "action-1")))
    for envelope, raw in (
        (scenario, json.dumps(scenario).encode()),
        (campaign, campaign_raw),
        (ledger, ledger_raw),
        (action, action_raw),
    ):
        _verify_envelope_hash(envelope)
        assert not _private_keys(envelope)
        assert b"uncompensated_resistance" not in raw or envelope is scenario
    assert not _private_keys(json.loads(create_raw))


def test_successful_cv_action_returns_verified_full_curve_and_updates_beliefs(tmp_path) -> None:
    service = DiagnosisService(tmp_path)
    campaign_id, initial_state, _ = _new_campaign(service)
    status, envelope, _ = _decoded(service.act(campaign_id, _recommended_action(initial_state, "action-1")))

    assert status == 200
    event = envelope["payload"]["event"]
    state = envelope["payload"]["state"]
    assert event["status"] == "success"
    assert event["observation"]["kind"] == "cv"
    assert event["observation"]["qc_status"] == "passed"
    _verify_curve(event["observation"]["curve"], event["observation"]["peak"])
    unsigned_observation = {key: value for key, value in event["observation"].items() if key != "evidence_hash"}
    assert event["observation"]["evidence_hash"] == _sha(unsigned_observation)
    assert event["beliefs_before"] == initial_state["beliefs"]
    assert event["beliefs_after"] != initial_state["beliefs"]
    assert state["beliefs"] == event["beliefs_after"]
    assert sum(state["beliefs"]) == pytest.approx(1.0, abs=1e-12)
    assert state["budget"] == {
        "attempt_limit": 12,
        "attempt_used": 1,
        "measurement_limit": 10,
        "measurement_used": 1,
    }
    assert state["last_valid_curve_hash"] == event["observation"]["curve"]["curve_hash"]


def test_second_accepted_execution_times_out_without_changing_beliefs(tmp_path) -> None:
    service = DiagnosisService(tmp_path)
    campaign_id, state, _ = _new_campaign(service)
    _, first, _ = _decoded(service.act(campaign_id, _recommended_action(state, "action-1")))
    after_first = first["payload"]["state"]
    status, second, _ = _decoded(service.act(campaign_id, _recommended_action(after_first, "action-2")))

    assert status == 200
    event = second["payload"]["event"]
    state = second["payload"]["state"]
    assert event["status"] == "timeout"
    assert event["failure_code"] == "TIMEOUT"
    assert event["observation"] is None
    assert event["beliefs_after"] == event["beliefs_before"] == after_first["beliefs"]
    assert event["attempt_cost"] == event["measurement_cost"] == 1
    assert state["budget"]["attempt_used"] == 2
    assert state["budget"]["measurement_used"] == 2
    assert state["success_count"] == 1


def test_rejected_action_is_a_ledger_event_costing_one_attempt_and_zero_measurements(tmp_path) -> None:
    service = DiagnosisService(tmp_path)
    campaign_id, state, _ = _new_campaign(service)
    request = json.loads(_recommended_action(state, "reject-1"))
    request["recommendation_id"] = "0" * 64
    status, envelope, _ = _decoded(service.act(campaign_id, _raw(request)))

    assert status == 422
    assert envelope["status"] == "rejected"
    assert envelope["payload"]["error"]["code"] == "INVALID_RECOMMENDATION"
    event = envelope["payload"]["event"]
    assert event["status"] == "rejected"
    assert event["attempt_cost"] == 1
    assert event["measurement_cost"] == 0
    assert event["observation"] is None
    assert event["beliefs_after"] == event["beliefs_before"]
    assert envelope["payload"]["state"]["budget"]["attempt_used"] == 1
    assert envelope["payload"]["state"]["budget"]["measurement_used"] == 0


def test_exact_replay_conflict_and_route_scoped_idempotency(tmp_path) -> None:
    service = DiagnosisService(tmp_path)
    campaign_id, state, _ = _new_campaign(service)
    action_raw = _recommended_action(state, "shared-request-id")
    first_status, first_body = service.act(campaign_id, action_raw)
    replay_status, replay_body = service.act(campaign_id, action_raw)
    assert (replay_status, replay_body) == (first_status, first_body)

    changed = json.loads(action_raw)
    changed["expected_state_version"] = 1
    conflict_status, conflict, _ = _decoded(service.act(campaign_id, _raw(changed)))
    assert conflict_status == 409
    assert conflict["payload"]["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    _, ledger_after_conflict, _ = _decoded(service.get_ledger(campaign_id))
    assert len(ledger_after_conflict["payload"]["events"]) == 1

    stop_status, stop, _ = _decoded(
        service.stop(
            campaign_id,
            _raw({"request_id": "shared-request-id", "expected_state_version": 1}),
        )
    )
    assert stop_status == 422
    assert stop["payload"]["error"]["code"] == "STOP_RULE_NOT_SATISFIED"


def test_create_parseable_conflict_and_closed_error_carry_scoped_input_hash(tmp_path) -> None:
    service = DiagnosisService(tmp_path)
    valid = _raw(
        {
            "request_id": "create-scoped",
            "scenario_id": "cv_diagnosis_v1",
            "scenario_version": "1.0.0",
        }
    )
    status, created, _ = _decoded(service.create_campaign(valid))
    assert status == 201
    assert created["state_version"] == 0

    changed = b'{"request_id":"create-scoped","scenario_id":"wrong","scenario_version":"1.0.0"}'
    conflict_status, conflict, _ = _decoded(service.create_campaign(changed))
    expected_conflict_hash = _sha(
        {
            "method": "POST",
            "canonical_path": "/api/v1/closed-loop/campaigns",
            "campaign_id": None,
            "request_id": "create-scoped",
            "request_body_hash": hashlib.sha256(changed).hexdigest(),
        }
    )
    assert conflict_status == 409
    assert conflict["idempotency_input_hash"] == expected_conflict_hash
    assert conflict["campaign_id"] is None
    assert len(service._data["campaigns"]) == 1

    invalid = b'{"request_id":"create-invalid","scenario_id":"wrong","scenario_version":"1.0.0"}'
    invalid_status, invalid_envelope, _ = _decoded(service.create_campaign(invalid))
    expected_invalid_hash = _sha(
        {
            "method": "POST",
            "canonical_path": "/api/v1/closed-loop/campaigns",
            "campaign_id": None,
            "request_id": "create-invalid",
            "request_body_hash": hashlib.sha256(invalid).hexdigest(),
        }
    )
    assert invalid_status == 400
    assert invalid_envelope["idempotency_input_hash"] == expected_invalid_hash
    assert len(service._data["campaigns"]) == 1


def test_ledger_event_hash_chain_and_versions_are_verifiable(tmp_path) -> None:
    service = DiagnosisService(tmp_path)
    campaign_id, state, _ = _new_campaign(service)
    _, first, _ = _decoded(service.act(campaign_id, _recommended_action(state, "action-1")))
    state = first["payload"]["state"]
    _, second, _ = _decoded(service.act(campaign_id, _recommended_action(state, "action-2")))
    state = second["payload"]["state"]
    invalid = json.loads(_recommended_action(state, "reject-3"))
    invalid["operation"] = "not_an_operation"
    service.act(campaign_id, _raw(invalid))

    status, ledger, _ = _decoded(service.get_ledger(campaign_id))
    assert status == 200
    _verify_envelope_hash(ledger)
    events = ledger["payload"]["events"]
    assert len(events) == 3
    previous_hash = events[0]["previous_event_hash"]
    assert len(previous_hash) == 64
    for index, event in enumerate(events):
        assert event["event_index"] == index
        assert event["state_version_before"] == index
        assert event["state_version_after"] == index + 1
        assert event["previous_event_hash"] == previous_hash
        assert event["event_hash"] == _sha({key: value for key, value in event.items() if key != "event_hash"})
        previous_hash = event["event_hash"]
    assert ledger["ledger_hash"] == previous_hash
    assert ledger["payload"]["state"]["ledger_head_hash"] == previous_hash
    assert ledger["payload"]["state"]["state_version"] == 3


def test_truth_reveal_requires_terminal_state_verifies_commitment_and_is_one_time(tmp_path) -> None:
    service = DiagnosisService(tmp_path)
    _, scenario, _ = _decoded(service.get_scenario())
    commitment = scenario["payload"]["scenario"]["commitment"]
    campaign_id, state, _ = _new_campaign(service)

    pre_status, pre, _ = _decoded(
        service.reveal(campaign_id, _raw({"request_id": "reveal-early", "expected_state_version": 0}))
    )
    assert pre_status == 409
    assert pre["payload"]["error"]["code"] == "REVEAL_NOT_AVAILABLE"

    action_index = 0
    while state["status"] == "active":
        action_index += 1
        status, response, _ = _decoded(
            service.act(campaign_id, _recommended_action(state, f"terminal-action-{action_index}"))
        )
        assert status == 200
        state = response["payload"]["state"]
        assert action_index <= 12
    assert state["stop"]["terminal"] is True

    reveal_raw = _raw({"request_id": "reveal-final", "expected_state_version": state["state_version"]})
    reveal_status, reveal, reveal_bytes = _decoded(service.reveal(campaign_id, reveal_raw))
    assert reveal_status == 200
    opened = reveal["payload"]["reveal"]
    assert opened["commitment"] == commitment == _sha(opened["commitment_payload"])
    assert opened["commitment_payload"]["hidden_truth"] == {"cause": "uncompensated_resistance"}
    assert len(opened["commitment_payload"]["reveal_nonce"]) == 43

    replay_status, _, replay_bytes = _decoded(service.reveal(campaign_id, reveal_raw))
    assert replay_status == 200
    assert replay_bytes == reveal_bytes
    repeat_status, repeat, _ = _decoded(
        service.reveal(
            campaign_id,
            _raw({"request_id": "reveal-again", "expected_state_version": state["state_version"]}),
        )
    )
    assert repeat_status == 409
    assert repeat["payload"]["error"]["code"] == "REVEAL_ALREADY_COMPLETED"
