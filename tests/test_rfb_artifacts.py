from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import discovery_flight_simulator.rfb.artifacts as artifact_module
from discovery_flight_simulator.ledger import canonical_json, sha256_json
from discovery_flight_simulator.rfb.artifacts import (
    RFBArtifactVerificationError,
    export_rfb_artifact_v1,
    verify_rfb_artifact_v1,
)
from discovery_flight_simulator.rfb.campaign import RFBCampaign
from discovery_flight_simulator.rfb.contracts import RFBPlanningStateV1, build_rfb_campaign_event_v1
from discovery_flight_simulator.rfb.execution import RFBExecutionService
from discovery_flight_simulator.rfb.oracle import RFBZeroOracleAdapter
from discovery_flight_simulator.rfb.policies import FixedGridRFBPolicy
from discovery_flight_simulator.rfb.scenario import load_rfb_scenario
from discovery_flight_simulator.rfb.store import SQLiteRFBCampaignStore


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "rfbzero_cell_v0.json"
_COMMITMENT_KEY = b"rfb-artifact-test-commitment-key"


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")


def _loaded():
    return load_rfb_scenario(SCENARIO_PATH, private_commitment_key=_COMMITMENT_KEY)


def _recommendation(store: SQLiteRFBCampaignStore, campaign_id: str):
    state = store.get_campaign(campaign_id)
    planning_state = RFBPlanningStateV1(
        scenario=store.public_scenario(campaign_id),
        event_head_sha256=store.events(campaign_id)[-1].event_sha256,
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


def _executing_campaign(tmp_path: Path) -> tuple[SQLiteRFBCampaignStore, str, dict[str, Any], Any]:
    loaded = _loaded()
    store = SQLiteRFBCampaignStore(tmp_path / "campaign.sqlite")
    campaign = RFBCampaign.create(
        store,
        "artifact-campaign",
        policy_id=FixedGridRFBPolicy.policy_id,
        policy_version=FixedGridRFBPolicy.policy_version,
        public_scenario=loaded.public_projection(),
        audit_timestamp="2026-07-20T12:00:00+00:00",
    )
    recommendation = _recommendation(store, campaign.campaign_id)
    pending = campaign.recommend(
        recommendation,
        expected_revision=campaign.state.revision,
        audit_timestamp="2026-07-20T12:01:00+00:00",
    )
    approved = campaign.approve(
        decision_id="approve-1",
        expected_revision=pending.revision,
        audit_timestamp="2026-07-20T12:02:00+00:00",
    )
    claim = store.claim_execution(
        campaign.campaign_id,
        decision_id="approve-1",
        expected_revision=approved.revision,
        execution_identity=loaded.execution_identity,
        now="2026-07-20T12:03:00+00:00",
        audit_timestamp="2026-07-20T12:03:00+00:00",
    )
    assert claim.claimed and claim.lease_token and claim.lease_generation
    return store, campaign.campaign_id, store.export_campaign(campaign.campaign_id), loaded


def _completed_campaign(tmp_path: Path) -> tuple[SQLiteRFBCampaignStore, str, dict[str, Any], Any]:
    loaded = _loaded()
    store = SQLiteRFBCampaignStore(tmp_path / "completed-campaign.sqlite")
    campaign = RFBCampaign.create(
        store,
        "completed-artifact-campaign",
        policy_id=FixedGridRFBPolicy.policy_id,
        policy_version=FixedGridRFBPolicy.policy_version,
        public_scenario=loaded.public_projection(),
        audit_timestamp="2026-07-20T12:00:00+00:00",
    )
    recommendation = _recommendation(store, campaign.campaign_id)
    pending = campaign.recommend(
        recommendation,
        expected_revision=campaign.state.revision,
        audit_timestamp="2026-07-20T12:01:00+00:00",
    )
    approved = campaign.approve(
        decision_id="approve-1",
        expected_revision=pending.revision,
        audit_timestamp="2026-07-20T12:02:00+00:00",
    )
    committed = RFBExecutionService(store, RFBZeroOracleAdapter()).execute(
        campaign.campaign_id,
        decision_id="approve-1",
        expected_revision=approved.revision,
        oracle_config=loaded.execution_oracle_spec,
        execution_identity=loaded.execution_identity,
        now="2026-07-20T12:03:00+00:00",
        audit_timestamp="2026-07-20T12:03:00+00:00",
    )
    assert committed["costs"] == {"attempt_cost": 1, "measurement_cost": 1}
    return store, campaign.campaign_id, store.export_campaign(campaign.campaign_id), loaded


def _refresh_manifest(manifest_path: Path, journal_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["journal.json"] = hashlib.sha256(journal_path.read_bytes()).hexdigest()
    manifest["manifest_sha256"] = sha256_json(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    _write_json(manifest_path, manifest)


def _rechain_journal(journal: dict[str, Any]) -> None:
    previous = "0" * 64
    rebuilt = []
    for sequence, event in enumerate(journal["events"]):
        rebuilt_event = build_rfb_campaign_event_v1(
            event_type=event["event_type"],
            payload=event["payload"],
            sequence=sequence,
            previous_event_sha256=previous,
        )
        rebuilt.append(rebuilt_event)
        previous = rebuilt_event["event_sha256"]
    journal["events"] = rebuilt
    journal["event_head_sha256"] = previous


def test_exports_the_exact_store_journal_and_verifies_its_semantic_replay(tmp_path: Path) -> None:
    store, campaign_id, exported, loaded = _executing_campaign(tmp_path)
    artifact_path = tmp_path / "rfb-artifact"

    verified = export_rfb_artifact_v1(
        artifact_path,
        exported,
        policy_metadata={"selection_order": "declared_candidate_order"},
        execution_identity=loaded.execution_identity,
    )

    assert set(path.name for path in artifact_path.iterdir()) == {"manifest.json", "journal.json"}
    assert verified.ranking_eligible
    assert verified.journal == exported
    assert verified.journal["events"] == store.export_campaign(campaign_id)["events"]
    assert verified.manifest["public_scenario"] == exported["campaign"]["public_scenario"]
    assert verified.manifest["utility_sha256"] == exported["campaign"]["public_scenario"]["utility_sha256"]
    assert verified.manifest["cost_model_sha256"] == exported["campaign"]["public_scenario"]["cost_model_sha256"]
    assert verified.replay.campaign == exported["campaign"]
    assert verify_rfb_artifact_v1(artifact_path) == verified


def test_exports_a_real_completed_execution(tmp_path: Path) -> None:
    _store, _campaign_id, exported, loaded = _completed_campaign(tmp_path)
    artifact_path = tmp_path / "completed-artifact"

    verified = export_rfb_artifact_v1(
        artifact_path,
        exported,
        policy_metadata={"selection_order": "declared_candidate_order"},
        execution_identity=loaded.execution_identity,
    )

    assert len(verified.journal["campaign"]["executions"]) == 1
    assert verified.journal["campaign"]["reserved_costs"] == {"attempts": 0, "measurements": 0}
    assert verify_rfb_artifact_v1(artifact_path) == verified


@pytest.mark.parametrize(
    ("name", "metadata"),
    [
        ("empty", {}),
        ("selection-order", {"selection_order": "declared_candidate_order"}),
        ("hidden-layer-count", {"hidden_layer_count": 3}),
        ("private-config-hmac", {"private_config_hmac_sha256": "a" * 64}),
        ("token-count", {"token_count": 128}),
        ("tokenizer", {"tokenizer": "byte-pair"}),
    ],
)
def test_policy_metadata_allows_explicit_public_commitments(
    tmp_path: Path, name: str, metadata: dict[str, Any]
) -> None:
    _store, _campaign_id, exported, loaded = _executing_campaign(tmp_path)

    verified = export_rfb_artifact_v1(
        tmp_path / f"metadata-{name}",
        exported,
        policy_metadata=metadata,
        execution_identity=loaded.execution_identity,
    )

    assert verified.manifest["policy"]["metadata"] == metadata


@pytest.mark.parametrize(
    "metadata",
    [
        {
            "selection_order": "declared_candidate_order",
            "hidden_layer_count": 0,
            "token_count": 0,
            "tokenizer": "byte-pair",
            "private_config_hmac_sha256": "a" * 64,
        },
        {
            "selection_order": "deterministic_public_history",
            "hidden_layer_count": 2,
            "token_count": 128,
            "tokenizer": "wordpiece",
            "private_config_hmac_sha256": "b" * 64,
        },
        {
            "selection_order": "deterministic_scalar_utility_ucb",
            "hidden_layer_count": 4,
            "token_count": 256,
            "tokenizer": "sentencepiece",
            "private_config_hmac_sha256": "c" * 64,
        },
    ],
)
def test_policy_metadata_allows_complete_public_schema(
    tmp_path: Path, metadata: dict[str, Any]
) -> None:
    _store, _campaign_id, exported, loaded = _executing_campaign(tmp_path)

    verified = export_rfb_artifact_v1(
        tmp_path / f"complete-metadata-{metadata['tokenizer']}",
        exported,
        policy_metadata=metadata,
        execution_identity=loaded.execution_identity,
    )

    assert verified.manifest["policy"]["metadata"] == metadata


@pytest.mark.parametrize(
    "key",
    [
        "privateConfigHmacSha256",
        "private-config-hmac-sha256",
        "PRIVATE_CONFIG_HMAC_SHA256",
    ],
)
def test_policy_metadata_rejects_normalized_private_commitment_aliases(
    tmp_path: Path, key: str
) -> None:
    _store, _campaign_id, exported, loaded = _executing_campaign(tmp_path)

    with pytest.raises(RFBArtifactVerificationError, match="forbidden field"):
        export_rfb_artifact_v1(
            tmp_path / "normalized-private-commitment",
            exported,
            policy_metadata={key: "a" * 64},
            execution_identity=loaded.execution_identity,
        )


@pytest.mark.parametrize(
    "metadata",
    [
        {"session_token": "RAW-SECRET"},
        {"session-token": "RAW-SECRET"},
        {"sessionToken": "RAW-SECRET"},
        {"SessionToken": "RAW-SECRET"},
        {"nested": {"bearer_token": "RAW-SECRET"}},
        {"authToken": "RAW-SECRET"},
        {"arbitrary_private_digest": "RAW-SECRET"},
        {"session_token_metadata": "RAW-SECRET"},
        {"nested": {"authTokenValue": "RAW-SECRET"}},
        {"nested": [{"bearer-token-encoded": "RAW-SECRET"}]},
    ],
)
def test_policy_metadata_rejects_secret_bearing_key_forms_without_echoing_values(
    tmp_path: Path, metadata: dict[str, Any]
) -> None:
    _store, _campaign_id, exported, loaded = _executing_campaign(tmp_path)

    with pytest.raises(RFBArtifactVerificationError, match="forbidden field") as error:
        export_rfb_artifact_v1(
            tmp_path / "secret-bearing-metadata",
            exported,
            policy_metadata=metadata,
            execution_identity=loaded.execution_identity,
        )

    assert "RAW-SECRET" not in str(error.value)


@pytest.mark.parametrize(
    "key",
    [
        "privateconfighmacsha256",
        "secretvalue",
        "privateconfigvalue",
        "raw",
        "session_token_metadata",
    ],
)
def test_policy_metadata_rejects_schema_bypasses_without_echoing_values(
    tmp_path: Path, key: str
) -> None:
    _store, _campaign_id, exported, loaded = _executing_campaign(tmp_path)

    with pytest.raises(RFBArtifactVerificationError) as error:
        export_rfb_artifact_v1(
            tmp_path / "schema-bypass",
            exported,
            policy_metadata={key: "RAW-SECRET"},
            execution_identity=loaded.execution_identity,
        )

    assert "RAW-SECRET" not in str(error.value)


@pytest.mark.parametrize(
    "metadata",
    [
        {"tokenizer": "RAW-SECRET"},
        {"unlisted": {"nested": "RAW-SECRET"}},
        {"unlisted": ["RAW-SECRET"]},
    ],
)
def test_policy_metadata_rejects_invalid_values_and_unknown_nested_data_without_echoing(
    tmp_path: Path, metadata: dict[str, Any]
) -> None:
    _store, _campaign_id, exported, loaded = _executing_campaign(tmp_path)

    with pytest.raises(RFBArtifactVerificationError) as error:
        export_rfb_artifact_v1(
            tmp_path / "invalid-policy-metadata",
            exported,
            policy_metadata=metadata,
            execution_identity=loaded.execution_identity,
        )

    assert "RAW-SECRET" not in str(error.value)


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({"private_config": {"raw": "must-not-export"}}, "forbidden field"),
        ({"lease_token": "must-not-export"}, "forbidden field"),
        ({"private_config_sha256": "a" * 64}, "forbidden field"),
        ({"private_config_hmac_sha256": "A" * 64}, "lowercase SHA-256"),
        ({"hidden_layer_count": True}, "non-negative integer"),
        ({"token_count": -1}, "non-negative integer"),
        ({"token_count": True}, "non-negative integer"),
        ({"selection_order": "non-deterministic"}, "allowed value"),
        ({"tokenizer": "whitespace"}, "allowed value"),
    ],
)
def test_policy_metadata_rejects_private_and_ambiguous_fields(
    tmp_path: Path, metadata: dict[str, Any], message: str
) -> None:
    _store, _campaign_id, exported, loaded = _executing_campaign(tmp_path)

    with pytest.raises(RFBArtifactVerificationError, match=message):
        export_rfb_artifact_v1(
            tmp_path / "rejected-metadata",
            exported,
            policy_metadata=metadata,
            execution_identity=loaded.execution_identity,
        )


def test_verifier_rejects_exact_journal_tampering_and_rehashed_semantic_tampering(tmp_path: Path) -> None:
    _store, _campaign_id, exported, loaded = _executing_campaign(tmp_path)
    artifact_path = tmp_path / "rfb-artifact"
    export_rfb_artifact_v1(
        artifact_path,
        exported,
        policy_metadata={"selection_order": "declared_candidate_order"},
        execution_identity=loaded.execution_identity,
    )

    journal_path = artifact_path / "journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["events"][1]["payload"]["recommendation"]["rationale"] = "tampered"
    _write_json(journal_path, journal)
    with pytest.raises(RFBArtifactVerificationError, match="file hash mismatch"):
        verify_rfb_artifact_v1(artifact_path)

    artifact_path = tmp_path / "semantic"
    export_rfb_artifact_v1(
        artifact_path,
        exported,
        policy_metadata={"selection_order": "declared_candidate_order"},
        execution_identity=loaded.execution_identity,
    )
    journal_path = artifact_path / "journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    started = next(event for event in journal["events"] if event["event_type"] == "execution_started")
    started["payload"]["execution"]["reserved_costs"] = {
        "attempt_cost": 0,
        "measurement_cost": 0,
    }
    _rechain_journal(journal)
    _write_json(journal_path, journal)
    _refresh_manifest(artifact_path / "manifest.json", journal_path)

    with pytest.raises(RFBArtifactVerificationError, match="reservation does not match"):
        verify_rfb_artifact_v1(artifact_path)


def test_verifier_rejects_bool_integer_terminal_snapshot_alias_after_rehash(tmp_path: Path) -> None:
    _store, _campaign_id, exported, loaded = _executing_campaign(tmp_path)
    artifact_path = tmp_path / "bool-integer-alias"
    export_rfb_artifact_v1(
        artifact_path,
        exported,
        policy_metadata={"selection_order": "declared_candidate_order"},
        execution_identity=loaded.execution_identity,
    )

    journal_path = artifact_path / "journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["campaign"]["comparison_eligible"] = int(journal["campaign"]["comparison_eligible"])
    _rechain_journal(journal)
    _write_json(journal_path, journal)
    _refresh_manifest(artifact_path / "manifest.json", journal_path)

    with pytest.raises(RFBArtifactVerificationError, match="terminal campaign state"):
        verify_rfb_artifact_v1(artifact_path)


def test_export_cleans_failed_temporary_artifact_and_allows_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _store, _campaign_id, exported, loaded = _executing_campaign(tmp_path)
    artifact_path = tmp_path / "retry-artifact"

    def fail_after_partial_write(root: Path, journal_bytes: bytes, _manifest_bytes: bytes) -> None:
        (root / "journal.json").write_bytes(journal_bytes)
        raise OSError("simulated artifact write failure")

    with monkeypatch.context() as patched:
        patched.setattr(artifact_module, "_write_artifact_files", fail_after_partial_write)
        with pytest.raises(RFBArtifactVerificationError, match="cannot write RFB artifact"):
            export_rfb_artifact_v1(
                artifact_path,
                exported,
                policy_metadata={"selection_order": "declared_candidate_order"},
                execution_identity=loaded.execution_identity,
            )

    assert not artifact_path.exists()
    assert not any(path.name.startswith(".retry-artifact.tmp-") for path in tmp_path.iterdir())

    verified = export_rfb_artifact_v1(
        artifact_path,
        exported,
        policy_metadata={"selection_order": "declared_candidate_order"},
        execution_identity=loaded.execution_identity,
    )

    assert verified.path == artifact_path
    assert verify_rfb_artifact_v1(artifact_path) == verified


def test_verifier_rejects_private_material_unexpected_files_and_strict_intervention(tmp_path: Path) -> None:
    _store, _campaign_id, exported, loaded = _executing_campaign(tmp_path)
    artifact_path = tmp_path / "rfb-artifact"
    export_rfb_artifact_v1(
        artifact_path,
        exported,
        policy_metadata={"selection_order": "declared_candidate_order"},
        execution_identity=loaded.execution_identity,
    )

    journal_path = artifact_path / "journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["private_config"] = {"must_not": "be_public"}
    _write_json(journal_path, journal)
    _refresh_manifest(artifact_path / "manifest.json", journal_path)
    with pytest.raises(RFBArtifactVerificationError, match="forbidden field"):
        verify_rfb_artifact_v1(artifact_path)

    clean_path = tmp_path / "clean"
    export_rfb_artifact_v1(
        clean_path,
        exported,
        policy_metadata={"selection_order": "declared_candidate_order"},
        execution_identity=loaded.execution_identity,
    )
    (clean_path / "extra.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(RFBArtifactVerificationError, match="missing or unexpected"):
        verify_rfb_artifact_v1(clean_path)

    strict_path = tmp_path / "strict"
    export_rfb_artifact_v1(
        strict_path,
        exported,
        policy_metadata={"selection_order": "declared_candidate_order"},
        execution_identity=loaded.execution_identity,
    )
    manifest_path = strict_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["human_intervened"] = True
    manifest["terminal_state"]["human_intervened"] = True
    manifest["manifest_sha256"] = sha256_json(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    _write_json(manifest_path, manifest)
    with pytest.raises(RFBArtifactVerificationError, match="strict benchmark artifact is unrankable"):
        verify_rfb_artifact_v1(strict_path)
