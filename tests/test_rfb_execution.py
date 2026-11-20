from __future__ import annotations

import json
from pathlib import Path

from discovery_flight_simulator.rfb.campaign import RFBCampaign
from discovery_flight_simulator.rfb.contracts import RFBPlanningStateV1
from discovery_flight_simulator.rfb.execution import RFBExecutionService
from discovery_flight_simulator.rfb.oracle import RFBZeroOracleAdapter
from discovery_flight_simulator.rfb.policies import FixedGridRFBPolicy
from discovery_flight_simulator.rfb.scenario import load_rfb_scenario
from discovery_flight_simulator.rfb.store import SQLiteRFBCampaignStore


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "rfbzero_cell_v0.json"


def test_claim_execution_reserves_the_canonical_cost_model(tmp_path: Path) -> None:
    loaded = load_rfb_scenario(
        SCENARIO_PATH,
        private_commitment_key=b"rfb-execution-test-commitment-key",
    )
    store = SQLiteRFBCampaignStore(tmp_path / "campaign.sqlite")
    campaign = RFBCampaign.create(
        store,
        "execution-claim",
        policy_id=FixedGridRFBPolicy.policy_id,
        policy_version=FixedGridRFBPolicy.policy_version,
        public_scenario=loaded.public_projection(),
    )
    state = campaign.state
    planning_state = RFBPlanningStateV1(
        scenario=store.public_scenario(campaign.campaign_id),
        event_head_sha256=store.events(campaign.campaign_id)[-1].event_sha256,
        revision=state.revision,
        remaining_attempt_budget=state.remaining_budgets["attempts"],
        remaining_measurement_budget=state.remaining_budgets["measurements"],
    )
    recommendation = FixedGridRFBPolicy().recommend(planning_state)
    assert recommendation is not None
    pending = campaign.recommend(recommendation, expected_revision=planning_state.revision)
    approved = campaign.approve(decision_id="approve-1", expected_revision=pending.revision)

    claim = store.claim_execution(
        campaign.campaign_id,
        decision_id="approve-1",
        expected_revision=approved.revision,
        execution_identity=loaded.execution_identity,
        now="2026-07-20T12:10:00+00:00",
    )

    assert claim.claimed
    assert claim.state.reserved_costs == {"attempts": 1, "measurements": 1}


def test_execution_service_commits_once_and_reuses_the_completed_execution(tmp_path: Path) -> None:
    loaded = load_rfb_scenario(
        SCENARIO_PATH,
        private_commitment_key=b"rfb-execution-test-commitment-key",
    )
    store = SQLiteRFBCampaignStore(tmp_path / "campaign.sqlite")
    campaign = RFBCampaign.create(
        store,
        "execution-completion",
        policy_id=FixedGridRFBPolicy.policy_id,
        policy_version=FixedGridRFBPolicy.policy_version,
        public_scenario=loaded.public_projection(),
    )
    state = campaign.state
    planning_state = RFBPlanningStateV1(
        scenario=store.public_scenario(campaign.campaign_id),
        event_head_sha256=store.events(campaign.campaign_id)[-1].event_sha256,
        revision=state.revision,
        remaining_attempt_budget=state.remaining_budgets["attempts"],
        remaining_measurement_budget=state.remaining_budgets["measurements"],
    )
    recommendation = FixedGridRFBPolicy().recommend(planning_state)
    assert recommendation is not None
    pending = campaign.recommend(recommendation, expected_revision=planning_state.revision)
    approved = campaign.approve(decision_id="approve-1", expected_revision=pending.revision)
    service = RFBExecutionService(store, RFBZeroOracleAdapter())

    committed = service.execute(
        campaign.campaign_id,
        decision_id="approve-1",
        expected_revision=approved.revision,
        oracle_config=loaded.execution_oracle_spec,
        execution_identity=loaded.execution_identity,
        now="2026-07-20T12:10:00+00:00",
    )
    completed_state = store.get_campaign(campaign.campaign_id)
    repeated = service.execute(
        campaign.campaign_id,
        decision_id="approve-1",
        expected_revision=approved.revision,
        oracle_config=loaded.execution_oracle_spec,
        execution_identity=loaded.execution_identity,
        now="2026-07-20T12:11:00+00:00",
    )
    retried_state = store.get_campaign(campaign.campaign_id)

    assert committed["costs"] == {"attempt_cost": 1, "measurement_cost": 1}
    assert completed_state.executions == (committed,)
    assert completed_state.cumulative_costs == {"attempts": 1, "measurements": 1}
    assert completed_state.reserved_costs == {"attempts": 0, "measurements": 0}
    assert repeated == committed
    assert retried_state == completed_state
    assert "model_parameters" not in json.dumps(store.export_campaign(campaign.campaign_id), sort_keys=True)
