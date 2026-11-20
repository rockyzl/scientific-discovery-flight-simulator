"""Durable public RFB campaign state and private execution leases.

The journal stores the public campaign state and the canonical event contract
verbatim.  Lease tokens, workers, timestamps, and execution identities are
private control-plane data: they never enter the exported state or event chain.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from discovery_flight_simulator.ledger import canonical_json, sha256_json

from .contracts import (
    FrozenScalarUtilityV1,
    RFBActionSchemaV1,
    RFBActionV1,
    RFBOutcomeV1,
    RFBPublicCostModelV1,
    RFBRecommendationV1,
    RFBScenarioV1,
    V1_VARYING_AXES,
    build_rfb_campaign_event_v1,
)
from .utility import utility_record_for_outcome

RFB_WORKFLOW_VERSION = "rfb_workflow_v1"
RFB_CAMPAIGN_STORE_SCHEMA_VERSION = "2"
_GENESIS_EVENT_SHA256 = "0" * 64

AWAITING_RECOMMENDATION = "awaiting_recommendation"
AWAITING_REVIEW = "awaiting_review"
APPROVED = "approved"
EXECUTING = "executing"
ABORTED = "aborted"
_PHASES = frozenset((AWAITING_RECOMMENDATION, AWAITING_REVIEW, APPROVED, EXECUTING, ABORTED))

STRICT_BENCHMARK = "strict_benchmark"
WORKFLOW_CASE_STUDY = "workflow_case_study"
# Kept as an import-compatible spelling; the public value is now the V1 mode.
HUMAN_INTERVENED = WORKFLOW_CASE_STUDY
_MODES = frozenset((STRICT_BENCHMARK, WORKFLOW_CASE_STUDY))


class RfbCampaignStoreError(RuntimeError):
    """Base class for durable RFB campaign-store failures."""


class CampaignNotFoundError(RfbCampaignStoreError):
    """Raised when the requested campaign does not exist."""


class CampaignAlreadyExistsError(RfbCampaignStoreError):
    """Raised when a campaign ID is reused."""


class RevisionConflictError(RfbCampaignStoreError):
    """Raised when a mutation was prepared from an obsolete campaign revision."""


class StaleRevisionError(RevisionConflictError):
    """Compatibility name for a stale optimistic-concurrency revision."""


class InvalidPhaseError(RfbCampaignStoreError):
    """Raised when an operation is not permitted in the current workflow phase."""


class NoPendingRecommendationError(InvalidPhaseError):
    """Raised when a human decision is attempted without a pending recommendation."""


class DuplicateResumeError(RfbCampaignStoreError):
    """Raised when a completed logical operation is resumed with new semantics."""


class ApprovalRequiredError(InvalidPhaseError):
    """Raised when execution is requested without its persisted approval."""


class ProtocolConsumptionError(RfbCampaignStoreError):
    """Raised when an invalid-protocol cost record is malformed."""


class BudgetExceededError(RfbCampaignStoreError):
    """Raised when consumption plus reservations would exceed a public budget."""


class ExecutionLeaseError(RfbCampaignStoreError):
    """Base class for execution lease failures."""


class StaleExecutionLeaseError(ExecutionLeaseError):
    """Raised when an expired or superseded worker attempts completion."""


class PrivateMaterialError(ValueError):
    """Raised when input intended for the public journal contains private material."""


class HashChainIntegrityError(RfbCampaignStoreError):
    """Raised when a persisted logical event or materialized state was tampered with."""


@dataclass(frozen=True)
class CampaignState:
    """The public, resumable state for one RFB campaign."""

    campaign_id: str
    revision: int
    phase: str
    policy_id: str
    policy_version: str
    public_scenario: dict[str, Any]
    pending_recommendation: dict[str, Any] | None
    decisions: tuple[dict[str, Any], ...]
    executions: tuple[dict[str, Any], ...]
    rejected_action_ids: tuple[str, ...]
    cumulative_costs: dict[str, int]
    reserved_costs: dict[str, int]
    mode: str
    comparison_eligible: bool
    human_intervened: bool
    approved_decision: dict[str, Any] | None
    workflow_version: str = RFB_WORKFLOW_VERSION

    @property
    def ranking_eligible(self) -> bool:
        return self.mode == STRICT_BENCHMARK and self.comparison_eligible and not self.human_intervened

    @property
    def remaining_budgets(self) -> dict[str, int]:
        return {
            "attempts": self.public_scenario["total_attempt_budget"]
            - self.cumulative_costs["attempts"]
            - self.reserved_costs["attempts"],
            "measurements": self.public_scenario["total_measurement_budget"]
            - self.cumulative_costs["measurements"]
            - self.reserved_costs["measurements"],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_version": self.workflow_version,
            "campaign_id": self.campaign_id,
            "revision": self.revision,
            "phase": self.phase,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "public_scenario": copy.deepcopy(self.public_scenario),
            "pending_recommendation": copy.deepcopy(self.pending_recommendation),
            "decisions": [copy.deepcopy(item) for item in self.decisions],
            "executions": [copy.deepcopy(item) for item in self.executions],
            "rejected_action_ids": list(self.rejected_action_ids),
            "cumulative_costs": dict(self.cumulative_costs),
            "reserved_costs": dict(self.reserved_costs),
            "mode": self.mode,
            "comparison_eligible": self.comparison_eligible,
            "human_intervened": self.human_intervened,
            "approved_decision": copy.deepcopy(self.approved_decision),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "CampaignState":
        expected = {
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
        if not isinstance(raw, Mapping) or set(raw) != expected:
            raise HashChainIntegrityError("campaign state has an unsupported shape")
        if raw["workflow_version"] != RFB_WORKFLOW_VERSION:
            raise HashChainIntegrityError("campaign state has an unsupported workflow version")
        try:
            scenario = _public_scenario_serialization(raw["public_scenario"])
        except ValueError as exc:
            raise HashChainIntegrityError("campaign state has an invalid public scenario") from exc
        pending = raw["pending_recommendation"]
        if pending is not None:
            try:
                pending = _recommendation_serialization(pending)
            except ValueError as exc:
                raise HashChainIntegrityError("campaign state has an invalid recommendation") from exc
        decisions = _mapping_list(raw["decisions"], "decisions")
        executions = _mapping_list(raw["executions"], "executions")
        rejected = raw["rejected_action_ids"]
        if not isinstance(rejected, list) or not all(_is_sha256(item) for item in rejected):
            raise HashChainIntegrityError("rejected_action_ids must be a list of action digests")
        cumulative = _costs(raw["cumulative_costs"], "cumulative_costs")
        reserved = _costs(raw["reserved_costs"], "reserved_costs")
        mode = raw["mode"]
        if mode not in _MODES:
            raise HashChainIntegrityError("campaign state has an unsupported mode")
        if not isinstance(raw["comparison_eligible"], bool) or not isinstance(raw["human_intervened"], bool):
            raise HashChainIntegrityError("campaign eligibility fields must be booleans")
        approved = raw["approved_decision"]
        if approved is not None:
            approved = _public_mapping(approved, "approved_decision")
        phase = raw["phase"]
        if phase not in _PHASES:
            raise HashChainIntegrityError("campaign state has an unsupported phase")
        state = cls(
            campaign_id=_nonempty_string(raw["campaign_id"], "campaign_id"),
            revision=_nonnegative_int(raw["revision"], "revision"),
            phase=phase,
            policy_id=_nonempty_string(raw["policy_id"], "policy_id"),
            policy_version=_nonempty_string(raw["policy_version"], "policy_version"),
            public_scenario=scenario,
            pending_recommendation=pending,
            decisions=tuple(decisions),
            executions=tuple(executions),
            rejected_action_ids=tuple(rejected),
            cumulative_costs=cumulative,
            reserved_costs=reserved,
            mode=mode,
            comparison_eligible=raw["comparison_eligible"],
            human_intervened=raw["human_intervened"],
            approved_decision=approved,
        )
        _validate_state_invariants(state)
        return state


@dataclass(frozen=True)
class CampaignJournalEvent:
    """One canonical public event with an un-hashed private audit timestamp."""

    event: dict[str, Any]
    audit_timestamp: str

    @property
    def sequence(self) -> int:
        return self.event["sequence"]

    @property
    def event_type(self) -> str:
        return self.event["event_type"]

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self.event["payload"])

    @property
    def previous_event_sha256(self) -> str:
        return self.event["previous_event_sha256"]

    @property
    def event_sha256(self) -> str:
        return self.event["event_sha256"]

    def to_dict(self) -> dict[str, Any]:
        """Return exactly the public contract event shape, without audit metadata."""

        return copy.deepcopy(self.event)


@dataclass(frozen=True)
class ExecutionLeaseClaim:
    """Private control-plane result of claiming a logical execution."""

    claimed: bool
    state: CampaignState
    action: dict[str, Any]
    lease_token: str | None = None
    lease_generation: int | None = None
    execution: dict[str, Any] | None = None

    @property
    def completed(self) -> bool:
        return self.execution is not None


class SQLiteRFBCampaignStore:
    """SQLite-backed public journal with private, renewable execution leases."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteRFBCampaignStore":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()

    def create_campaign(
        self,
        campaign_id: str,
        *,
        policy_id: str,
        policy_version: str,
        public_scenario: RFBScenarioV1 | Mapping[str, Any],
        mode: str = STRICT_BENCHMARK,
        audit_timestamp: str | None = None,
    ) -> CampaignState:
        """Persist the complete public scenario and create its canonical genesis event."""

        campaign_id = _nonempty_string(campaign_id, "campaign_id")
        policy_id = _nonempty_string(policy_id, "policy_id")
        policy_version = _nonempty_string(policy_version, "policy_version")
        if mode != STRICT_BENCHMARK:
            raise ValueError("new RFB campaigns must begin in strict_benchmark mode")
        scenario = _public_scenario_serialization(public_scenario)
        state = CampaignState(
            campaign_id=campaign_id,
            revision=0,
            phase=AWAITING_RECOMMENDATION,
            policy_id=policy_id,
            policy_version=policy_version,
            public_scenario=scenario,
            pending_recommendation=None,
            decisions=(),
            executions=(),
            rejected_action_ids=(),
            cumulative_costs={"attempts": 0, "measurements": 0},
            reserved_costs={"attempts": 0, "measurements": 0},
            mode=STRICT_BENCHMARK,
            comparison_eligible=True,
            human_intervened=False,
            approved_decision=None,
        )
        _validate_state_invariants(state)
        timestamp = _audit_timestamp(audit_timestamp)
        with self._transaction() as cursor:
            if cursor.execute("SELECT 1 FROM rfb_campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone():
                raise CampaignAlreadyExistsError(f"campaign already exists: {campaign_id}")
            self._insert_campaign(cursor, state, timestamp)
            self._append_event(
                cursor,
                state,
                event_type="campaign_created",
                payload={
                    "campaign_id": campaign_id,
                    "policy_id": policy_id,
                    "policy_version": policy_version,
                    "public_scenario": scenario,
                },
                audit_timestamp=timestamp,
            )
        return self.get_campaign(campaign_id)

    def get_campaign(self, campaign_id: str) -> CampaignState:
        campaign_id = _nonempty_string(campaign_id, "campaign_id")
        row = self._campaign_row(campaign_id)
        state = self._state_from_row(row)
        self._assert_integrity(row, state)
        return state

    def public_scenario(self, campaign_id: str) -> RFBScenarioV1:
        """Return the verified public scenario reconstructed from campaign state."""

        return _scenario_from_serialization(self.get_campaign(campaign_id).public_scenario)

    def save_recommendation(
        self,
        campaign_id: str,
        recommendation: RFBRecommendationV1 | Mapping[str, Any],
        *,
        expected_revision: int,
        recommendation_id: str | None = None,
        audit_timestamp: str | None = None,
    ) -> CampaignState:
        """Persist one full canonical recommendation anchored to the current public head."""

        normalized = _recommendation_serialization(recommendation)
        if recommendation_id is not None and recommendation_id != normalized["recommendation_id"]:
            raise ValueError("recommendation_id disagrees with canonical recommendation content")
        timestamp = _audit_timestamp(audit_timestamp)
        with self._transaction() as cursor:
            row, state = self._load_verified_campaign(cursor, campaign_id)
            self._require_revision(state, expected_revision)
            if state.phase != AWAITING_RECOMMENDATION:
                raise InvalidPhaseError(f"cannot save a recommendation while campaign phase is {state.phase!r}")
            self._validate_recommendation_provenance(row, state, normalized)
            self._require_new_recommendation_id(cursor, state.campaign_id, normalized["recommendation_id"])
            next_state = _replace_state(
                state,
                revision=state.revision + 1,
                phase=AWAITING_REVIEW,
                pending_recommendation=normalized,
            )
            self._write_transition(
                cursor,
                row,
                next_state,
                event_type="recommendation_saved",
                payload={"recommendation": normalized},
                audit_timestamp=timestamp,
            )
        return self.get_campaign(campaign_id)

    append_recommendation = save_recommendation

    def approve(
        self,
        campaign_id: str,
        *,
        decision_id: str,
        expected_revision: int,
        reviewer_id: str | None = None,
        audit_timestamp: str | None = None,
    ) -> CampaignState:
        """Record an unchanged approval; reviewer input remains private audit metadata."""

        del reviewer_id
        decision_id = _nonempty_string(decision_id, "decision_id")
        timestamp = _audit_timestamp(audit_timestamp)
        with self._transaction() as cursor:
            row, state = self._load_verified_campaign(cursor, campaign_id)
            self._require_new_decision_id(state, decision_id)
            self._require_revision(state, expected_revision)
            pending = self._require_pending_review(state)
            decision = _decision_record(decision_id, "approve", pending)
            next_state = _replace_state(
                state,
                revision=state.revision + 1,
                phase=APPROVED,
                decisions=(*state.decisions, decision),
                approved_decision=decision,
            )
            self._write_transition(
                cursor,
                row,
                next_state,
                event_type="approval_recorded",
                payload={"approval": decision},
                audit_timestamp=timestamp,
            )
        return self.get_campaign(campaign_id)

    def approve_with_edit(
        self,
        campaign_id: str,
        edited_recommendation: RFBRecommendationV1 | Mapping[str, Any],
        *,
        decision_id: str,
        expected_revision: int,
        recommendation_id: str | None = None,
        reviewer_id: str | None = None,
        audit_timestamp: str | None = None,
    ) -> CampaignState:
        """Record an explicit human edit and require a fresh approval of the new recommendation."""

        del reviewer_id
        decision_id = _nonempty_string(decision_id, "decision_id")
        edited = _recommendation_serialization(edited_recommendation)
        if recommendation_id is not None and recommendation_id != edited["recommendation_id"]:
            raise ValueError("recommendation_id disagrees with canonical recommendation content")
        timestamp = _audit_timestamp(audit_timestamp)
        with self._transaction() as cursor:
            row, state = self._load_verified_campaign(cursor, campaign_id)
            self._require_new_decision_id(state, decision_id)
            self._require_revision(state, expected_revision)
            pending = self._require_pending_review(state)
            self._validate_recommendation_provenance(row, state, edited)
            self._require_new_recommendation_id(cursor, state.campaign_id, edited["recommendation_id"])
            decision = _decision_record(
                decision_id,
                "approve_with_edit",
                pending,
                edited_recommendation_id=edited["recommendation_id"],
            )
            next_state = _replace_state(
                state,
                revision=state.revision + 1,
                pending_recommendation=edited,
                decisions=(*state.decisions, decision),
                mode=WORKFLOW_CASE_STUDY,
                comparison_eligible=False,
                human_intervened=True,
            )
            self._write_transition(
                cursor,
                row,
                next_state,
                event_type="intervention_recorded",
                payload={"intervention": decision, "recommendation": edited},
                audit_timestamp=timestamp,
            )
        return self.get_campaign(campaign_id)

    def reject(
        self,
        campaign_id: str,
        *,
        decision_id: str,
        reason_code: str,
        expected_revision: int,
        reviewer_id: str | None = None,
        audit_timestamp: str | None = None,
    ) -> CampaignState:
        """Reject the pending recommendation without any execution cost."""

        del reviewer_id
        decision_id = _nonempty_string(decision_id, "decision_id")
        reason_code = _nonempty_string(reason_code, "reason_code")
        timestamp = _audit_timestamp(audit_timestamp)
        with self._transaction() as cursor:
            row, state = self._load_verified_campaign(cursor, campaign_id)
            self._require_new_decision_id(state, decision_id)
            self._require_revision(state, expected_revision)
            pending = self._require_pending_review(state)
            decision = _decision_record(decision_id, "reject", pending, reason_code=reason_code)
            rejected_ids = tuple(dict.fromkeys((*state.rejected_action_ids, pending["action_id"])))
            next_state = _replace_state(
                state,
                revision=state.revision + 1,
                phase=AWAITING_RECOMMENDATION,
                pending_recommendation=None,
                decisions=(*state.decisions, decision),
                rejected_action_ids=rejected_ids,
                mode=WORKFLOW_CASE_STUDY,
                comparison_eligible=False,
                human_intervened=True,
            )
            self._write_transition(
                cursor,
                row,
                next_state,
                event_type="intervention_recorded",
                payload={"intervention": decision},
                audit_timestamp=timestamp,
            )
        return self.get_campaign(campaign_id)

    def abort(
        self,
        campaign_id: str,
        *,
        decision_id: str,
        reason_code: str,
        expected_revision: int,
        reviewer_id: str | None = None,
        audit_timestamp: str | None = None,
    ) -> CampaignState:
        """Abort from review and mark the campaign as a human case study."""

        del reviewer_id
        decision_id = _nonempty_string(decision_id, "decision_id")
        reason_code = _nonempty_string(reason_code, "reason_code")
        timestamp = _audit_timestamp(audit_timestamp)
        with self._transaction() as cursor:
            row, state = self._load_verified_campaign(cursor, campaign_id)
            self._require_new_decision_id(state, decision_id)
            self._require_revision(state, expected_revision)
            pending = self._require_pending_review(state)
            decision = _decision_record(decision_id, "abort", pending, reason_code=reason_code)
            next_state = _replace_state(
                state,
                revision=state.revision + 1,
                phase=ABORTED,
                pending_recommendation=None,
                decisions=(*state.decisions, decision),
                mode=WORKFLOW_CASE_STUDY,
                comparison_eligible=False,
                human_intervened=True,
            )
            self._write_transition(
                cursor,
                row,
                next_state,
                event_type="intervention_recorded",
                payload={"intervention": decision},
                audit_timestamp=timestamp,
            )
        return self.get_campaign(campaign_id)

    def record_decision(
        self,
        campaign_id: str,
        decision: str,
        *,
        decision_id: str,
        expected_revision: int,
        edited_recommendation: RFBRecommendationV1 | Mapping[str, Any] | None = None,
        recommendation_id: str | None = None,
        reason_code: str | None = None,
        reviewer_id: str | None = None,
        audit_timestamp: str | None = None,
    ) -> CampaignState:
        if decision == "approve":
            if edited_recommendation is not None or reason_code is not None:
                raise ValueError("approve does not accept an edit or reason_code")
            return self.approve(
                campaign_id,
                decision_id=decision_id,
                expected_revision=expected_revision,
                reviewer_id=reviewer_id,
                audit_timestamp=audit_timestamp,
            )
        if decision == "approve_with_edit":
            if edited_recommendation is None or reason_code is not None:
                raise ValueError("approve_with_edit requires exactly one edited recommendation")
            return self.approve_with_edit(
                campaign_id,
                edited_recommendation,
                decision_id=decision_id,
                expected_revision=expected_revision,
                recommendation_id=recommendation_id,
                reviewer_id=reviewer_id,
                audit_timestamp=audit_timestamp,
            )
        if decision == "reject":
            if reason_code is None or edited_recommendation is not None:
                raise ValueError("reject requires a reason_code and does not accept an edit")
            return self.reject(
                campaign_id,
                decision_id=decision_id,
                reason_code=reason_code,
                expected_revision=expected_revision,
                reviewer_id=reviewer_id,
                audit_timestamp=audit_timestamp,
            )
        if decision == "abort":
            if reason_code is None or edited_recommendation is not None:
                raise ValueError("abort requires a reason_code and does not accept an edit")
            return self.abort(
                campaign_id,
                decision_id=decision_id,
                reason_code=reason_code,
                expected_revision=expected_revision,
                reviewer_id=reviewer_id,
                audit_timestamp=audit_timestamp,
            )
        raise ValueError(f"unsupported RFB decision: {decision!r}")

    def record_invalid_protocol_consumption(
        self,
        campaign_id: str,
        *,
        expected_revision: int,
        reason_codes: Sequence[str],
        recommendation_id: str | None = None,
        attempt_cost: int = 1,
        measurement_cost: int = 0,
        audit_timestamp: str | None = None,
    ) -> CampaignState:
        """Charge the frozen invalid-protocol costs without approval or execution."""

        if attempt_cost != 1 or measurement_cost != 0:
            raise ProtocolConsumptionError("an invalid RFB protocol consumes exactly one attempt and zero measurements")
        if isinstance(reason_codes, (str, bytes)) or not isinstance(reason_codes, Sequence):
            raise ProtocolConsumptionError("reason_codes must be a non-empty sequence of strings")
        codes = tuple(_nonempty_string(code, "reason_code") for code in reason_codes)
        if not codes:
            raise ProtocolConsumptionError("reason_codes must be non-empty")
        timestamp = _audit_timestamp(audit_timestamp)
        with self._transaction() as cursor:
            row, state = self._load_verified_campaign(cursor, campaign_id)
            self._require_revision(state, expected_revision)
            pending = self._require_pending_review(state)
            if recommendation_id is not None and recommendation_id != pending["recommendation_id"]:
                raise NoPendingRecommendationError("invalid protocol record does not match pending recommendation")
            cost = _scenario_from_serialization(state.public_scenario).cost_model.invalid_protocol_costs
            _require_budget(state, cost)
            consumption = {
                "recommendation_id": pending["recommendation_id"],
                "request_id": pending["request"]["request_id"],
                "action_id": pending["action_id"],
                "reason_codes": list(codes),
                "costs": cost,
            }
            next_state = _replace_state(
                state,
                revision=state.revision + 1,
                phase=AWAITING_RECOMMENDATION,
                pending_recommendation=None,
                cumulative_costs=_add_costs(state.cumulative_costs, cost),
            )
            self._write_transition(
                cursor,
                row,
                next_state,
                event_type="invalid_protocol_consumed",
                payload={"consumption": consumption},
                audit_timestamp=timestamp,
            )
        return self.get_campaign(campaign_id)

    record_invalid_protocol = record_invalid_protocol_consumption

    def claim_execution(
        self,
        campaign_id: str,
        *,
        decision_id: str,
        expected_revision: int,
        execution_identity: Mapping[str, Any],
        lease_ttl_seconds: int = 300,
        now: str | None = None,
        audit_timestamp: str | None = None,
    ) -> ExecutionLeaseClaim:
        """Atomically claim or renew the single private lease for an approved action.

        A first claim emits one public ``execution_started`` event and reserves
        the public cost. Renewals after expiry only update private lease data.
        """

        decision_id = _nonempty_string(decision_id, "decision_id")
        ttl = _positive_int(lease_ttl_seconds, "lease_ttl_seconds")
        private_now = _lease_time(now)
        expiry = (private_now + timedelta(seconds=ttl)).isoformat()
        execution_identity_sha256 = _identity_sha256(execution_identity, "execution_identity")
        timestamp = _audit_timestamp(audit_timestamp)
        with self._transaction() as cursor:
            row, state = self._load_verified_campaign(cursor, campaign_id)
            existing_execution = _execution_for_decision(state, decision_id)
            if existing_execution is not None:
                return ExecutionLeaseClaim(
                    claimed=False,
                    state=state,
                    action=copy.deepcopy(existing_execution["action"]),
                    execution=existing_execution,
                )
            lease = cursor.execute(
                "SELECT * FROM rfb_execution_leases WHERE campaign_id = ? AND decision_id = ?",
                (state.campaign_id, decision_id),
            ).fetchone()
            if lease is not None:
                if lease["status"] == "completed":
                    raise HashChainIntegrityError("completed lease has no committed execution")
                if lease["status"] != "active":
                    raise HashChainIntegrityError("execution lease has an unsupported status")
                if state.phase != EXECUTING or state.approved_decision is None or state.pending_recommendation is None:
                    raise HashChainIntegrityError("active lease disagrees with campaign state")
                action = state.pending_recommendation["action"]
                if private_now < _lease_time(lease["lease_expires_at"]):
                    return ExecutionLeaseClaim(claimed=False, state=state, action=copy.deepcopy(action))
                generation = lease["generation"] + 1
                token = _lease_token(state, state.approved_decision, execution_identity_sha256)
                cursor.execute(
                    """
                    UPDATE rfb_execution_leases
                       SET execution_identity_sha256 = ?, lease_token = ?, generation = ?, lease_expires_at = ?
                     WHERE campaign_id = ? AND decision_id = ?
                    """,
                    (execution_identity_sha256, token, generation, expiry, state.campaign_id, decision_id),
                )
                return ExecutionLeaseClaim(
                    claimed=True,
                    state=state,
                    action=copy.deepcopy(action),
                    lease_token=token,
                    lease_generation=generation,
                )

            self._require_revision(state, expected_revision)
            if state.phase != APPROVED or state.approved_decision is None or state.pending_recommendation is None:
                raise ApprovalRequiredError("execution requires a persisted current approval")
            approved = state.approved_decision
            if approved["decision_id"] != decision_id:
                raise ApprovalRequiredError("execution decision ID does not match the current approval")
            scenario = _scenario_from_serialization(state.public_scenario)
            cost = scenario.cost_model.valid_execution_costs
            _require_budget(state, cost)
            token = _lease_token(state, approved, execution_identity_sha256)
            cursor.execute(
                """
                INSERT INTO rfb_execution_leases (
                    campaign_id, decision_id, recommendation_id, request_id, action_id,
                    execution_identity_sha256, lease_token, generation, status, lease_expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.campaign_id,
                    decision_id,
                    approved["recommendation_id"],
                    approved["request_id"],
                    approved["action_id"],
                    execution_identity_sha256,
                    token,
                    1,
                    "active",
                    expiry,
                ),
            )
            next_state = _replace_state(
                state,
                revision=state.revision + 1,
                phase=EXECUTING,
                reserved_costs=_add_costs(state.reserved_costs, cost),
            )
            execution_started = {
                "decision_id": decision_id,
                "recommendation_id": approved["recommendation_id"],
                "request_id": approved["request_id"],
                "action_id": approved["action_id"],
                "action": state.pending_recommendation["action"],
                "reserved_costs": cost,
            }
            self._write_transition(
                cursor,
                row,
                next_state,
                event_type="execution_started",
                payload={"execution": execution_started},
                audit_timestamp=timestamp,
            )
            return ExecutionLeaseClaim(
                claimed=True,
                state=next_state,
                action=copy.deepcopy(state.pending_recommendation["action"]),
                lease_token=token,
                lease_generation=1,
            )

    def release_execution_lease(
        self,
        campaign_id: str,
        *,
        decision_id: str,
        lease_token: str,
        lease_generation: int,
        now: str | None = None,
    ) -> bool:
        """Release an active private lease so a later claim can renew it without an event."""

        private_now = _lease_time(now).isoformat()
        with self._transaction() as cursor:
            _row, state = self._load_verified_campaign(cursor, campaign_id)
            lease = self._lease_for_completion(cursor, state, decision_id, lease_token, lease_generation)
            if lease["status"] == "completed":
                return False
            cursor.execute(
                """
                UPDATE rfb_execution_leases SET lease_expires_at = ?
                 WHERE campaign_id = ? AND decision_id = ?
                """,
                (private_now, state.campaign_id, decision_id),
            )
        return True

    def complete_execution(
        self,
        campaign_id: str,
        *,
        decision_id: str,
        action: RFBActionV1 | Mapping[str, Any],
        outcome: RFBOutcomeV1 | Mapping[str, Any],
        lease_token: str,
        lease_generation: int,
        audit_timestamp: str | None = None,
    ) -> dict[str, Any]:
        """Commit a lease result exactly once, converting its reservation to cost."""

        decision_id = _nonempty_string(decision_id, "decision_id")
        action_object = _action_from(action)
        outcome_object = _outcome_from(outcome)
        timestamp = _audit_timestamp(audit_timestamp)
        with self._transaction() as cursor:
            row, state = self._load_verified_campaign(cursor, campaign_id)
            lease = self._lease_for_completion(cursor, state, decision_id, lease_token, lease_generation)
            existing_execution = _execution_for_decision(state, decision_id)
            if lease["status"] == "completed":
                if existing_execution is None:
                    raise HashChainIntegrityError("completed lease has no committed execution")
                _require_matching_execution(existing_execution, action_object, outcome_object)
                return existing_execution
            if state.phase != EXECUTING or state.approved_decision is None or state.pending_recommendation is None:
                raise ApprovalRequiredError("execution completion requires an active approved lease")
            approved = state.approved_decision
            if approved["decision_id"] != decision_id or approved["action_id"] != action_object.identity_sha256:
                raise StaleExecutionLeaseError("execution completion does not match the approved action")
            if state.pending_recommendation["action_id"] != action_object.identity_sha256:
                raise StaleExecutionLeaseError("execution completion action does not match pending recommendation")
            scenario = _scenario_from_serialization(state.public_scenario)
            costs = scenario.cost_model.valid_execution_costs
            if state.reserved_costs != _model_costs(costs, "valid_execution_costs"):
                raise HashChainIntegrityError("active execution reservation does not match the public cost model")
            utility_record = utility_record_for_outcome(outcome_object, scenario.utility)
            execution = {
                "decision_id": decision_id,
                "recommendation_id": approved["recommendation_id"],
                "request_id": approved["request_id"],
                "action_id": action_object.identity_sha256,
                "action": action_object.to_dict(),
                "outcome": outcome_object.to_dict(),
                "utility_record": utility_record.to_dict(),
                "costs": costs,
            }
            next_state = _replace_state(
                state,
                revision=state.revision + 1,
                phase=AWAITING_RECOMMENDATION,
                pending_recommendation=None,
                executions=(*state.executions, execution),
                cumulative_costs=_add_costs(state.cumulative_costs, costs),
                reserved_costs=_subtract_costs(state.reserved_costs, costs),
                approved_decision=None,
            )
            cursor.execute(
                """
                UPDATE rfb_execution_leases SET status = 'completed', lease_expires_at = NULL
                 WHERE campaign_id = ? AND decision_id = ?
                """,
                (state.campaign_id, decision_id),
            )
            self._write_transition(
                cursor,
                row,
                next_state,
                event_type="execution_completed",
                payload={"execution": execution},
                audit_timestamp=timestamp,
            )
        return copy.deepcopy(execution)

    def events(self, campaign_id: str) -> tuple[CampaignJournalEvent, ...]:
        campaign_id = _nonempty_string(campaign_id, "campaign_id")
        row = self._campaign_row(campaign_id)
        state = self._state_from_row(row)
        return tuple(self._assert_integrity(row, state))

    def export_campaign(self, campaign_id: str) -> dict[str, Any]:
        """Export public state and contract events, excluding all private lease metadata."""

        campaign_id = _nonempty_string(campaign_id, "campaign_id")
        row = self._campaign_row(campaign_id)
        state = self._state_from_row(row)
        events = self._assert_integrity(row, state)
        exported = {
            "workflow_version": RFB_WORKFLOW_VERSION,
            "campaign": state.to_dict(),
            "event_head_sha256": row["head_event_sha256"],
            "events": [event.to_dict() for event in events],
        }
        _assert_no_private_material(exported, "public export")
        return exported

    def verify_campaign(self, campaign_id: str) -> bool:
        self.get_campaign(campaign_id)
        return True

    def _initialize(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rfb_campaign_store_meta (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version TEXT NOT NULL
                )
                """
            )
            row = self._connection.execute(
                "SELECT schema_version FROM rfb_campaign_store_meta WHERE singleton = 1"
            ).fetchone()
            if row is None:
                self._connection.execute(
                    "INSERT INTO rfb_campaign_store_meta (singleton, schema_version) VALUES (1, ?)",
                    (RFB_CAMPAIGN_STORE_SCHEMA_VERSION,),
                )
            elif row["schema_version"] != RFB_CAMPAIGN_STORE_SCHEMA_VERSION:
                raise RfbCampaignStoreError("unsupported RFB campaign-store schema version")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rfb_campaigns (
                    campaign_id TEXT PRIMARY KEY,
                    workflow_version TEXT NOT NULL,
                    policy_id TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    public_scenario_json TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    pending_recommendation_json TEXT,
                    decisions_json TEXT NOT NULL,
                    executions_json TEXT NOT NULL,
                    rejected_action_ids_json TEXT NOT NULL,
                    cumulative_costs_json TEXT NOT NULL,
                    reserved_costs_json TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    comparison_eligible INTEGER NOT NULL,
                    human_intervened INTEGER NOT NULL,
                    approved_decision_json TEXT,
                    state_json TEXT NOT NULL,
                    event_count INTEGER NOT NULL,
                    head_event_sha256 TEXT NOT NULL,
                    created_audit_timestamp TEXT NOT NULL,
                    updated_audit_timestamp TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rfb_campaign_events (
                    campaign_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    event_sha256 TEXT NOT NULL,
                    audit_timestamp TEXT NOT NULL,
                    PRIMARY KEY (campaign_id, sequence),
                    FOREIGN KEY (campaign_id) REFERENCES rfb_campaigns (campaign_id)
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rfb_execution_leases (
                    campaign_id TEXT NOT NULL,
                    decision_id TEXT NOT NULL,
                    recommendation_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    execution_identity_sha256 TEXT NOT NULL,
                    lease_token TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    lease_expires_at TEXT,
                    PRIMARY KEY (campaign_id, decision_id),
                    FOREIGN KEY (campaign_id) REFERENCES rfb_campaigns (campaign_id)
                )
                """
            )
            self._connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS rfb_one_active_execution_lease
                    ON rfb_execution_leases (campaign_id)
                 WHERE status = 'active'
                """
            )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Cursor]:
        cursor = self._connection.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            yield cursor
        except Exception:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    def _insert_campaign(self, cursor: sqlite3.Cursor, state: CampaignState, timestamp: str) -> None:
        columns = _state_columns(state)
        cursor.execute(
            """
            INSERT INTO rfb_campaigns (
                campaign_id, workflow_version, policy_id, policy_version, public_scenario_json,
                revision, phase, pending_recommendation_json, decisions_json, executions_json,
                rejected_action_ids_json, cumulative_costs_json, reserved_costs_json, mode,
                comparison_eligible, human_intervened, approved_decision_json, state_json,
                event_count, head_event_sha256, created_audit_timestamp, updated_audit_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state.campaign_id,
                *columns,
                0,
                _GENESIS_EVENT_SHA256,
                timestamp,
                timestamp,
            ),
        )

    def _write_transition(
        self,
        cursor: sqlite3.Cursor,
        row: sqlite3.Row,
        state: CampaignState,
        *,
        event_type: str,
        payload: Mapping[str, Any],
        audit_timestamp: str,
    ) -> None:
        _validate_state_invariants(state)
        self._update_materialized_state(cursor, state, audit_timestamp)
        self._append_event(
            cursor,
            state,
            event_type=event_type,
            payload=payload,
            audit_timestamp=audit_timestamp,
            previous_event_sha256=row["head_event_sha256"],
            sequence=row["event_count"],
        )

    def _update_materialized_state(
        self, cursor: sqlite3.Cursor, state: CampaignState, audit_timestamp: str
    ) -> None:
        columns = _state_columns(state)
        cursor.execute(
            """
            UPDATE rfb_campaigns
               SET workflow_version = ?, policy_id = ?, policy_version = ?, public_scenario_json = ?,
                   revision = ?, phase = ?, pending_recommendation_json = ?, decisions_json = ?,
                   executions_json = ?, rejected_action_ids_json = ?, cumulative_costs_json = ?,
                   reserved_costs_json = ?, mode = ?, comparison_eligible = ?, human_intervened = ?,
                   approved_decision_json = ?, state_json = ?, updated_audit_timestamp = ?
             WHERE campaign_id = ?
            """,
            (*columns, audit_timestamp, state.campaign_id),
        )
        if cursor.rowcount != 1:
            raise CampaignNotFoundError(f"campaign not found: {state.campaign_id}")

    def _append_event(
        self,
        cursor: sqlite3.Cursor,
        state: CampaignState,
        *,
        event_type: str,
        payload: Mapping[str, Any],
        audit_timestamp: str,
        previous_event_sha256: str = _GENESIS_EVENT_SHA256,
        sequence: int = 0,
    ) -> None:
        event = build_rfb_campaign_event_v1(
            event_type=event_type,
            payload=_public_mapping(payload, "event payload"),
            sequence=sequence,
            previous_event_sha256=previous_event_sha256,
        )
        cursor.execute(
            """
            INSERT INTO rfb_campaign_events (
                campaign_id, sequence, event_type, event_json, event_sha256, audit_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                state.campaign_id,
                sequence,
                event_type,
                canonical_json(event),
                event["event_sha256"],
                audit_timestamp,
            ),
        )
        cursor.execute(
            """
            UPDATE rfb_campaigns SET event_count = ?, head_event_sha256 = ? WHERE campaign_id = ?
            """,
            (sequence + 1, event["event_sha256"], state.campaign_id),
        )

    def _campaign_row(self, campaign_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM rfb_campaigns WHERE campaign_id = ?", (campaign_id,)
        ).fetchone()
        if row is None:
            raise CampaignNotFoundError(f"campaign not found: {campaign_id}")
        return row

    def _load_verified_campaign(
        self, cursor: sqlite3.Cursor, campaign_id: str
    ) -> tuple[sqlite3.Row, CampaignState]:
        campaign_id = _nonempty_string(campaign_id, "campaign_id")
        row = cursor.execute("SELECT * FROM rfb_campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone()
        if row is None:
            raise CampaignNotFoundError(f"campaign not found: {campaign_id}")
        state = self._state_from_row(row)
        self._assert_integrity(row, state, cursor=cursor)
        return row, state

    def _state_from_row(self, row: sqlite3.Row) -> CampaignState:
        try:
            raw = json.loads(row["state_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise HashChainIntegrityError("campaign materialized state is not valid JSON") from exc
        if canonical_json(raw) != row["state_json"]:
            raise HashChainIntegrityError("campaign materialized state is not canonical JSON")
        state = CampaignState.from_dict(raw)
        if state.campaign_id != row["campaign_id"]:
            raise HashChainIntegrityError("campaign ID disagrees with materialized state")
        if tuple(_state_columns(state)) != _row_state_columns(row):
            raise HashChainIntegrityError("campaign materialized columns disagree with state snapshot")
        return state

    def _assert_integrity(
        self,
        row: sqlite3.Row,
        state: CampaignState,
        *,
        cursor: sqlite3.Cursor | None = None,
    ) -> list[CampaignJournalEvent]:
        if row["workflow_version"] != RFB_WORKFLOW_VERSION:
            raise HashChainIntegrityError("campaign uses an unsupported workflow version")
        rows = (cursor or self._connection).execute(
            "SELECT * FROM rfb_campaign_events WHERE campaign_id = ? ORDER BY sequence", (state.campaign_id,)
        ).fetchall()
        if len(rows) != row["event_count"]:
            raise HashChainIntegrityError("campaign event count does not match its journal")
        previous = _GENESIS_EVENT_SHA256
        events: list[CampaignJournalEvent] = []
        for sequence, event_row in enumerate(rows):
            if event_row["sequence"] != sequence:
                raise HashChainIntegrityError("campaign event sequence is discontinuous")
            try:
                event = json.loads(event_row["event_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise HashChainIntegrityError("campaign event is not valid JSON") from exc
            if canonical_json(event) != event_row["event_json"]:
                raise HashChainIntegrityError("campaign event is not canonical JSON")
            try:
                expected = build_rfb_campaign_event_v1(
                    event_type=event_row["event_type"],
                    payload=event["payload"],
                    sequence=sequence,
                    previous_event_sha256=previous,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise HashChainIntegrityError("campaign event has an unsupported shape") from exc
            if event != expected or event_row["event_sha256"] != event["event_sha256"]:
                raise HashChainIntegrityError("campaign event hash chain mismatch")
            events.append(CampaignJournalEvent(event=event, audit_timestamp=event_row["audit_timestamp"]))
            previous = event["event_sha256"]
        if not events:
            raise HashChainIntegrityError("campaign journal is missing its genesis event")
        if previous != row["head_event_sha256"]:
            raise HashChainIntegrityError("campaign head hash does not match its journal")
        return events

    @staticmethod
    def _require_revision(state: CampaignState, expected_revision: int) -> None:
        expected = _nonnegative_int(expected_revision, "expected_revision")
        if expected != state.revision:
            raise StaleRevisionError(f"stale campaign revision: expected {expected}, current {state.revision}")

    @staticmethod
    def _require_pending_review(state: CampaignState) -> dict[str, Any]:
        if state.phase != AWAITING_REVIEW or state.pending_recommendation is None:
            raise NoPendingRecommendationError("a current recommendation in awaiting_review is required")
        return copy.deepcopy(state.pending_recommendation)

    @staticmethod
    def _require_new_decision_id(state: CampaignState, decision_id: str) -> None:
        if any(decision.get("decision_id") == decision_id for decision in state.decisions):
            raise DuplicateResumeError(f"decision ID has already been consumed: {decision_id}")

    def _require_new_recommendation_id(
        self, cursor: sqlite3.Cursor, campaign_id: str, recommendation_id: str
    ) -> None:
        for event_row in cursor.execute(
            "SELECT event_json FROM rfb_campaign_events WHERE campaign_id = ?", (campaign_id,)
        ):
            payload = json.loads(event_row["event_json"])["payload"]
            for value in (payload.get("recommendation"),):
                if isinstance(value, Mapping) and value.get("recommendation_id") == recommendation_id:
                    raise DuplicateResumeError(f"recommendation ID has already been persisted: {recommendation_id}")

    @staticmethod
    def _validate_recommendation_provenance(
        row: sqlite3.Row, state: CampaignState, recommendation: Mapping[str, Any]
    ) -> None:
        scenario = _scenario_from_serialization(state.public_scenario)
        expected = {
            "policy_id": state.policy_id,
            "policy_version": state.policy_version,
            "public_projection_sha256": scenario.public_projection_sha256,
            "candidate_set_sha256": scenario.candidate_set_sha256,
            "utility_sha256": scenario.utility_sha256,
            "basis_event_head_sha256": row["head_event_sha256"],
            "basis_revision": state.revision,
            "remaining_attempt_budget": state.remaining_budgets["attempts"],
            "remaining_measurement_budget": state.remaining_budgets["measurements"],
        }
        for name, value in expected.items():
            if recommendation[name] != value:
                raise ValueError(f"recommendation {name} does not match the current public campaign state")
        action = _action_from(recommendation["action"])
        if not scenario.contains(action):
            raise ValueError("recommendation action is not a member of the public candidate set")
        request = recommendation["request"]
        if request["request_id"] != recommendation["recommendation_id"]:
            raise ValueError("recommendation request_id must equal recommendation_id")
        if request["action"] != action.to_dict() or recommendation["action_id"] != action.identity_sha256:
            raise ValueError("recommendation action/request identifiers do not match canonical action content")

    @staticmethod
    def _lease_for_completion(
        cursor: sqlite3.Cursor,
        state: CampaignState,
        decision_id: str,
        lease_token: str,
        lease_generation: int,
    ) -> sqlite3.Row:
        if not _is_sha256(lease_token):
            raise StaleExecutionLeaseError("lease token is invalid")
        generation = _positive_int(lease_generation, "lease_generation")
        lease = cursor.execute(
            "SELECT * FROM rfb_execution_leases WHERE campaign_id = ? AND decision_id = ?",
            (state.campaign_id, decision_id),
        ).fetchone()
        if lease is None:
            raise StaleExecutionLeaseError("execution lease does not exist")
        if lease["lease_token"] != lease_token or lease["generation"] != generation:
            raise StaleExecutionLeaseError("execution lease was superseded by another worker")
        return lease


RFBCampaignStore = SQLiteRFBCampaignStore
RFBWorkflowStore = SQLiteRFBCampaignStore


def _replace_state(state: CampaignState, **changes: Any) -> CampaignState:
    values = state.to_dict()
    values.update(changes)
    values.pop("workflow_version")
    return CampaignState(**values)


def _state_json(state: CampaignState) -> str:
    return canonical_json(state.to_dict())


def _state_columns(state: CampaignState) -> tuple[Any, ...]:
    return (
        RFB_WORKFLOW_VERSION,
        state.policy_id,
        state.policy_version,
        canonical_json(state.public_scenario),
        state.revision,
        state.phase,
        _json_or_none(state.pending_recommendation),
        canonical_json(list(state.decisions)),
        canonical_json(list(state.executions)),
        canonical_json(list(state.rejected_action_ids)),
        canonical_json(state.cumulative_costs),
        canonical_json(state.reserved_costs),
        state.mode,
        int(state.comparison_eligible),
        int(state.human_intervened),
        _json_or_none(state.approved_decision),
        _state_json(state),
    )


def _row_state_columns(row: sqlite3.Row) -> tuple[Any, ...]:
    return (
        row["workflow_version"],
        row["policy_id"],
        row["policy_version"],
        row["public_scenario_json"],
        row["revision"],
        row["phase"],
        row["pending_recommendation_json"],
        row["decisions_json"],
        row["executions_json"],
        row["rejected_action_ids_json"],
        row["cumulative_costs_json"],
        row["reserved_costs_json"],
        row["mode"],
        row["comparison_eligible"],
        row["human_intervened"],
        row["approved_decision_json"],
        row["state_json"],
    )


def _json_or_none(value: Any) -> str | None:
    return None if value is None else canonical_json(value)


def _public_scenario_serialization(value: RFBScenarioV1 | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, RFBScenarioV1):
        raw = value.to_dict()
    else:
        raw = _public_mapping(value, "public_scenario")
    scenario = _scenario_from_serialization(raw)
    serialized = scenario.to_dict()
    if raw != serialized:
        raise ValueError("public_scenario is not the complete canonical RFBScenarioV1 serialization")
    return serialized


def _scenario_from_serialization(raw: Mapping[str, Any]) -> RFBScenarioV1:
    normalized = _public_mapping(raw, "public_scenario")
    expected = {
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
    if set(normalized) != expected:
        raise ValueError("public_scenario does not have the complete canonical RFBScenarioV1 shape")
    if normalized["action_schema"].keys() != {"ranges"}:
        raise ValueError("public_scenario action_schema is malformed")
    if normalized["fixed_action_values"] != normalized["fixed_fields"]:
        raise ValueError("public_scenario fixed action values disagree")
    if normalized["varying_axes"] != list(V1_VARYING_AXES):
        raise ValueError("public_scenario varying axes disagree with RFB V1")
    utility_raw = normalized["utility"]
    if not isinstance(utility_raw, Mapping):
        raise ValueError("public_scenario utility is malformed")
    utility = FrozenScalarUtilityV1(
        energy_reference_J=utility_raw.get("energy_reference_J"),
        duration_reference_s=utility_raw.get("duration_reference_s"),
    )
    cost_raw = normalized["cost_model"]
    cost_model = RFBPublicCostModelV1()
    if cost_raw != cost_model.to_dict():
        raise ValueError("public_scenario cost model does not match the frozen RFB V1 model")
    actions_raw = normalized["candidate_actions"]
    if not isinstance(actions_raw, list):
        raise ValueError("public_scenario candidate_actions must be a list")
    scenario = RFBScenarioV1(
        scenario_id=normalized["scenario_id"],
        scenario_version=normalized["scenario_version"],
        candidate_actions=tuple(_action_from(item) for item in actions_raw),
        action_schema=RFBActionSchemaV1(normalized["action_schema"]["ranges"]),
        fixed_fields=normalized["fixed_fields"],
        ocv_50_soc_V=normalized["ocv_50_soc_V"],
        utility=utility,
        total_attempt_budget=normalized["total_attempt_budget"],
        total_measurement_budget=normalized["total_measurement_budget"],
        cost_model=cost_model,
        provenance=normalized["provenance"],
        model_dimension=normalized["model_dimension"],
        domain_version=normalized["domain_version"],
    )
    if scenario.to_dict() != normalized:
        raise ValueError("public_scenario hash, utility, cost model, or budget verification failed")
    return scenario


def _recommendation_serialization(value: RFBRecommendationV1 | Mapping[str, Any]) -> dict[str, Any]:
    raw = value.to_dict() if isinstance(value, RFBRecommendationV1) else _public_mapping(value, "recommendation")
    expected = {
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
    if set(raw) != expected:
        raise ValueError("recommendation must have the complete canonical RFBRecommendationV1 shape")
    recommendation = RFBRecommendationV1(
        action=_action_from(raw["action"]),
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
    serialized = recommendation.to_dict()
    if raw != serialized:
        raise ValueError("recommendation request/action fields do not match canonical content")
    return serialized


def _action_from(value: RFBActionV1 | Mapping[str, Any]) -> RFBActionV1:
    if isinstance(value, RFBActionV1):
        return value
    if isinstance(value, Mapping):
        return RFBActionV1.from_dict(value)
    raise ValueError("action must be an RFBActionV1 or canonical action mapping")


def _outcome_from(value: RFBOutcomeV1 | Mapping[str, Any]) -> RFBOutcomeV1:
    if isinstance(value, RFBOutcomeV1):
        return value
    if not isinstance(value, Mapping):
        raise ValueError("outcome must be an RFBOutcomeV1 or canonical outcome mapping")
    expected = {
        "status",
        "delivered_discharge_energy_J",
        "round_trip_efficiency",
        "capacity_retention",
        "elapsed_duration_s",
        "qc_flags",
        "provenance",
    }
    if set(value) != expected:
        raise ValueError("outcome must contain complete canonical RFB outcome fields")
    return RFBOutcomeV1(
        status=value["status"],
        delivered_discharge_energy_J=value["delivered_discharge_energy_J"],
        round_trip_efficiency=value["round_trip_efficiency"],
        capacity_retention=value["capacity_retention"],
        elapsed_duration_s=value["elapsed_duration_s"],
        qc_flags=tuple(value["qc_flags"]),
        provenance=value["provenance"],
    )


def _validate_state_invariants(state: CampaignState) -> None:
    scenario = _scenario_from_serialization(state.public_scenario)
    if state.policy_id != _nonempty_string(state.policy_id, "policy_id"):
        raise HashChainIntegrityError("campaign policy_id is invalid")
    if state.mode == WORKFLOW_CASE_STUDY and (state.comparison_eligible or not state.human_intervened):
        raise HashChainIntegrityError("human case studies must be unrankable")
    if state.human_intervened and state.mode != WORKFLOW_CASE_STUDY:
        raise HashChainIntegrityError("human intervention must use workflow_case_study mode")
    for name, total in (
        ("attempts", scenario.total_attempt_budget),
        ("measurements", scenario.total_measurement_budget),
    ):
        if state.cumulative_costs[name] + state.reserved_costs[name] > total:
            raise HashChainIntegrityError("consumed and reserved costs exceed the public scenario budget")
    if state.phase == AWAITING_RECOMMENDATION:
        if state.pending_recommendation is not None or state.approved_decision is not None or any(state.reserved_costs.values()):
            raise HashChainIntegrityError("awaiting_recommendation may not retain a pending approval or reservation")
    elif state.phase == AWAITING_REVIEW:
        if state.pending_recommendation is None or state.approved_decision is not None or any(state.reserved_costs.values()):
            raise HashChainIntegrityError("awaiting_review requires only one pending recommendation")
    elif state.phase == APPROVED:
        if state.pending_recommendation is None or state.approved_decision is None or any(state.reserved_costs.values()):
            raise HashChainIntegrityError("approved requires a pending recommendation and no reservation")
    elif state.phase == EXECUTING:
        if state.pending_recommendation is None or state.approved_decision is None:
            raise HashChainIntegrityError("executing requires the approved recommendation")
        expected_reservation = _model_costs(
            scenario.cost_model.valid_execution_costs,
            "valid_execution_costs",
        )
        if state.reserved_costs != expected_reservation:
            raise HashChainIntegrityError("executing must reserve exactly the public execution costs")
    elif state.phase == ABORTED:
        if state.pending_recommendation is not None or state.approved_decision is not None or any(state.reserved_costs.values()):
            raise HashChainIntegrityError("aborted campaigns may not retain pending execution state")
    if state.pending_recommendation is not None:
        _recommendation_serialization(state.pending_recommendation)
    if state.approved_decision is not None and state.pending_recommendation is not None:
        for key in ("recommendation_id", "request_id", "action_id"):
            pending_value = (
                state.pending_recommendation["request"]["request_id"]
                if key == "request_id"
                else state.pending_recommendation[key]
            )
            if state.approved_decision.get(key) != pending_value:
                raise HashChainIntegrityError("approved decision does not match the pending recommendation")
    seen_decisions: set[str] = set()
    for decision in state.decisions:
        decision_id = decision.get("decision_id")
        if not isinstance(decision_id, str) or not decision_id or decision_id in seen_decisions:
            raise HashChainIntegrityError("decision records must have unique public decision IDs")
        seen_decisions.add(decision_id)
    seen_executions: set[str] = set()
    for execution in state.executions:
        _validate_execution_record(execution, scenario)
        decision_id = execution["decision_id"]
        if decision_id in seen_executions:
            raise HashChainIntegrityError("execution records must have unique decision IDs")
        seen_executions.add(decision_id)


def _validate_execution_record(execution: Mapping[str, Any], scenario: RFBScenarioV1) -> None:
    expected = {
        "decision_id",
        "recommendation_id",
        "request_id",
        "action_id",
        "action",
        "outcome",
        "utility_record",
        "costs",
    }
    if set(execution) != expected:
        raise HashChainIntegrityError("execution record has an unsupported shape")
    action = _action_from(execution["action"])
    if execution["action_id"] != action.identity_sha256 or not scenario.contains(action):
        raise HashChainIntegrityError("execution record action is not a public candidate")
    outcome = _outcome_from(execution["outcome"])
    expected_record = utility_record_for_outcome(outcome, scenario.utility).to_dict()
    if execution["utility_record"] != expected_record:
        raise HashChainIntegrityError("execution utility record is not canonical for its outcome")
    if execution["costs"] != scenario.cost_model.valid_execution_costs:
        raise HashChainIntegrityError("execution costs do not match the public cost model")


def _costs(value: Any, name: str) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != {"attempts", "measurements"}:
        raise HashChainIntegrityError(f"{name} has an unsupported shape")
    return {
        "attempts": _nonnegative_int(value["attempts"], f"{name}.attempts"),
        "measurements": _nonnegative_int(value["measurements"], f"{name}.measurements"),
    }


def _model_costs(value: Any, name: str) -> dict[str, int]:
    """Translate public cost-model fields into ledger accounting keys."""

    if not isinstance(value, Mapping) or set(value) != {"attempt_cost", "measurement_cost"}:
        raise HashChainIntegrityError(f"{name} has an unsupported shape")
    return {
        "attempts": _nonnegative_int(value["attempt_cost"], f"{name}.attempt_cost"),
        "measurements": _nonnegative_int(
            value["measurement_cost"], f"{name}.measurement_cost"
        ),
    }


def _add_costs(current: Mapping[str, int], delta: Mapping[str, int]) -> dict[str, int]:
    return {"attempts": current["attempts"] + delta["attempt_cost"], "measurements": current["measurements"] + delta["measurement_cost"]}


def _subtract_costs(current: Mapping[str, int], delta: Mapping[str, int]) -> dict[str, int]:
    result = {"attempts": current["attempts"] - delta["attempt_cost"], "measurements": current["measurements"] - delta["measurement_cost"]}
    if min(result.values()) < 0:
        raise HashChainIntegrityError("execution completion would create a negative reservation")
    return result


def _require_budget(state: CampaignState, costs: Mapping[str, int]) -> None:
    remaining = state.remaining_budgets
    if costs["attempt_cost"] > remaining["attempts"] or costs["measurement_cost"] > remaining["measurements"]:
        raise BudgetExceededError("public attempt or measurement budget is exhausted")


def _decision_record(
    decision_id: str,
    decision_type: str,
    pending: Mapping[str, Any],
    *,
    reason_code: str | None = None,
    edited_recommendation_id: str | None = None,
) -> dict[str, Any]:
    record = {
        "decision_id": decision_id,
        "decision": decision_type,
        "recommendation_id": pending["recommendation_id"],
        "request_id": pending["request"]["request_id"],
        "action_id": pending["action_id"],
    }
    if reason_code is not None:
        record["reason_code"] = reason_code
    if edited_recommendation_id is not None:
        record["edited_recommendation_id"] = edited_recommendation_id
    return record


def _execution_for_decision(state: CampaignState, decision_id: str) -> dict[str, Any] | None:
    for execution in state.executions:
        if execution.get("decision_id") == decision_id:
            return copy.deepcopy(execution)
    return None


def _require_matching_execution(
    execution: Mapping[str, Any], action: RFBActionV1, outcome: RFBOutcomeV1
) -> None:
    if execution["action_id"] != action.identity_sha256 or execution["outcome"] != outcome.to_dict():
        raise DuplicateResumeError("completed execution does not match the supplied action and outcome")


def _lease_token(
    state: CampaignState, approved: Mapping[str, Any], execution_identity_sha256: str
) -> str:
    return sha256_json(
        {
            "campaign_id": state.campaign_id,
            "decision_id": approved["decision_id"],
            "recommendation_id": approved["recommendation_id"],
            "request_id": approved["request_id"],
            "action_id": approved["action_id"],
            "scenario_public_identity": state.public_scenario["public_projection_sha256"],
            "execution_identity_sha256": execution_identity_sha256,
            "utility_sha256": state.pending_recommendation["utility_sha256"],
        }
    )


def _identity_sha256(value: Mapping[str, Any], name: str) -> str:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    try:
        return sha256_json(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be canonical JSON-compatible data") from exc


def _mapping_list(value: Any, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise HashChainIntegrityError(f"{name} must be a list of mappings")
    return [_public_mapping(item, name) for item in value]


def _public_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    try:
        normalized = json.loads(canonical_json(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be canonical JSON-compatible data") from exc
    if not isinstance(normalized, dict):
        raise ValueError(f"{name} must be a JSON object")
    _assert_no_private_material(normalized, name)
    return normalized


def _assert_no_private_material(value: Any, context: str) -> None:
    """Fail closed on private config and control-plane material in public data."""

    prohibited_exact = {
        "private",
        "private_config",
        "oracle_config",
        "execution_oracle_spec",
        "model_parameters",
        "replay_key",
        "lease_token",
        "lease_generation",
        "lease_expires_at",
        "worker_id",
        "reviewer_id",
    }
    prohibited_fragments = (
        "private_key",
        "secret",
        "password",
        "credential",
        "api_key",
        "access_key",
        "auth_token",
        "bearer_token",
    )

    def visit(item: Any, path: str) -> None:
        if isinstance(item, Mapping):
            for key, nested in item.items():
                if not isinstance(key, str):
                    raise PrivateMaterialError(f"{context} contains a non-string key at {path}")
                normalized = key.lower().replace("-", "_")
                is_digest = any(marker in normalized for marker in ("sha256", "hmac", "digest", "commitment"))
                if (
                    normalized in prohibited_exact
                    or any(fragment in normalized for fragment in prohibited_fragments)
                    or ("private" in normalized and not is_digest)
                ):
                    raise PrivateMaterialError(f"{context} contains forbidden private material at {path}.{key}")
                visit(nested, f"{path}.{key}")
        elif isinstance(item, list):
            for index, nested in enumerate(item):
                visit(nested, f"{path}[{index}]")

    visit(value, "$")


def _audit_timestamp(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    return _lease_time(value).isoformat() if value.endswith("Z") else _lease_time(value).isoformat()


def _lease_time(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


def _nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


__all__ = [
    "ABORTED",
    "APPROVED",
    "AWAITING_RECOMMENDATION",
    "AWAITING_REVIEW",
    "ApprovalRequiredError",
    "BudgetExceededError",
    "CampaignAlreadyExistsError",
    "CampaignJournalEvent",
    "CampaignNotFoundError",
    "CampaignState",
    "DuplicateResumeError",
    "EXECUTING",
    "ExecutionLeaseClaim",
    "ExecutionLeaseError",
    "HUMAN_INTERVENED",
    "HashChainIntegrityError",
    "InvalidPhaseError",
    "NoPendingRecommendationError",
    "PrivateMaterialError",
    "ProtocolConsumptionError",
    "RFBCampaignStore",
    "RFBWorkflowStore",
    "RFB_CAMPAIGN_STORE_SCHEMA_VERSION",
    "RFB_WORKFLOW_VERSION",
    "RevisionConflictError",
    "RfbCampaignStoreError",
    "SQLiteRFBCampaignStore",
    "STRICT_BENCHMARK",
    "StaleExecutionLeaseError",
    "StaleRevisionError",
    "WORKFLOW_CASE_STUDY",
]
