from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from discovery_flight_simulator.ledger import sha256_json
from discovery_flight_simulator.rfb.campaign import RFBCampaign
from discovery_flight_simulator.rfb.contracts import RFBPlanningStateV1
from discovery_flight_simulator.rfb.policies import FixedGridRFBPolicy
from discovery_flight_simulator.rfb.replay import RFBReplayError, replay_rfb_campaign_export_v1
from discovery_flight_simulator.rfb.scenario import load_rfb_scenario
from discovery_flight_simulator.rfb.store import SQLiteRFBCampaignStore


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "rfbzero_cell_v0.json"
_COMMITMENT_KEY = b"rfb-replay-test-commitment-key"


def _campaign(tmp_path: Path, campaign_id: str) -> tuple[SQLiteRFBCampaignStore, RFBCampaign]:
    loaded = load_rfb_scenario(SCENARIO_PATH, private_commitment_key=_COMMITMENT_KEY)
    store = SQLiteRFBCampaignStore(tmp_path / f"{campaign_id}.sqlite")
    campaign = RFBCampaign.create(
        store,
        campaign_id,
        policy_id=FixedGridRFBPolicy.policy_id,
        policy_version=FixedGridRFBPolicy.policy_version,
        public_scenario=loaded.public_projection(),
    )
    return store, campaign


def _recommendation(campaign: RFBCampaign):
    state = campaign.state
    planning_state = RFBPlanningStateV1(
        scenario=campaign.store.public_scenario(campaign.campaign_id),
        event_head_sha256=campaign.store.events(campaign.campaign_id)[-1].event_sha256,
        revision=state.revision,
        remaining_attempt_budget=state.remaining_budgets["attempts"],
        remaining_measurement_budget=state.remaining_budgets["measurements"],
    )
    recommendation = FixedGridRFBPolicy().recommend(
        planning_state,
        rejected_action_ids=state.rejected_action_ids,
    )
    assert recommendation is not None
    return recommendation


def _rechain(exported: dict[str, Any]) -> None:
    previous = "0" * 64
    for event in exported["events"]:
        event["previous_event_sha256"] = previous
        event["event_sha256"] = sha256_json(
            {
                "schema_version": event["schema_version"],
                "event_type": event["event_type"],
                "payload": event["payload"],
                "sequence": event["sequence"],
                "previous_event_sha256": event["previous_event_sha256"],
            }
        )
        previous = event["event_sha256"]
    exported["event_head_sha256"] = previous


def test_replay_derives_human_intervention_for_edit_reject_and_abort(tmp_path: Path) -> None:
    store, edited = _campaign(tmp_path, "edited")
    first = _recommendation(edited)
    pending = edited.recommend(first, expected_revision=edited.state.revision)
    replacement = _recommendation(edited)
    edited.approve_with_edit(
        replacement,
        decision_id="edit-1",
        expected_revision=pending.revision,
    )
    replayed_edit = replay_rfb_campaign_export_v1(store.export_campaign(edited.campaign_id))
    assert replayed_edit.human_intervened
    assert not replayed_edit.comparison_eligible
    assert replayed_edit.campaign["phase"] == "awaiting_review"

    reject_store, rejected = _campaign(tmp_path, "rejected")
    pending = rejected.recommend(_recommendation(rejected), expected_revision=rejected.state.revision)
    rejected.reject(decision_id="reject-1", reason_code="scope", expected_revision=pending.revision)
    replayed_reject = replay_rfb_campaign_export_v1(reject_store.export_campaign(rejected.campaign_id))
    assert replayed_reject.human_intervened
    assert replayed_reject.campaign["phase"] == "awaiting_recommendation"

    abort_store, aborted = _campaign(tmp_path, "aborted")
    pending = aborted.recommend(_recommendation(aborted), expected_revision=aborted.state.revision)
    aborted.abort(decision_id="abort-1", reason_code="scope", expected_revision=pending.revision)
    replayed_abort = replay_rfb_campaign_export_v1(abort_store.export_campaign(aborted.campaign_id))
    assert replayed_abort.human_intervened
    assert replayed_abort.campaign["phase"] == "aborted"


def test_replay_rejects_a_semantically_invalid_but_rehashed_execution_reservation(tmp_path: Path) -> None:
    store, campaign = _campaign(tmp_path, "reservation")
    pending = campaign.recommend(_recommendation(campaign), expected_revision=campaign.state.revision)
    approved = campaign.approve(decision_id="approve-1", expected_revision=pending.revision)
    loaded = load_rfb_scenario(SCENARIO_PATH, private_commitment_key=_COMMITMENT_KEY)
    store.claim_execution(
        campaign.campaign_id,
        decision_id="approve-1",
        expected_revision=approved.revision,
        execution_identity=loaded.execution_identity,
    )
    exported = store.export_campaign(campaign.campaign_id)
    started = next(event for event in exported["events"] if event["event_type"] == "execution_started")
    started["payload"]["execution"]["reserved_costs"] = {
        "attempt_cost": 0,
        "measurement_cost": 0,
    }
    _rechain(exported)

    with pytest.raises(RFBReplayError, match="reservation does not match"):
        replay_rfb_campaign_export_v1(exported)


def test_replay_rejects_a_rehashed_boolean_event_sequence(tmp_path: Path) -> None:
    store, campaign = _campaign(tmp_path, "boolean-sequence")
    exported = store.export_campaign(campaign.campaign_id)
    exported["events"][0]["sequence"] = False
    _rechain(exported)

    with pytest.raises(RFBReplayError, match="canonical hash chain mismatch"):
        replay_rfb_campaign_export_v1(exported)


def test_replay_rejects_a_boolean_terminal_revision(tmp_path: Path) -> None:
    store, campaign = _campaign(tmp_path, "boolean-revision")
    exported = store.export_campaign(campaign.campaign_id)
    assert exported["campaign"]["revision"] == 0
    exported["campaign"]["revision"] = False

    with pytest.raises(RFBReplayError, match="terminal campaign state does not match"):
        replay_rfb_campaign_export_v1(exported)


def test_replay_rejects_a_rehashed_boolean_execution_cost(tmp_path: Path) -> None:
    store, campaign = _campaign(tmp_path, "boolean-cost")
    pending = campaign.recommend(_recommendation(campaign), expected_revision=campaign.state.revision)
    approved = campaign.approve(decision_id="approve-1", expected_revision=pending.revision)
    loaded = load_rfb_scenario(SCENARIO_PATH, private_commitment_key=_COMMITMENT_KEY)
    store.claim_execution(
        campaign.campaign_id,
        decision_id="approve-1",
        expected_revision=approved.revision,
        execution_identity=loaded.execution_identity,
    )
    exported = store.export_campaign(campaign.campaign_id)
    started = next(event for event in exported["events"] if event["event_type"] == "execution_started")
    assert started["payload"]["execution"]["reserved_costs"]["attempt_cost"] == 1
    started["payload"]["execution"]["reserved_costs"]["attempt_cost"] = True
    _rechain(exported)

    with pytest.raises(RFBReplayError, match="reservation does not match"):
        replay_rfb_campaign_export_v1(exported)


def test_replay_rejects_an_integer_terminal_eligibility_flag(tmp_path: Path) -> None:
    store, campaign = _campaign(tmp_path, "integer-eligibility")
    exported = store.export_campaign(campaign.campaign_id)
    assert exported["campaign"]["comparison_eligible"] is True
    exported["campaign"]["comparison_eligible"] = 1

    with pytest.raises(RFBReplayError, match="terminal campaign state does not match"):
        replay_rfb_campaign_export_v1(exported)
