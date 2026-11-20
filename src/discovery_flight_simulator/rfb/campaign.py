"""Small campaign facade over the durable RFB workflow store."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import RFBRecommendationV1, RFBScenarioV1
from .store import CampaignState, SQLiteRFBCampaignStore


class RFBCampaign:
    """One durable RFB campaign addressed by its campaign ID."""

    def __init__(self, store: SQLiteRFBCampaignStore, campaign_id: str) -> None:
        self.store = store
        self.campaign_id = campaign_id

    @classmethod
    def create(
        cls,
        store: SQLiteRFBCampaignStore,
        campaign_id: str,
        *,
        policy_id: str,
        policy_version: str,
        public_scenario: RFBScenarioV1 | Mapping[str, Any],
        audit_timestamp: str | None = None,
    ) -> "RFBCampaign":
        store.create_campaign(
            campaign_id,
            policy_id=policy_id,
            policy_version=policy_version,
            public_scenario=public_scenario,
            audit_timestamp=audit_timestamp,
        )
        return cls(store, campaign_id)

    @classmethod
    def resume(cls, store: SQLiteRFBCampaignStore, campaign_id: str) -> "RFBCampaign":
        """Return a campaign only after the store has verified its durable journal."""

        store.get_campaign(campaign_id)
        return cls(store, campaign_id)

    @classmethod
    def open(cls, path: str | Path, campaign_id: str) -> "RFBCampaign":
        """Open a SQLite journal and resume one verified campaign."""

        return cls.resume(SQLiteRFBCampaignStore(path), campaign_id)

    @property
    def state(self) -> CampaignState:
        return self.store.get_campaign(self.campaign_id)

    def recommend(
        self,
        recommendation: RFBRecommendationV1 | Mapping[str, Any],
        *,
        expected_revision: int,
        recommendation_id: str | None = None,
        audit_timestamp: str | None = None,
    ) -> CampaignState:
        return self.store.save_recommendation(
            self.campaign_id,
            recommendation,
            expected_revision=expected_revision,
            recommendation_id=recommendation_id,
            audit_timestamp=audit_timestamp,
        )

    def approve(
        self,
        *,
        decision_id: str,
        expected_revision: int,
        reviewer_id: str | None = None,
        audit_timestamp: str | None = None,
    ) -> CampaignState:
        return self.store.approve(
            self.campaign_id,
            decision_id=decision_id,
            expected_revision=expected_revision,
            reviewer_id=reviewer_id,
            audit_timestamp=audit_timestamp,
        )

    def approve_with_edit(
        self,
        edited_recommendation: RFBRecommendationV1 | Mapping[str, Any],
        *,
        decision_id: str,
        expected_revision: int,
        recommendation_id: str | None = None,
        reviewer_id: str | None = None,
        audit_timestamp: str | None = None,
    ) -> CampaignState:
        return self.store.approve_with_edit(
            self.campaign_id,
            edited_recommendation,
            decision_id=decision_id,
            expected_revision=expected_revision,
            recommendation_id=recommendation_id,
            reviewer_id=reviewer_id,
            audit_timestamp=audit_timestamp,
        )

    def reject(
        self,
        *,
        decision_id: str,
        reason_code: str,
        expected_revision: int,
        reviewer_id: str | None = None,
        audit_timestamp: str | None = None,
    ) -> CampaignState:
        return self.store.reject(
            self.campaign_id,
            decision_id=decision_id,
            reason_code=reason_code,
            expected_revision=expected_revision,
            reviewer_id=reviewer_id,
            audit_timestamp=audit_timestamp,
        )

    def abort(
        self,
        *,
        decision_id: str,
        reason_code: str,
        expected_revision: int,
        reviewer_id: str | None = None,
        audit_timestamp: str | None = None,
    ) -> CampaignState:
        return self.store.abort(
            self.campaign_id,
            decision_id=decision_id,
            reason_code=reason_code,
            expected_revision=expected_revision,
            reviewer_id=reviewer_id,
            audit_timestamp=audit_timestamp,
        )

    def record_invalid_protocol_consumption(
        self,
        *,
        expected_revision: int,
        reason_codes: Sequence[str],
        recommendation_id: str | None = None,
        audit_timestamp: str | None = None,
    ) -> CampaignState:
        return self.store.record_invalid_protocol_consumption(
            self.campaign_id,
            expected_revision=expected_revision,
            reason_codes=reason_codes,
            recommendation_id=recommendation_id,
            audit_timestamp=audit_timestamp,
        )

    def export(self) -> dict[str, Any]:
        return self.store.export_campaign(self.campaign_id)


RfbCampaign = RFBCampaign

__all__ = ["RFBCampaign", "RfbCampaign"]
