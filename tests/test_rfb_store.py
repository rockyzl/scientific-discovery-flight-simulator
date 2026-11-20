from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from discovery_flight_simulator.rfb.campaign import RFBCampaign
from discovery_flight_simulator.rfb.contracts import RFBActionV1, RFBPlanningStateV1, build_rfb_campaign_event_v1
from discovery_flight_simulator.rfb.policies import FixedGridRFBPolicy
from discovery_flight_simulator.rfb.scenario import load_rfb_scenario
from discovery_flight_simulator.rfb.store import (
    APPROVED,
    AWAITING_RECOMMENDATION,
    AWAITING_REVIEW,
    SQLiteRFBCampaignStore,
    STRICT_BENCHMARK,
    WORKFLOW_CASE_STUDY,
)


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "rfbzero_cell_v0.json"
_COMMITMENT_KEY = b"rfb-store-test-commitment-key"


def _public_scenario():
    return load_rfb_scenario(SCENARIO_PATH, private_commitment_key=_COMMITMENT_KEY).public_projection()


def _store(tmp_path: Path) -> SQLiteRFBCampaignStore:
    return SQLiteRFBCampaignStore(tmp_path / "rfb-campaign.sqlite")


def _campaign(
    store: SQLiteRFBCampaignStore,
    campaign_id: str,
    *,
    scenario=None,
) -> RFBCampaign:
    return RFBCampaign.create(
        store,
        campaign_id,
        policy_id=FixedGridRFBPolicy.policy_id,
        policy_version=FixedGridRFBPolicy.policy_version,
        public_scenario=scenario or _public_scenario(),
        audit_timestamp="2026-07-20T12:00:00+00:00",
    )


def _planning_state(campaign: RFBCampaign) -> RFBPlanningStateV1:
    state = campaign.state
    return RFBPlanningStateV1(
        scenario=campaign.store.public_scenario(campaign.campaign_id),
        event_head_sha256=campaign.store.events(campaign.campaign_id)[-1].event_sha256,
        revision=state.revision,
        remaining_attempt_budget=state.remaining_budgets["attempts"],
        remaining_measurement_budget=state.remaining_budgets["measurements"],
    )


def _recommendation(campaign: RFBCampaign):
    state = campaign.state
    recommendation = FixedGridRFBPolicy().recommend(
        _planning_state(campaign),
        rejected_action_ids=state.rejected_action_ids,
    )
    assert recommendation is not None
    return recommendation


def _save_recommendation(campaign: RFBCampaign):
    recommendation = _recommendation(campaign)
    return recommendation, campaign.recommend(recommendation, expected_revision=campaign.state.revision)


def test_fixed_key_real_scenario_to_policy_campaign_and_persisted_recommendation(tmp_path: Path) -> None:
    loaded = load_rfb_scenario(SCENARIO_PATH, private_commitment_key=_COMMITMENT_KEY)
    public_scenario = loaded.public_projection()
    store = _store(tmp_path)
    campaign = _campaign(store, "canonical-flow", scenario=public_scenario)

    planning_state = _planning_state(campaign)
    recommendation = FixedGridRFBPolicy().recommend(planning_state)
    assert recommendation is not None
    persisted = campaign.recommend(recommendation, expected_revision=planning_state.revision)

    assert planning_state.scenario == public_scenario
    assert recommendation.action == public_scenario.candidate_actions[0]
    assert persisted.phase == AWAITING_REVIEW
    assert persisted.pending_recommendation == recommendation.to_dict()


