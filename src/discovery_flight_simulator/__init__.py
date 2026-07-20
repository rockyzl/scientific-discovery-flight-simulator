"""Scientific Discovery Flight Simulator.

All measurements produced by this package are simulated. The package does not
control real instruments and is not a validated scientific decision system.
"""

from .contracts import (
    CampaignEnvironment,
    Evaluator,
    ExperimentEvent,
    ExperimentRequest,
    InstrumentCapabilities,
    Observation,
    Planner,
    PublicCampaignState,
    PublicWorldSpec,
    SeedBundle,
    StopDecision,
    ValidationResult,
)
from .artifacts import (
    ArtifactVerificationError,
    VerifiedArtifactBundle,
    verify_artifact_bundle,
)
from .ledger import EvidenceLedger
from .runner import CampaignRunner
from .validator import ProtocolValidator

__all__ = [
    "CampaignEnvironment",
    "CampaignRunner",
    "Evaluator",
    "EvidenceLedger",
    "ExperimentEvent",
    "ExperimentRequest",
    "InstrumentCapabilities",
    "Observation",
    "Planner",
    "ProtocolValidator",
    "PublicCampaignState",
    "PublicWorldSpec",
    "SeedBundle",
    "StopDecision",
    "ValidationResult",
    "ArtifactVerificationError",
    "VerifiedArtifactBundle",
    "verify_artifact_bundle",
]

__version__ = "0.1.0"
