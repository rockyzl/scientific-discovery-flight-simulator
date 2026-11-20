from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from discovery_flight_simulator.rfb.contracts import RFBPlanningStateV1
from discovery_flight_simulator.rfb.policies import FixedGridRFBPolicy
from discovery_flight_simulator.rfb.scenario import LoadedRFBScenarioV1, load_rfb_scenario
from discovery_flight_simulator.rfb.store import (
    APPROVED,
    AWAITING_RECOMMENDATION,
    AWAITING_REVIEW,
    SQLiteRFBCampaignStore,
    WORKFLOW_CASE_STUDY,
)
from discovery_flight_simulator.rfb.workflow import RFBWorkflowResumeConflictError, RFBWorkflowService


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "rfbzero_cell_v0.json"
SCENARIO_ID = "rfbzero_cell_v0"
_COMMITMENT_KEY = b"rfb-workflow-test-commitment-key"


def _loaded_scenarios() -> dict[str, LoadedRFBScenarioV1]:
    loaded = load_rfb_scenario(SCENARIO_PATH, private_commitment_key=_COMMITMENT_KEY)
    return {SCENARIO_ID: loaded}


def _service(tmp_path: Path) -> tuple[SQLiteRFBCampaignStore, RFBWorkflowService]:
    store = SQLiteRFBCampaignStore(tmp_path / "campaign.sqlite")
    service = RFBWorkflowService(store, _loaded_scenarios(), tmp_path / "workflow-checkpoints.sqlite")
    return store, service


def _snapshot_payload(service: RFBWorkflowService, campaign_id: str) -> str:
    snapshot = service._graph.get_state(service._graph_config(campaign_id))
    interrupts = [
        interrupt.value
        for task in snapshot.tasks
        for interrupt in task.interrupts
    ]
    return json.dumps({"values": snapshot.values, "interrupts": interrupts}, sort_keys=True)


def _edited_recommendation(
    store: SQLiteRFBCampaignStore, campaign_id: str
):
    state = store.get_campaign(campaign_id)
    planning_state = RFBPlanningStateV1(
        scenario=store.public_scenario(campaign_id),
        event_head_sha256=store.events(campaign_id)[-1].event_sha256,
        revision=state.revision,
        remaining_attempt_budget=state.remaining_budgets["attempts"],
        remaining_measurement_budget=state.remaining_budgets["measurements"],
    )
    recommendation = FixedGridRFBPolicy().recommend(planning_state)
    assert recommendation is not None
    return replace(
        recommendation,
        action=planning_state.scenario.candidate_actions[1],
        action_id=None,
        recommendation_id=None,
        recommendation_sha256=None,
    )


def test_create_pauses_for_review_without_execution_or_cost(tmp_path: Path) -> None:
    store, service = _service(tmp_path)

    result = service.create_campaign("workflow-start", SCENARIO_ID, "fixed_grid")

    assert result.disposition == "advanced"
    assert result.state.phase == AWAITING_REVIEW
    assert result.state.executions == ()
    assert result.state.cumulative_costs == {"attempts": 0, "measurements": 0}
    assert result.state.reserved_costs == {"attempts": 0, "measurements": 0}
    assert result.state.pending_recommendation is not None
    assert len(service.public_events("workflow-start")) == 2
    assert store.get_campaign("workflow-start") == result.state

    service.close()
    store.close()


