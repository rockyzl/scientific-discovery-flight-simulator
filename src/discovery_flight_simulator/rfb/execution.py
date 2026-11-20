"""The only bridge between durable RFB campaign state and RFBzero execution.

Guarantee: one logical execution and one cost can be committed for an approved
action. A process crash after simulation but before the SQLite completion
transaction may deterministically recompute the simulation, but only one result
and one cost are ever committed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .contracts import RFBActionV1, RFBOutcomeV1
from .oracle import FrozenOracleConfig, RFBZeroOracleAdapter
from .store import ExecutionLeaseError, SQLiteRFBCampaignStore
from .utility import utility_record_for_outcome


class RFBOracleExecutor(Protocol):
    """Minimal adapter surface used by the durable execution bridge."""

    def execute(self, config: FrozenOracleConfig, action: RFBActionV1) -> RFBOutcomeV1:
        """Run one deterministic simulated action."""


@dataclass
class RFBExecutionService:
    """Claim, simulate, derive utility, and commit a single approved action."""

    store: SQLiteRFBCampaignStore
    oracle: RFBOracleExecutor

    def execute(
        self,
        campaign_id: str,
        *,
        decision_id: str,
        expected_revision: int,
        oracle_config: FrozenOracleConfig,
        execution_identity: Mapping[str, Any],
        lease_ttl_seconds: int = 300,
        now: str | None = None,
        audit_timestamp: str | None = None,
    ) -> dict[str, Any]:
        claim = self.store.claim_execution(
            campaign_id,
            decision_id=decision_id,
            expected_revision=expected_revision,
            execution_identity=execution_identity,
            lease_ttl_seconds=lease_ttl_seconds,
            now=now,
            audit_timestamp=audit_timestamp,
        )
        if claim.completed:
            assert claim.execution is not None
            return claim.execution
        if not claim.claimed or claim.lease_token is None or claim.lease_generation is None:
            raise ExecutionLeaseError("an active worker already owns this logical execution")

        action = RFBActionV1.from_dict(claim.action)
        outcome = self.oracle.execute(oracle_config, action)
        # This is deliberately derived before completion; the store independently
        # recomputes it and never accepts a caller-supplied scalar utility.
        utility_record = utility_record_for_outcome(outcome, self.store.public_scenario(campaign_id).utility)
        committed = self.store.complete_execution(
            campaign_id,
            decision_id=decision_id,
            action=action,
            outcome=outcome,
            lease_token=claim.lease_token,
            lease_generation=claim.lease_generation,
            audit_timestamp=audit_timestamp,
        )
        if committed["utility_record"] != utility_record.to_dict():
            raise ExecutionLeaseError("committed utility record does not match the canonical derivation")
        return committed


def execute_approved_action(
    store: SQLiteRFBCampaignStore,
    campaign_id: str,
    *,
    decision_id: str,
    expected_revision: int,
    oracle_config: FrozenOracleConfig,
    execution_identity: Mapping[str, Any],
    oracle: RFBOracleExecutor | None = None,
    lease_ttl_seconds: int = 300,
    now: str | None = None,
    audit_timestamp: str | None = None,
) -> dict[str, Any]:
    """Execute one approved action through the durable lease protocol."""

    return RFBExecutionService(store, oracle or RFBZeroOracleAdapter()).execute(
        campaign_id,
        decision_id=decision_id,
        expected_revision=expected_revision,
        oracle_config=oracle_config,
        execution_identity=execution_identity,
        lease_ttl_seconds=lease_ttl_seconds,
        now=now,
        audit_timestamp=audit_timestamp,
    )


execute_campaign_action = execute_approved_action

__all__ = [
    "RFBExecutionService",
    "RFBOracleExecutor",
    "execute_approved_action",
    "execute_campaign_action",
]
