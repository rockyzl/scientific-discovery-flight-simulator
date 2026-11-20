"""Pure logical replay for public ``rfb_campaign_event_v1`` journals.

The reducer intentionally has no dependency on the SQLite store.  It verifies
the public contract hashes and rebuilds the materialized campaign snapshot from
the event payloads, so a valid-looking rehash cannot bless an invalid state
transition.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from discovery_flight_simulator.ledger import canonical_json

from .contracts import (
    RFB_CAMPAIGN_EVENT_SCHEMA_VERSION,
    RFBActionSchemaV1,
    RFBActionV1,
    RFBOutcomeV1,
    RFBPublicCostModelV1,
    RFBRecommendationV1,
    RFBScenarioV1,
    FrozenScalarUtilityV1,
    build_rfb_campaign_event_v1,
)
from .utility import utility_record_for_outcome


RFB_WORKFLOW_VERSION = "rfb_workflow_v1"
GENESIS_EVENT_SHA256 = "0" * 64

AWAITING_RECOMMENDATION = "awaiting_recommendation"
AWAITING_REVIEW = "awaiting_review"
APPROVED = "approved"
EXECUTING = "executing"
ABORTED = "aborted"
STRICT_BENCHMARK_MODE = "strict_benchmark"
WORKFLOW_CASE_STUDY_MODE = "workflow_case_study"

_EXPORT_FIELDS = frozenset({"workflow_version", "campaign", "event_head_sha256", "events"})
_CAMPAIGN_FIELDS = frozenset(
    {
        "workflow_version",
        "campaign_id",
        "revision",
        "phase",
        "policy_id",
        "policy_version",
        "public_scenario",
        "pending_recommendation",
        "decisions",
        "executions",
        "rejected_action_ids",
        "cumulative_costs",
        "reserved_costs",
        "mode",
        "comparison_eligible",
        "human_intervened",
        "approved_decision",
    }
)
_SCENARIO_FIELDS = frozenset(
    {
        "schema_version",
        "domain_version",
        "scenario_id",
        "scenario_version",
        "provenance",
        "model_dimension",
        "total_attempt_budget",
        "total_measurement_budget",
        "varying_axes",
        "action_schema",
        "fixed_fields",
        "ocv_50_soc_V",
        "fixed_action_values",
        "candidate_actions",
        "candidate_set_sha256",
        "cost_model",
        "cost_model_sha256",
        "utility",
        "utility_sha256",
        "public_projection_sha256",
    }
)
_RECOMMENDATION_FIELDS = frozenset(
    {
        "schema_version",
        "policy_id",
        "policy_version",
        "action",
        "action_id",
        "public_projection_sha256",
        "candidate_set_sha256",
        "utility_sha256",
        "basis_event_head_sha256",
        "basis_revision",
        "remaining_attempt_budget",
        "remaining_measurement_budget",
        "predicted_utility_mean",
        "predicted_utility_std",
        "rationale",
        "recommendation_id",
        "recommendation_sha256",
        "request",
    }
)
_EXECUTION_FIELDS = frozenset(
    {
        "decision_id",
        "recommendation_id",
        "request_id",
        "action_id",
        "action",
        "outcome",
        "utility_record",
        "costs",
    }
)


class RFBReplayError(ValueError):
    """Raised when a public RFB journal cannot be replayed exactly."""


@dataclass(frozen=True)
class ReplayedRFBCampaignV1:
    """The public campaign snapshot independently derived from its event log."""

    campaign: dict[str, Any]
    event_head_sha256: str

    @property
    def human_intervened(self) -> bool:
        return bool(self.campaign["human_intervened"])

    @property
    def comparison_eligible(self) -> bool:
        return bool(self.campaign["comparison_eligible"])

    @property
    def ranking_eligible(self) -> bool:
        return bool(
            self.campaign["mode"] == STRICT_BENCHMARK_MODE
            and self.comparison_eligible
            and not self.human_intervened
        )


@dataclass
class _ReplayState:
    campaign_id: str
    policy_id: str
    policy_version: str
    scenario: RFBScenarioV1
    revision: int = 0
    phase: str = AWAITING_RECOMMENDATION
    pending_recommendation: dict[str, Any] | None = None
    decisions: list[dict[str, Any]] | None = None
    executions: list[dict[str, Any]] | None = None
    rejected_action_ids: list[str] | None = None
    cumulative_costs: dict[str, int] | None = None
    reserved_costs: dict[str, int] | None = None
    mode: str = STRICT_BENCHMARK_MODE
    human_intervened: bool = False
    approved_decision: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.decisions = [] if self.decisions is None else self.decisions
        self.executions = [] if self.executions is None else self.executions
        self.rejected_action_ids = [] if self.rejected_action_ids is None else self.rejected_action_ids
        self.cumulative_costs = (
            {"attempts": 0, "measurements": 0}
            if self.cumulative_costs is None
            else self.cumulative_costs
        )
        self.reserved_costs = (
            {"attempts": 0, "measurements": 0} if self.reserved_costs is None else self.reserved_costs
        )

    @property
    def comparison_eligible(self) -> bool:
        return not self.human_intervened

    @property
    def remaining_budgets(self) -> dict[str, int]:
        return {
            "attempts": self.scenario.total_attempt_budget
            - self.cumulative_costs["attempts"]
            - self.reserved_costs["attempts"],
            "measurements": self.scenario.total_measurement_budget
            - self.cumulative_costs["measurements"]
            - self.reserved_costs["measurements"],
        }

    def to_campaign_dict(self) -> dict[str, Any]:
        return {
            "workflow_version": RFB_WORKFLOW_VERSION,
            "campaign_id": self.campaign_id,
            "revision": self.revision,
            "phase": self.phase,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "public_scenario": self.scenario.to_dict(),
            "pending_recommendation": copy.deepcopy(self.pending_recommendation),
            "decisions": copy.deepcopy(self.decisions),
            "executions": copy.deepcopy(self.executions),
            "rejected_action_ids": list(self.rejected_action_ids),
            "cumulative_costs": dict(self.cumulative_costs),
            "reserved_costs": dict(self.reserved_costs),
            "mode": self.mode,
            "comparison_eligible": self.comparison_eligible,
            "human_intervened": self.human_intervened,
            "approved_decision": copy.deepcopy(self.approved_decision),
        }


def replay_rfb_campaign_export_v1(exported: Mapping[str, Any]) -> ReplayedRFBCampaignV1:
    """Verify and replay one exact ``SQLiteRFBCampaignStore.export_campaign`` value."""

    raw = _canonical_mapping(exported, "campaign export")
    _require_exact_keys(raw, _EXPORT_FIELDS, "campaign export")
    _require_equal(raw["workflow_version"], RFB_WORKFLOW_VERSION, "workflow version")
    _require_sha256(raw["event_head_sha256"], "event_head_sha256")
    if not isinstance(raw["events"], list) or not raw["events"]:
        raise RFBReplayError("campaign export must contain its canonical genesis event")

    state: _ReplayState | None = None
    previous = GENESIS_EVENT_SHA256
    recommendation_ids: set[str] = set()
    decision_ids: set[str] = set()
    execution_decision_ids: set[str] = set()
    for sequence, event in enumerate(raw["events"]):
        event_data = _canonical_mapping(event, f"events[{sequence}]")
        _verify_contract_event(event_data, sequence, previous)
        event_type = event_data["event_type"]
        payload = event_data["payload"]
        if sequence == 0:
            state = _apply_campaign_created(event_type, payload)
        else:
            if state is None:
                raise AssertionError("genesis event must establish replay state")
            _apply_transition(
                state,
                event_type,
                payload,
                previous_event_sha256=previous,
                recommendation_ids=recommendation_ids,
                decision_ids=decision_ids,
                execution_decision_ids=execution_decision_ids,
            )
        if state is not None and sequence == 0:
            # The first event has no recommendation, decision, or execution ID to reserve.
            pass
        previous = event_data["event_sha256"]

    if state is None:
        raise RFBReplayError("campaign journal is missing campaign_created")
    if raw["event_head_sha256"] != previous:
        raise RFBReplayError("campaign export event_head_sha256 does not match the event chain")
    _validate_terminal_state(raw["campaign"], state)
    return ReplayedRFBCampaignV1(campaign=state.to_campaign_dict(), event_head_sha256=previous)


def _apply_campaign_created(event_type: Any, payload: Any) -> _ReplayState:
    if event_type != "campaign_created":
        raise RFBReplayError("first campaign event must be campaign_created")
    data = _canonical_mapping(payload, "campaign_created payload")
    _require_exact_keys(
        data,
        {"campaign_id", "policy_id", "policy_version", "public_scenario"},
        "campaign_created payload",
    )
    campaign_id = _nonempty_string(data["campaign_id"], "campaign_id")
    policy_id = _nonempty_string(data["policy_id"], "policy_id")
    policy_version = _nonempty_string(data["policy_version"], "policy_version")
    return _ReplayState(
        campaign_id=campaign_id,
        policy_id=policy_id,
        policy_version=policy_version,
        scenario=_scenario_from_public_payload(data["public_scenario"]),
    )


def _apply_transition(
    state: _ReplayState,
    event_type: str,
    payload: Any,
    *,
    previous_event_sha256: str,
    recommendation_ids: set[str],
    decision_ids: set[str],
    execution_decision_ids: set[str],
) -> None:
    if event_type == "recommendation_saved":
        _apply_recommendation_saved(state, payload, previous_event_sha256, recommendation_ids)
    elif event_type == "approval_recorded":
        _apply_approval(state, payload, decision_ids)
    elif event_type == "intervention_recorded":
        _apply_intervention(state, payload, previous_event_sha256, recommendation_ids, decision_ids)
    elif event_type == "invalid_protocol_consumed":
        _apply_invalid_protocol(state, payload)
    elif event_type == "execution_started":
        _apply_execution_started(state, payload)
    elif event_type == "execution_completed":
        _apply_execution_completed(state, payload, execution_decision_ids)
    else:
        raise RFBReplayError(f"unsupported RFB campaign event type: {event_type!r}")


def _apply_recommendation_saved(
    state: _ReplayState,
    payload: Any,
    previous_event_sha256: str,
    recommendation_ids: set[str],
) -> None:
    if state.phase != AWAITING_RECOMMENDATION:
        raise RFBReplayError("recommendation_saved requires awaiting_recommendation")
    data = _canonical_mapping(payload, "recommendation_saved payload")
    _require_exact_keys(data, {"recommendation"}, "recommendation_saved payload")
    recommendation = _validated_recommendation(
        data["recommendation"], state, previous_event_sha256, recommendation_ids
    )
    state.pending_recommendation = recommendation
    state.phase = AWAITING_REVIEW
    state.revision += 1


def _apply_approval(state: _ReplayState, payload: Any, decision_ids: set[str]) -> None:
    if state.phase != AWAITING_REVIEW or state.pending_recommendation is None:
        raise RFBReplayError("approval_recorded requires a pending review")
    data = _canonical_mapping(payload, "approval_recorded payload")
    _require_exact_keys(data, {"approval"}, "approval_recorded payload")
    approval = _validated_decision(data["approval"], state.pending_recommendation, "approve", decision_ids)
    state.decisions.append(approval)
    state.approved_decision = approval
    state.phase = APPROVED
    state.revision += 1


def _apply_intervention(
    state: _ReplayState,
    payload: Any,
    previous_event_sha256: str,
    recommendation_ids: set[str],
    decision_ids: set[str],
) -> None:
    if state.phase != AWAITING_REVIEW or state.pending_recommendation is None:
        raise RFBReplayError("intervention_recorded requires a pending review")
    data = _canonical_mapping(payload, "intervention_recorded payload")
    intervention = _canonical_mapping(data.get("intervention"), "intervention_recorded intervention")
    decision_type = intervention.get("decision")
    if decision_type == "approve_with_edit":
        _require_exact_keys(data, {"intervention", "recommendation"}, "edit intervention payload")
        decision = _validated_decision(
            intervention, state.pending_recommendation, "approve_with_edit", decision_ids
        )
        recommendation = _validated_recommendation(
            data["recommendation"], state, previous_event_sha256, recommendation_ids
        )
        if decision.get("edited_recommendation_id") != recommendation["recommendation_id"]:
            raise RFBReplayError("edited approval does not bind the replacement recommendation")
        state.decisions.append(decision)
        state.pending_recommendation = recommendation
        state.phase = AWAITING_REVIEW
    elif decision_type == "reject":
        _require_exact_keys(data, {"intervention"}, "reject intervention payload")
        decision = _validated_decision(intervention, state.pending_recommendation, "reject", decision_ids)
        state.decisions.append(decision)
        if state.pending_recommendation["action_id"] not in state.rejected_action_ids:
            state.rejected_action_ids.append(state.pending_recommendation["action_id"])
        state.pending_recommendation = None
        state.phase = AWAITING_RECOMMENDATION
    elif decision_type == "abort":
        _require_exact_keys(data, {"intervention"}, "abort intervention payload")
        decision = _validated_decision(intervention, state.pending_recommendation, "abort", decision_ids)
        state.decisions.append(decision)
        state.pending_recommendation = None
        state.phase = ABORTED
    else:
        raise RFBReplayError("intervention_recorded has an unsupported decision")
    state.mode = WORKFLOW_CASE_STUDY_MODE
    state.human_intervened = True
    state.approved_decision = None
    state.revision += 1


def _apply_invalid_protocol(state: _ReplayState, payload: Any) -> None:
    if state.phase != AWAITING_REVIEW or state.pending_recommendation is None:
        raise RFBReplayError("invalid_protocol_consumed requires a pending review")
    data = _canonical_mapping(payload, "invalid_protocol_consumed payload")
    _require_exact_keys(data, {"consumption"}, "invalid_protocol_consumed payload")
    consumption = _canonical_mapping(data["consumption"], "invalid protocol consumption")
    _require_exact_keys(
        consumption,
        {"recommendation_id", "request_id", "action_id", "reason_codes", "costs"},
        "invalid protocol consumption",
    )
    _require_pending_identifiers(consumption, state.pending_recommendation, "invalid protocol consumption")
    if (
        not isinstance(consumption["reason_codes"], list)
        or not consumption["reason_codes"]
        or not all(isinstance(code, str) and code.strip() for code in consumption["reason_codes"])
    ):
        raise RFBReplayError("invalid protocol consumption requires non-empty reason_codes")
    expected_cost = state.scenario.cost_model.invalid_protocol_costs
    if not _canonical_equal(consumption["costs"], expected_cost):
        raise RFBReplayError("invalid protocol costs do not match the frozen public cost model")
    _require_budget(state, expected_cost)
    _add_costs(state.cumulative_costs, expected_cost)
    state.pending_recommendation = None
    state.phase = AWAITING_RECOMMENDATION
    state.revision += 1


def _apply_execution_started(state: _ReplayState, payload: Any) -> None:
    if (
        state.phase != APPROVED
        or state.pending_recommendation is None
        or state.approved_decision is None
    ):
        raise RFBReplayError("execution_started requires an approved recommendation")
    data = _canonical_mapping(payload, "execution_started payload")
    _require_exact_keys(data, {"execution"}, "execution_started payload")
    execution = _canonical_mapping(data["execution"], "execution_started execution")
    _require_exact_keys(
        execution,
        {"decision_id", "recommendation_id", "request_id", "action_id", "action", "reserved_costs"},
        "execution_started execution",
    )
    _require_pending_identifiers(execution, state.pending_recommendation, "execution_started execution")
    if not _canonical_equal(execution["decision_id"], state.approved_decision["decision_id"]):
        raise RFBReplayError("execution_started decision does not match the persisted approval")
    action = _action_from(execution["action"], "execution_started action")
    if not _canonical_equal(action.to_dict(), state.pending_recommendation["action"]):
        raise RFBReplayError("execution_started action does not match the approved recommendation")
    expected_cost = state.scenario.cost_model.valid_execution_costs
    if not _canonical_equal(execution["reserved_costs"], expected_cost):
        raise RFBReplayError("execution reservation does not match the frozen public cost model")
    _require_budget(state, expected_cost)
    _add_costs(state.reserved_costs, expected_cost)
    state.phase = EXECUTING
    state.revision += 1


def _apply_execution_completed(
    state: _ReplayState, payload: Any, execution_decision_ids: set[str]
) -> None:
    if (
        state.phase != EXECUTING
        or state.pending_recommendation is None
        or state.approved_decision is None
    ):
        raise RFBReplayError("execution_completed requires an active approved execution")
    data = _canonical_mapping(payload, "execution_completed payload")
    _require_exact_keys(data, {"execution"}, "execution_completed payload")
    execution = _canonical_mapping(data["execution"], "execution_completed execution")
    _require_exact_keys(execution, _EXECUTION_FIELDS, "execution_completed execution")
    _require_pending_identifiers(execution, state.pending_recommendation, "execution_completed execution")
    decision_id = _nonempty_string(execution["decision_id"], "execution decision_id")
    if (
        not _canonical_equal(decision_id, state.approved_decision["decision_id"])
        or decision_id in execution_decision_ids
    ):
        raise RFBReplayError("execution completion does not match one active approval")
    action = _action_from(execution["action"], "execution completion action")
    if not _canonical_equal(action.to_dict(), state.pending_recommendation["action"]):
        raise RFBReplayError("execution completion action does not match the approved recommendation")
    outcome = _outcome_from(execution["outcome"], "execution outcome")
    expected_utility = utility_record_for_outcome(outcome, state.scenario.utility).to_dict()
    if not _canonical_equal(execution["utility_record"], expected_utility):
        raise RFBReplayError("execution utility record is not derived from the frozen utility")
    expected_cost = state.scenario.cost_model.valid_execution_costs
    if not _canonical_equal(execution["costs"], expected_cost) or not _canonical_equal(
        state.reserved_costs, _ledger_costs(expected_cost)
    ):
        raise RFBReplayError("execution completion cost does not match its reservation")
    _add_costs(state.cumulative_costs, expected_cost)
    _subtract_costs(state.reserved_costs, expected_cost)
    execution_decision_ids.add(decision_id)
    state.executions.append(execution)
    state.pending_recommendation = None
    state.approved_decision = None
    state.phase = AWAITING_RECOMMENDATION
    state.revision += 1


def _validated_recommendation(
    value: Any,
    state: _ReplayState,
    previous_event_sha256: str,
    recommendation_ids: set[str],
) -> dict[str, Any]:
    raw = _canonical_mapping(value, "recommendation")
    _require_exact_keys(raw, _RECOMMENDATION_FIELDS, "recommendation")
    try:
        recommendation = RFBRecommendationV1(
            action=_action_from(raw["action"], "recommendation action"),
            policy_id=raw["policy_id"],
            policy_version=raw["policy_version"],
            public_projection_sha256=raw["public_projection_sha256"],
            candidate_set_sha256=raw["candidate_set_sha256"],
            utility_sha256=raw["utility_sha256"],
            basis_event_head_sha256=raw["basis_event_head_sha256"],
            basis_revision=raw["basis_revision"],
            remaining_attempt_budget=raw["remaining_attempt_budget"],
            remaining_measurement_budget=raw["remaining_measurement_budget"],
            predicted_utility_mean=raw["predicted_utility_mean"],
            predicted_utility_std=raw["predicted_utility_std"],
            rationale=raw["rationale"],
            action_id=raw["action_id"],
            recommendation_id=raw["recommendation_id"],
            recommendation_sha256=raw["recommendation_sha256"],
            schema_version=raw["schema_version"],
        )
    except (TypeError, ValueError) as exc:
        raise RFBReplayError(f"recommendation is not canonical: {exc}") from exc
    serialized = recommendation.to_dict()
    if not _canonical_equal(raw, serialized):
        raise RFBReplayError("recommendation request/action fields are not canonical")
    if (
        recommendation.policy_id != state.policy_id
        or recommendation.policy_version != state.policy_version
        or recommendation.public_projection_sha256 != state.scenario.public_projection_sha256
        or recommendation.candidate_set_sha256 != state.scenario.candidate_set_sha256
        or recommendation.utility_sha256 != state.scenario.utility_sha256
        or recommendation.basis_event_head_sha256 != previous_event_sha256
        or recommendation.basis_revision != state.revision
        or recommendation.remaining_attempt_budget != state.remaining_budgets["attempts"]
        or recommendation.remaining_measurement_budget != state.remaining_budgets["measurements"]
        or not state.scenario.contains(recommendation.action)
    ):
        raise RFBReplayError("recommendation is not anchored to the current public campaign state")
    if recommendation.recommendation_id in recommendation_ids:
        raise RFBReplayError("recommendation ID is reused in the campaign journal")
    recommendation_ids.add(recommendation.recommendation_id)
    return serialized


def _validated_decision(
    value: Any,
    pending: Mapping[str, Any],
    decision_type: str,
    decision_ids: set[str],
) -> dict[str, Any]:
    decision = _canonical_mapping(value, "decision")
    expected = {"decision_id", "decision", "recommendation_id", "request_id", "action_id"}
    if decision_type in {"reject", "abort"}:
        expected.add("reason_code")
    if decision_type == "approve_with_edit":
        expected.add("edited_recommendation_id")
    _require_exact_keys(decision, expected, f"{decision_type} decision")
    if decision.get("decision") != decision_type:
        raise RFBReplayError("decision type does not match its event")
    decision_id = _nonempty_string(decision.get("decision_id"), "decision_id")
    if decision_id in decision_ids:
        raise RFBReplayError("decision ID is reused in the campaign journal")
    _require_pending_identifiers(decision, pending, f"{decision_type} decision")
    if decision_type in {"reject", "abort"}:
        _nonempty_string(decision.get("reason_code"), "decision reason_code")
    if decision_type == "approve_with_edit":
        _nonempty_string(decision.get("edited_recommendation_id"), "edited_recommendation_id")
    decision_ids.add(decision_id)
    return decision


def _require_pending_identifiers(
    value: Mapping[str, Any], pending: Mapping[str, Any], label: str
) -> None:
    expected = {
        "recommendation_id": pending["recommendation_id"],
        "request_id": pending["request"]["request_id"],
        "action_id": pending["action_id"],
    }
    for field, expected_value in expected.items():
        if not _canonical_equal(value.get(field), expected_value):
            raise RFBReplayError(f"{label} does not bind the current pending recommendation")


def _scenario_from_public_payload(value: Any) -> RFBScenarioV1:
    raw = _canonical_mapping(value, "public_scenario")
    _require_exact_keys(raw, _SCENARIO_FIELDS, "public_scenario")
    try:
        utility = FrozenScalarUtilityV1(
            energy_reference_J=raw["utility"]["energy_reference_J"],
            duration_reference_s=raw["utility"]["duration_reference_s"],
        )
        if not _canonical_equal(raw["utility"], utility.to_dict()):
            raise ValueError("utility definition does not match frozen RFB V1")
        cost_model = RFBPublicCostModelV1()
        if not _canonical_equal(raw["cost_model"], cost_model.to_dict()):
            raise ValueError("cost model does not match frozen RFB V1")
        scenario = RFBScenarioV1(
            scenario_id=raw["scenario_id"],
            scenario_version=raw["scenario_version"],
            candidate_actions=tuple(_action_from(item, "candidate action") for item in raw["candidate_actions"]),
            action_schema=RFBActionSchemaV1(raw["action_schema"]["ranges"]),
            fixed_fields=raw["fixed_fields"],
            ocv_50_soc_V=raw["ocv_50_soc_V"],
            utility=utility,
            total_attempt_budget=raw["total_attempt_budget"],
            total_measurement_budget=raw["total_measurement_budget"],
            cost_model=cost_model,
            provenance=raw["provenance"],
            model_dimension=raw["model_dimension"],
            domain_version=raw["domain_version"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RFBReplayError(f"public_scenario is not canonical: {exc}") from exc
    if not _canonical_equal(raw, scenario.to_dict()):
        raise RFBReplayError("public_scenario hashes or canonical fields do not match")
    return scenario


def _action_from(value: Any, label: str) -> RFBActionV1:
    if not isinstance(value, Mapping):
        raise RFBReplayError(f"{label} must be a canonical action mapping")
    try:
        return RFBActionV1.from_dict(value)
    except (TypeError, ValueError) as exc:
        raise RFBReplayError(f"{label} is not a canonical RFB action") from exc


def _outcome_from(value: Any, label: str) -> RFBOutcomeV1:
    raw = _canonical_mapping(value, label)
    expected = {
        "status",
        "delivered_discharge_energy_J",
        "round_trip_efficiency",
        "capacity_retention",
        "elapsed_duration_s",
        "qc_flags",
        "provenance",
    }
    _require_exact_keys(raw, expected, label)
    try:
        outcome = RFBOutcomeV1(
            status=raw["status"],
            delivered_discharge_energy_J=raw["delivered_discharge_energy_J"],
            round_trip_efficiency=raw["round_trip_efficiency"],
            capacity_retention=raw["capacity_retention"],
            elapsed_duration_s=raw["elapsed_duration_s"],
            qc_flags=tuple(raw["qc_flags"]),
            provenance=raw["provenance"],
        )
    except (TypeError, ValueError) as exc:
        raise RFBReplayError(f"{label} is not a canonical RFB outcome") from exc
    if not _canonical_equal(raw, outcome.to_dict()):
        raise RFBReplayError(f"{label} is not canonical")
    return outcome


def _verify_contract_event(event: dict[str, Any], sequence: int, previous: str) -> None:
    try:
        expected = build_rfb_campaign_event_v1(
            event_type=event["event_type"],
            payload=event["payload"],
            sequence=sequence,
            previous_event_sha256=previous,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RFBReplayError(f"event {sequence} does not satisfy rfb_campaign_event_v1") from exc
    # JSON bytes preserve distinctions such as ``false`` versus ``0`` that
    # Python's structural equality intentionally aliases.
    if not _canonical_equal(event, expected):
        raise RFBReplayError(f"event {sequence} canonical hash chain mismatch")
    if event["schema_version"] != RFB_CAMPAIGN_EVENT_SCHEMA_VERSION:
        raise RFBReplayError(f"event {sequence} has an unsupported schema version")


def _validate_terminal_state(value: Any, state: _ReplayState) -> None:
    campaign = _canonical_mapping(value, "terminal campaign state")
    _require_exact_keys(campaign, _CAMPAIGN_FIELDS, "terminal campaign state")
    if not _canonical_equal(campaign, state.to_campaign_dict()):
        raise RFBReplayError("terminal campaign state does not match the independently replayed journal")


def _require_budget(state: _ReplayState, costs: Mapping[str, Any]) -> None:
    delta = _ledger_costs(costs)
    remaining = state.remaining_budgets
    if delta["attempts"] > remaining["attempts"] or delta["measurements"] > remaining["measurements"]:
        raise RFBReplayError("campaign journal exceeds its public budget")


def _ledger_costs(costs: Mapping[str, Any]) -> dict[str, int]:
    if set(costs) != {"attempt_cost", "measurement_cost"}:
        raise RFBReplayError("cost record has an unsupported shape")
    result: dict[str, int] = {}
    for source, destination in (("attempt_cost", "attempts"), ("measurement_cost", "measurements")):
        value = costs[source]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RFBReplayError("cost record values must be non-negative integers")
        result[destination] = value
    return result


def _add_costs(target: dict[str, int], costs: Mapping[str, Any]) -> None:
    delta = _ledger_costs(costs)
    target["attempts"] += delta["attempts"]
    target["measurements"] += delta["measurements"]


def _subtract_costs(target: dict[str, int], costs: Mapping[str, Any]) -> None:
    delta = _ledger_costs(costs)
    target["attempts"] -= delta["attempts"]
    target["measurements"] -= delta["measurements"]
    if min(target.values()) < 0:
        raise RFBReplayError("execution completion would create a negative cost reservation")


def _canonical_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RFBReplayError(f"{label} must be a JSON object")
    try:
        normalized = canonical_json(value)
        copied = copy.deepcopy(value)
    except (TypeError, ValueError) as exc:
        raise RFBReplayError(f"{label} must be canonical JSON data") from exc
    if normalized != canonical_json(copied):
        raise RFBReplayError(f"{label} must be canonical JSON data")
    if not isinstance(copied, dict):
        return dict(copied)
    return copied


def _require_exact_keys(value: Mapping[str, Any], expected: set[str] | frozenset[str], label: str) -> None:
    if set(value) != set(expected):
        raise RFBReplayError(f"{label} fields do not match the RFB V1 contract")


def _require_equal(actual: Any, expected: Any, label: str) -> None:
    if not _canonical_equal(actual, expected):
        raise RFBReplayError(f"{label} mismatch")


def _canonical_equal(actual: Any, expected: Any) -> bool:
    """Compare public JSON by canonical bytes, including JSON scalar types."""

    try:
        return canonical_json(actual) == canonical_json(expected)
    except (TypeError, ValueError):
        return False


def _require_sha256(value: Any, label: str) -> None:
    if not (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    ):
        raise RFBReplayError(f"{label} must be a lowercase SHA-256 digest")


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RFBReplayError(f"{label} must be a non-empty string")
    return value.strip()


replay_rfb_campaign_v1 = replay_rfb_campaign_export_v1


__all__ = [
    "GENESIS_EVENT_SHA256",
    "RFBReplayError",
    "RFB_WORKFLOW_VERSION",
    "ReplayedRFBCampaignV1",
    "replay_rfb_campaign_export_v1",
    "replay_rfb_campaign_v1",
]
