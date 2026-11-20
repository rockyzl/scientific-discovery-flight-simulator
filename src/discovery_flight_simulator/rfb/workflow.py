"""Durable LangGraph orchestration for simulated RFB V1 campaigns.

The campaign store is authoritative.  This graph only keeps a campaign ID and
small control markers needed to recreate a pending review interruption after a
process restart.  Private scenario execution data stays on this service and is
passed directly to the durable execution bridge, never to graph state.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from discovery_flight_simulator.ledger import sha256_json

from .contracts import RFBActionV1, RFBOutcomeV1, RFBPlanningStateV1
from .execution import RFBExecutionService
from .oracle import RFBZeroOracleAdapter
from .policies import (
    ConstrainedBORFBPolicy,
    FixedGridRFBPolicy,
    RFBPolicyV1,
    RFBPublicObservationV1,
    RandomRFBPolicy,
)
from .scenario import LoadedRFBScenarioV1
from .store import (
    APPROVED,
    AWAITING_RECOMMENDATION,
    AWAITING_REVIEW,
    EXECUTING,
    CampaignJournalEvent,
    CampaignState,
    SQLiteRFBCampaignStore,
)


class RFBWorkflowError(RuntimeError):
    """Base class for workflow orchestration failures with safe messages."""


class UnknownRFBScenarioError(RFBWorkflowError):
    """Raised when a requested loaded scenario is unavailable."""


class UnknownRFBPolicyError(RFBWorkflowError):
    """Raised when a requested static policy is unavailable."""


class RFBWorkflowResumeConflictError(RFBWorkflowError):
    """Raised when a resume does not match the current public decision."""


class RFBWorkflowPhaseConflictError(RFBWorkflowResumeConflictError):
    """Raised when a workflow node cannot operate in the source-of-truth phase."""


class RFBWorkflowExhaustedError(RFBWorkflowError):
    """Raised when no canonical recommendation can be persisted."""


class _RFBWorkflowGraphState(TypedDict, total=False):
    """Harmless durable graph control state; campaign data remains in SQLite."""

    campaign_id: str
    review_waiting: bool
    last_processed_decision_id: str


@dataclass(frozen=True)
class RFBWorkflowAdvanceResult:
    """The verified public campaign state after one workflow advancement."""

    state: CampaignState
    disposition: Literal["advanced", "already_applied"]

    def __post_init__(self) -> None:
        if self.disposition not in {"advanced", "already_applied"}:
            raise ValueError("workflow disposition is unsupported")


_POLICIES: dict[str, type[RFBPolicyV1]] = {
    FixedGridRFBPolicy.policy_id: FixedGridRFBPolicy,
    RandomRFBPolicy.policy_id: RandomRFBPolicy,
    ConstrainedBORFBPolicy.policy_id: ConstrainedBORFBPolicy,
}


class RFBWorkflowService:
    """Run deterministic review-gated RFB orchestration over a durable store."""

    def __init__(
        self,
        store: SQLiteRFBCampaignStore,
        scenarios: Mapping[str, LoadedRFBScenarioV1],
        checkpoint_path: str | Path,
    ) -> None:
        self.store = store
        self._scenarios = dict(scenarios)
        self._checkpoint_connection = sqlite3.connect(Path(checkpoint_path), check_same_thread=False)
        self._checkpointer = SqliteSaver(self._checkpoint_connection)
        self._checkpointer.setup()
        self._execution_service = RFBExecutionService(store, RFBZeroOracleAdapter())
        self._graph = self._build_graph()
        self._closed = False

    def create_campaign(
        self, campaign_id: str, scenario_id: str, policy_id: str
    ) -> RFBWorkflowAdvanceResult:
        """Create strict campaign state, persist a recommendation, and pause for review."""

        scenario = self._scenario_for_id(scenario_id)
        policy_type = self._policy_for_id(policy_id)
        self.store.create_campaign(
            campaign_id,
            policy_id=policy_type.policy_id,
            policy_version=policy_type.policy_version,
            public_scenario=scenario.public_projection(),
        )
        self._graph.invoke(
            {"campaign_id": campaign_id},
            self._graph_config(campaign_id),
            durability="sync",
        )
        return RFBWorkflowAdvanceResult(self.store.get_campaign(campaign_id), "advanced")

    def record_decision(
        self,
        campaign_id: str,
        decision_id: str,
        expected_revision: int,
        decision: str,
        reason_code: str | None = None,
        edited_recommendation: Mapping[str, Any] | None = None,
    ) -> CampaignState:
        """Record only the durable public decision; this method never runs the graph."""

        if decision not in {"approve", "reject", "approve_with_edit"}:
            raise RFBWorkflowError("workflow decision is unsupported")
        return self.store.record_decision(
            campaign_id,
            decision,
            decision_id=decision_id,
            expected_revision=expected_revision,
            reason_code=reason_code,
            edited_recommendation=edited_recommendation,
        )

    def resume(
        self, campaign_id: str, decision_id: str, expected_revision: int
    ) -> RFBWorkflowAdvanceResult:
        """Advance exactly the specified recorded decision through its graph continuation."""

        if not isinstance(decision_id, str) or not decision_id.strip():
            raise RFBWorkflowResumeConflictError("workflow resume requires a decision")
        decision_id = decision_id.strip()
        state = self.store.get_campaign(campaign_id)
        events = self.store.events(campaign_id)
        config = self._graph_config(campaign_id)

        if self._approved_decision_is_fully_applied(state, decision_id):
            self._require_durable_decision_revision(state, events, decision_id, expected_revision)
            return RFBWorkflowAdvanceResult(state, "already_applied")

        snapshot = self._graph.get_state(config)
        graph_values = snapshot.values if isinstance(snapshot.values, Mapping) else {}

        if self._decision_is_fully_applied(state, decision_id, graph_values):
            self._require_durable_decision_revision(state, events, decision_id, expected_revision)
            return RFBWorkflowAdvanceResult(state, "already_applied")

        self._require_resume_matches(state, decision_id, expected_revision)
        if graph_values.get("last_processed_decision_id") == decision_id:
            self._graph.invoke(None, config, durability="sync")
        else:
            self._graph.invoke(Command(resume=decision_id), config, durability="sync")
        return RFBWorkflowAdvanceResult(self.store.get_campaign(campaign_id), "advanced")

    def campaign_state(self, campaign_id: str) -> CampaignState:
        """Return verified public state from the campaign source of truth."""

        return self.store.get_campaign(campaign_id)

    def public_events(self, campaign_id: str) -> tuple[CampaignJournalEvent, ...]:
        """Return verified public journal events from the campaign source of truth."""

        return self.store.events(campaign_id)

    def close(self) -> None:
        """Close only the disposable graph checkpointer connection."""

        if not self._closed:
            self._checkpoint_connection.close()
            self._closed = True

    def _build_graph(self):
        builder = StateGraph(_RFBWorkflowGraphState)
        builder.add_node("recommend", self._recommend)
        builder.add_node("review", self._review)
        builder.add_node("execute", self._execute)
        builder.add_edge(START, "recommend")
        builder.add_edge("recommend", "review")
        builder.add_conditional_edges("review", self._route_after_review)
        builder.add_edge("execute", "recommend")
        return builder.compile(checkpointer=self._checkpointer)

    def _recommend(self, graph_state: _RFBWorkflowGraphState) -> dict[str, bool]:
        campaign_id = self._campaign_id_from_graph_state(graph_state)
        state = self.store.get_campaign(campaign_id)
        if state.phase == AWAITING_REVIEW:
            # A crash after SQLite saved the recommendation must not save it twice.
            return {"review_waiting": True}
        if state.phase != AWAITING_RECOMMENDATION:
            raise RFBWorkflowPhaseConflictError("workflow cannot create a recommendation now")

        self._loaded_scenario_for_campaign(campaign_id)
        policy_type = self._policy_for_campaign(state)
        events = self.store.events(campaign_id)
        if not events:
            raise RFBWorkflowError("workflow campaign journal is incomplete")
        planning_state = RFBPlanningStateV1(
            scenario=self.store.public_scenario(campaign_id),
            event_head_sha256=events[-1].event_sha256,
            revision=state.revision,
            remaining_attempt_budget=state.remaining_budgets["attempts"],
            remaining_measurement_budget=state.remaining_budgets["measurements"],
        )
        recommendation = policy_type().recommend(
            planning_state,
            observations=self._public_observations(state),
            rejected_action_ids=state.rejected_action_ids,
        )
        if recommendation is None:
            raise RFBWorkflowExhaustedError("workflow cannot create another recommendation")
        self.store.save_recommendation(
            campaign_id,
            recommendation,
            expected_revision=state.revision,
        )
        return {"review_waiting": True}

    def _review(self, graph_state: _RFBWorkflowGraphState) -> dict[str, str | bool]:
        campaign_id = self._campaign_id_from_graph_state(graph_state)
        state = self.store.get_campaign(campaign_id)
        waiting = bool(graph_state.get("review_waiting", False))
        if state.phase != AWAITING_REVIEW and not waiting:
            raise RFBWorkflowPhaseConflictError("workflow review is not pending")

        # LangGraph replays this node to deliver a resume value.  ``waiting``
        # records that the original interruption was created from awaiting_review.
        decision_id = interrupt({"campaign_id": campaign_id})
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise RFBWorkflowResumeConflictError("workflow resume requires a decision")
        decision_id = decision_id.strip()

        # SQLite may have changed while the graph was interrupted; it decides the route.
        resumed_state = self.store.get_campaign(campaign_id)
        self._require_resumed_decision_matches(resumed_state, decision_id)
        return {"review_waiting": False, "last_processed_decision_id": decision_id}

    def _route_after_review(self, graph_state: _RFBWorkflowGraphState) -> str:
        campaign_id = self._campaign_id_from_graph_state(graph_state)
        state = self.store.get_campaign(campaign_id)
        if state.phase in {APPROVED, EXECUTING}:
            return "execute"
        if state.phase == AWAITING_RECOMMENDATION:
            return "recommend"
        if state.phase == AWAITING_REVIEW:
            return "review"
        if state.phase == "aborted":
            return END
        raise RFBWorkflowPhaseConflictError("workflow cannot route the current campaign phase")

    def _execute(self, graph_state: _RFBWorkflowGraphState) -> dict[str, Any]:
        campaign_id = self._campaign_id_from_graph_state(graph_state)
        decision_id = graph_state.get("last_processed_decision_id")
        if not isinstance(decision_id, str) or not decision_id:
            raise RFBWorkflowResumeConflictError("workflow execution lacks a decision")
        state = self.store.get_campaign(campaign_id)
        if state.phase == AWAITING_RECOMMENDATION:
            # A crash after commit replays this node, but the store has already completed it.
            return {}
        if state.phase != APPROVED or state.approved_decision is None:
            raise RFBWorkflowPhaseConflictError("workflow execution is not approved")
        if state.approved_decision.get("decision_id") != decision_id:
            raise RFBWorkflowResumeConflictError("workflow execution decision does not match")

        scenario = self._loaded_scenario_for_campaign(campaign_id)
        self._execution_service.execute(
            campaign_id,
            decision_id=decision_id,
            expected_revision=state.revision,
            oracle_config=scenario.execution_oracle_spec,
            execution_identity=scenario.execution_identity,
        )
        return {}

    def _scenario_for_id(self, scenario_id: str) -> LoadedRFBScenarioV1:
        scenario = self._scenarios.get(scenario_id)
        if not isinstance(scenario, LoadedRFBScenarioV1):
            raise UnknownRFBScenarioError("requested RFB scenario is unavailable")
        if scenario.public_projection().scenario_id != scenario_id:
            raise UnknownRFBScenarioError("requested RFB scenario is unavailable")
        return scenario

    @staticmethod
    def _policy_for_id(policy_id: str) -> type[RFBPolicyV1]:
        policy_type = _POLICIES.get(policy_id)
        if policy_type is None:
            raise UnknownRFBPolicyError("requested RFB policy is unavailable")
        return policy_type

    def _loaded_scenario_for_campaign(self, campaign_id: str) -> LoadedRFBScenarioV1:
        public_scenario = self.store.public_scenario(campaign_id)
        scenario = self._scenario_for_id(public_scenario.scenario_id)
        if scenario.public_projection().public_projection_sha256 != public_scenario.public_projection_sha256:
            raise UnknownRFBScenarioError("campaign RFB scenario is unavailable")
        return scenario

    @staticmethod
    def _policy_for_campaign(state: CampaignState) -> type[RFBPolicyV1]:
        policy_type = _POLICIES.get(state.policy_id)
        if policy_type is None or policy_type.policy_version != state.policy_version:
            raise UnknownRFBPolicyError("campaign RFB policy is unavailable")
        return policy_type

    @staticmethod
    def _public_observations(state: CampaignState) -> tuple[RFBPublicObservationV1, ...]:
        observations: list[RFBPublicObservationV1] = []
        for execution in state.executions:
            utility_record = execution["utility_record"]
            observations.append(
                RFBPublicObservationV1(
                    action=RFBActionV1.from_dict(execution["action"]),
                    outcome=RFBOutcomeV1(**execution["outcome"]),
                    utility=utility_record["utility"],
                )
            )
        return tuple(observations)

    @staticmethod
    def _campaign_id_from_graph_state(graph_state: _RFBWorkflowGraphState) -> str:
        campaign_id = graph_state.get("campaign_id")
        if not isinstance(campaign_id, str) or not campaign_id.strip():
            raise RFBWorkflowError("workflow graph campaign is invalid")
        return campaign_id

    @staticmethod
    def _decision_record(state: CampaignState, decision_id: str) -> Mapping[str, Any] | None:
        return next(
            (decision for decision in state.decisions if decision.get("decision_id") == decision_id),
            None,
        )

    def _require_resume_matches(
        self, state: CampaignState, decision_id: str, expected_revision: int
    ) -> None:
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool):
            raise RFBWorkflowResumeConflictError("workflow resume revision is invalid")
        if state.revision != expected_revision:
            raise RFBWorkflowResumeConflictError("workflow resume revision does not match")
        self._require_resumed_decision_matches(state, decision_id)

    def _require_resumed_decision_matches(self, state: CampaignState, decision_id: str) -> None:
        decision = self._decision_record(state, decision_id)
        if decision is None:
            raise RFBWorkflowResumeConflictError("workflow resume decision is unavailable")
        decision_type = decision.get("decision")
        if state.phase in {APPROVED, EXECUTING}:
            if (
                decision_type != "approve"
                or state.approved_decision is None
                or state.approved_decision.get("decision_id") != decision_id
            ):
                raise RFBWorkflowResumeConflictError("workflow resume decision does not match")
            return
        if state.phase == AWAITING_RECOMMENDATION:
            if not state.decisions or state.decisions[-1].get("decision_id") != decision_id:
                raise RFBWorkflowResumeConflictError("workflow resume decision does not match")
            if decision_type != "reject":
                raise RFBWorkflowResumeConflictError("workflow resume decision does not match")
            return
        if state.phase == AWAITING_REVIEW:
            if not state.decisions or state.decisions[-1].get("decision_id") != decision_id:
                raise RFBWorkflowResumeConflictError("workflow resume decision does not match")
            if decision_type != "approve_with_edit":
                raise RFBWorkflowResumeConflictError("workflow resume decision does not match")
            return
        raise RFBWorkflowPhaseConflictError("workflow resume is not permitted now")

    def _require_durable_decision_revision(
        self,
        state: CampaignState,
        events: tuple[CampaignJournalEvent, ...],
        decision_id: str,
        expected_revision: int,
    ) -> None:
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool):
            raise RFBWorkflowResumeConflictError("workflow resume revision is invalid")
        decision = self._decision_record(state, decision_id)
        if decision is None:
            raise RFBWorkflowResumeConflictError("workflow resume decision is unavailable")
        for event in events:
            if event.event_type == "approval_recorded":
                event_decision = event.payload.get("approval")
            elif event.event_type == "intervention_recorded":
                event_decision = event.payload.get("intervention")
            else:
                continue
            if event_decision == decision:
                if event.sequence == expected_revision:
                    return
                raise RFBWorkflowResumeConflictError("workflow resume revision does not match")
        raise RFBWorkflowResumeConflictError("workflow resume decision is unavailable")

    @staticmethod
    def _approved_decision_is_fully_applied(state: CampaignState, decision_id: str) -> bool:
        decision = RFBWorkflowService._decision_record(state, decision_id)
        return (
            decision is not None
            and decision.get("decision") == "approve"
            and any(execution.get("decision_id") == decision_id for execution in state.executions)
        )

    def _decision_is_fully_applied(
        self,
        state: CampaignState,
        decision_id: str,
        graph_values: Mapping[str, Any],
    ) -> bool:
        if graph_values.get("last_processed_decision_id") != decision_id:
            return False
        decision = self._decision_record(state, decision_id)
        if decision is None:
            return False
        if decision.get("decision") == "approve":
            return any(execution.get("decision_id") == decision_id for execution in state.executions)
        if decision.get("decision") == "reject":
            return state.phase == AWAITING_REVIEW
        if decision.get("decision") == "approve_with_edit":
            return state.phase == AWAITING_REVIEW
        return False

    @staticmethod
    def _thread_id(campaign_id: str) -> str:
        return "rfb-workflow-v1-" + sha256_json({"campaign_id": campaign_id})

    def _graph_config(self, campaign_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": self._thread_id(campaign_id)}}


__all__ = [
    "RFBWorkflowAdvanceResult",
    "RFBWorkflowError",
    "RFBWorkflowExhaustedError",
    "RFBWorkflowPhaseConflictError",
    "RFBWorkflowResumeConflictError",
    "RFBWorkflowService",
    "UnknownRFBPolicyError",
    "UnknownRFBScenarioError",
]