def test_approval_is_record_only_then_resume_executes_once_and_is_idempotent(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    review = service.create_campaign("workflow-approve", SCENARIO_ID, "fixed_grid").state
    first_recommendation = review.pending_recommendation
    assert first_recommendation is not None

    approved = service.record_decision(
        "workflow-approve",
        "approval-1",
        review.revision,
        "approve",
    )
    assert approved.phase == APPROVED
    assert approved.executions == ()
    assert approved.cumulative_costs == {"attempts": 0, "measurements": 0}
    assert approved.reserved_costs == {"attempts": 0, "measurements": 0}

    advanced = service.resume("workflow-approve", "approval-1", approved.revision)

    assert advanced.disposition == "advanced"
    assert advanced.state.phase == AWAITING_REVIEW
    assert len(advanced.state.executions) == 1
    assert advanced.state.cumulative_costs == {"attempts": 1, "measurements": 1}
    assert advanced.state.reserved_costs == {"attempts": 0, "measurements": 0}
    assert advanced.state.pending_recommendation is not None
    assert advanced.state.pending_recommendation["action_id"] != first_recommendation["action_id"]

    repeated = service.resume("workflow-approve", "approval-1", approved.revision)

    assert repeated.disposition == "already_applied"
    assert repeated.state == advanced.state
    assert len(store.get_campaign("workflow-approve").executions) == 1
    assert store.get_campaign("workflow-approve").cumulative_costs == {
        "attempts": 1,
        "measurements": 1,
    }

    service.close()
    store.close()


def test_completed_approval_resume_requires_its_durable_approval_revision(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    review = service.create_campaign("workflow-completed-revision", SCENARIO_ID, "fixed_grid").state
    approved = service.record_decision(
        "workflow-completed-revision", "approval-completed-1", review.revision, "approve"
    )
    completed = service.resume(
        "workflow-completed-revision", "approval-completed-1", approved.revision
    )

    with pytest.raises(RFBWorkflowResumeConflictError, match="revision"):
        service.resume(
            "workflow-completed-revision",
            "approval-completed-1",
            completed.state.revision,
        )

    repeated = service.resume(
        "workflow-completed-revision", "approval-completed-1", approved.revision
    )
    assert repeated.disposition == "already_applied"
    assert repeated.state == completed.state

    service.close()
    store.close()


def test_reject_then_resume_creates_a_new_unrankable_review_without_execution(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    review = service.create_campaign("workflow-reject", SCENARIO_ID, "fixed_grid").state
    rejected_recommendation = review.pending_recommendation
    assert rejected_recommendation is not None

    rejected = service.record_decision(
        "workflow-reject",
        "rejection-1",
        review.revision,
        "reject",
        reason_code="outside_review_scope",
    )
    assert rejected.phase == AWAITING_RECOMMENDATION
    assert rejected.executions == ()

    advanced = service.resume("workflow-reject", "rejection-1", rejected.revision)

    assert advanced.disposition == "advanced"
    assert advanced.state.phase == AWAITING_REVIEW
    assert advanced.state.executions == ()
    assert advanced.state.cumulative_costs == {"attempts": 0, "measurements": 0}
    assert advanced.state.mode == WORKFLOW_CASE_STUDY
    assert advanced.state.human_intervened
    assert not advanced.state.comparison_eligible
    assert advanced.state.pending_recommendation is not None
    assert advanced.state.pending_recommendation["action_id"] != rejected_recommendation["action_id"]
    assert rejected_recommendation["action_id"] in advanced.state.rejected_action_ids
    assert store.get_campaign("workflow-reject") == advanced.state

    service.close()
    store.close()


def test_edited_recommendation_stays_in_review_until_a_fresh_approval(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    review = service.create_campaign("workflow-edit", SCENARIO_ID, "fixed_grid").state
    edited_recommendation = _edited_recommendation(store, "workflow-edit")

    edited = service.record_decision(
        "workflow-edit",
        "edit-1",
        review.revision,
        "approve_with_edit",
        edited_recommendation=edited_recommendation.to_dict(),
    )
    assert edited.phase == AWAITING_REVIEW
    assert edited.executions == ()
    assert edited.mode == WORKFLOW_CASE_STUDY

    resumed = service.resume("workflow-edit", "edit-1", edited.revision)

    assert resumed.disposition == "advanced"
    assert resumed.state.phase == AWAITING_REVIEW
    assert resumed.state.executions == ()
    assert resumed.state.cumulative_costs == {"attempts": 0, "measurements": 0}
    fresh_approval = service.record_decision(
        "workflow-edit",
        "edit-approval-1",
        resumed.state.revision,
        "approve",
    )
    assert fresh_approval.phase == APPROVED
    assert fresh_approval.executions == ()

    service.close()
    store.close()


def test_restart_resumes_pending_review_without_private_graph_state(tmp_path: Path) -> None:
    store = SQLiteRFBCampaignStore(tmp_path / "campaign.sqlite")
    checkpoint_path = tmp_path / "workflow-checkpoints.sqlite"
    first = RFBWorkflowService(store, _loaded_scenarios(), checkpoint_path)
    review = first.create_campaign("workflow-restart", SCENARIO_ID, "random").state

    paused_payload = _snapshot_payload(first, "workflow-restart")
    assert '"campaign_id": "workflow-restart"' in paused_payload
    for forbidden in (
        "model_parameters",
        "execution_identity",
        "execution_oracle_spec",
        "lease_token",
        "reviewer",
        "capacity_reference_C",
    ):
        assert forbidden not in paused_payload
    first.close()

    restarted = RFBWorkflowService(store, _loaded_scenarios(), checkpoint_path)
    approved = restarted.record_decision(
        "workflow-restart",
        "restart-approval-1",
        review.revision,
        "approve",
    )
    resumed = restarted.resume("workflow-restart", "restart-approval-1", approved.revision)

    assert resumed.disposition == "advanced"
    assert resumed.state.phase == AWAITING_REVIEW
    assert len(resumed.state.executions) == 1
    resumed_payload = _snapshot_payload(restarted, "workflow-restart")
    for forbidden in (
        "model_parameters",
        "execution_identity",
        "execution_oracle_spec",
        "lease_token",
        "reviewer",
        "capacity_reference_C",
    ):
        assert forbidden not in resumed_payload

    restarted.close()
    store.close()


def test_workflow_module_has_no_llm_hardware_or_network_runtime_imports() -> None:
    import discovery_flight_simulator.rfb.workflow as workflow

    source = Path(workflow.__file__).read_text(encoding="utf-8")
    imports: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    forbidden_roots = {
        "anthropic",
        "http",
        "httpx",
        "langchain",
        "litellm",
        "openai",
        "opcua",
        "pyvisa",
        "requests",
        "serial",
        "socket",
        "subprocess",
        "urllib",
    }
    assert not {
        imported
        for imported in imports
        if imported.split(".", maxsplit=1)[0] in forbidden_roots
    }