def test_sqlite_restart_retains_canonical_journal_and_audit_time_is_not_hashed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    campaign = _campaign(store, "restart")
    recommendation, pending = _save_recommendation(campaign)
    before_restart = store.events(campaign.campaign_id)
    db_path = store.path
    store.close()

    restarted = SQLiteRFBCampaignStore(db_path)
    state = restarted.get_campaign(campaign.campaign_id)
    after_restart = restarted.events(campaign.campaign_id)
    first = build_rfb_campaign_event_v1(
        event_type="audit_independent",
        payload={"recommendation_id": recommendation.recommendation_id},
        sequence=7,
        previous_event_sha256="a" * 64,
        audit_timestamp="2026-07-20T12:05:00+00:00",
    )
    second = build_rfb_campaign_event_v1(
        event_type="audit_independent",
        payload={"recommendation_id": recommendation.recommendation_id},
        sequence=7,
        previous_event_sha256="a" * 64,
        audit_timestamp="2030-01-01T00:00:00+00:00",
    )

    assert state.revision == pending.revision == 1
    assert state.pending_recommendation == recommendation.to_dict()
    assert [(event.event_sha256, event.audit_timestamp) for event in after_restart] == [
        (event.event_sha256, event.audit_timestamp) for event in before_restart
    ]
    assert first["event_sha256"] == second["event_sha256"]


@pytest.mark.parametrize(
    "variant",
    (
        "scenario",
        "policy",
        "head",
        "candidate",
    ),
)
def test_recommendation_provenance_rejects_wrong_public_basis(tmp_path: Path, variant: str) -> None:
    store = _store(tmp_path)
    campaign = _campaign(store, f"provenance-{variant}")
    recommendation = _recommendation(campaign)

    if variant == "scenario":
        invalid = replace(
            recommendation,
            public_projection_sha256="f" * 64,
            recommendation_id=None,
            recommendation_sha256=None,
        )
    elif variant == "policy":
        invalid = replace(
            recommendation,
            policy_id="wrong_policy",
            recommendation_id=None,
            recommendation_sha256=None,
        )
    elif variant == "head":
        invalid = replace(
            recommendation,
            basis_event_head_sha256="f" * 64,
            recommendation_id=None,
            recommendation_sha256=None,
        )
    else:
        invalid = replace(
            recommendation,
            action=RFBActionV1(0.12, -0.09, 1.5, 0.5, 240),
            action_id=None,
            recommendation_id=None,
            recommendation_sha256=None,
        )

    with pytest.raises(ValueError, match="recommendation .* does not match|candidate set"):
        campaign.recommend(invalid, expected_revision=campaign.state.revision)


def test_approval_is_strict_while_reject_and_edit_are_human_unrankable(tmp_path: Path) -> None:
    store = _store(tmp_path)

    approved_campaign = _campaign(store, "approved")
    _, pending = _save_recommendation(approved_campaign)
    approved = approved_campaign.approve(decision_id="approve-1", expected_revision=pending.revision)
    assert approved.phase == APPROVED
    assert approved.mode == STRICT_BENCHMARK
    assert approved.comparison_eligible and approved.ranking_eligible

    rejected_campaign = _campaign(store, "rejected")
    rejected_recommendation, pending = _save_recommendation(rejected_campaign)
    rejected = rejected_campaign.reject(
        decision_id="reject-1",
        reason_code="outside_review_scope",
        expected_revision=pending.revision,
    )
    assert rejected.phase == AWAITING_RECOMMENDATION
    assert rejected.rejected_action_ids == (rejected_recommendation.action_id,)
    assert rejected.cumulative_costs == {"attempts": 0, "measurements": 0}
    assert rejected.mode == WORKFLOW_CASE_STUDY
    assert rejected.human_intervened
    assert not rejected.comparison_eligible and not rejected.ranking_eligible

    edited_campaign = _campaign(store, "edited")
    _, pending = _save_recommendation(edited_campaign)
    edited_basis = _recommendation(edited_campaign)
    edited_recommendation = replace(
        edited_basis,
        action=_public_scenario().candidate_actions[1],
        action_id=None,
        recommendation_id=None,
        recommendation_sha256=None,
    )
    edited = edited_campaign.approve_with_edit(
        edited_recommendation,
        decision_id="edit-1",
        expected_revision=pending.revision,
    )
    assert edited.phase == AWAITING_REVIEW
    assert edited.pending_recommendation == edited_recommendation.to_dict()
    assert edited.mode == WORKFLOW_CASE_STUDY
    assert edited.human_intervened
    assert not edited.comparison_eligible and not edited.ranking_eligible
