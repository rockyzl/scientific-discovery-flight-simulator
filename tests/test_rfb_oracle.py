from __future__ import annotations

from dataclasses import asdict

import pytest

pytest.importorskip("rfbzero")

from discovery_flight_simulator.rfb import oracle
from discovery_flight_simulator.rfb.contracts import (
    FrozenScalarUtilityV1,
    RFBActionV1,
    RFBOutcomeV1,
)
from discovery_flight_simulator.rfb.oracle import (
    ADAPTER_ID,
    ADAPTER_VERSION,
    REDUCER_ID,
    REDUCER_VERSION,
    RFBZeroOracleAdapter,
    RFBZeroOracleConfig,
)
from discovery_flight_simulator.rfb.utility import score_outcome


# Test-owned known RFBzero 1.0.1 model inputs. The scenario's private oracle
# configuration is still a placeholder and must not be loaded into this test.
MODEL_PARAMETERS = {
    "volume_cls": 0.005,
    "volume_ncls": 0.010,
    "c_ox_cls": 0.005,
    "c_red_cls": 0.005,
    "c_ox_ncls": 0.005,
    "c_red_ncls": 0.005,
    "ocv_50_soc": 1.0,
    "resistance": 0.5,
    "k_0_cls": 1e-3,
    "k_0_ncls": 1e-3,
    "time_step": 0.1,
}
CONFIG = RFBZeroOracleConfig(
    MODEL_PARAMETERS,
    capacity_reference_C=4.824,
    charge_first=False,
)
ACTION = RFBActionV1(
    charge_current_A=0.10,
    discharge_current_A=-0.08,
    charge_voltage_limit_V=1.5,
    discharge_voltage_limit_V=0.5,
    protocol_duration_s=240.0,
)
UTILITY = FrozenScalarUtilityV1(energy_reference_J=10.0, duration_reference_s=240.0)


def test_rfbzero_execution_returns_a_scoreable_canonical_complete_outcome() -> None:
    outcome = RFBZeroOracleAdapter().execute(CONFIG, ACTION)

    assert isinstance(outcome, RFBOutcomeV1)
    assert outcome.status == "complete"
    assert outcome.provenance == "simulated"
    assert outcome.qc_flags == ()
    assert outcome.delivered_discharge_energy_J is not None
    assert outcome.delivered_discharge_energy_J > 0.0
    assert outcome.round_trip_efficiency is not None
    assert outcome.capacity_retention is not None
    assert outcome.elapsed_duration_s == 240.0
    assert score_outcome(outcome, UTILITY) > UTILITY.invalid_result_utility
    assert score_outcome(RFBOutcomeV1("failed", None, None, None, None), UTILITY) == (
        UTILITY.invalid_result_utility
    )


def test_canonical_action_and_its_serialized_form_are_deterministic_and_fresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed_models: list[object] = []
    real_zero_d_model = oracle.ZeroDModel

    def construct_model(**kwargs: object) -> object:
        model = real_zero_d_model(**kwargs)
        constructed_models.append(model)
        return model

    monkeypatch.setattr(oracle, "ZeroDModel", construct_model)
    adapter = RFBZeroOracleAdapter()

    first = adapter.execute(CONFIG, ACTION)
    second = adapter.execute(CONFIG, ACTION.to_dict())

    assert asdict(first) == asdict(second)
    assert len(constructed_models) == 2
    assert constructed_models[0] is not constructed_models[1]
    assert not hasattr(first, "results")
    assert not hasattr(first, "cell_model")


def test_invalid_canonical_action_is_rejected_without_constructing_a_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed = False

    def should_not_construct(**_kwargs: object) -> object:
        nonlocal constructed
        constructed = True
        raise AssertionError("invalid action reached RFBzero")

    monkeypatch.setattr(oracle, "ZeroDModel", should_not_construct)
    invalid_action = {**ACTION.to_dict(), "charge_current_A": 0.0}

    outcome = RFBZeroOracleAdapter().execute(CONFIG, invalid_action)

    assert outcome == RFBOutcomeV1(
        status="invalid",
        delivered_discharge_energy_J=None,
        round_trip_efficiency=None,
        capacity_retention=None,
        elapsed_duration_s=None,
        qc_flags=("rfbzero_invalid_input:ValueError",),
    )
    assert not constructed


def test_partial_and_unexpected_rfbzero_end_conditions_have_stable_canonical_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PartialResults:
        steps = 1
        time_step = 1.0
        step_time = [1.0]
        step_is_charge = [True]
        current = [0.1]
        cell_v = [1.1]
        half_cycle_is_charge: list[bool] = []
        half_cycle_capacity: list[float] = []
        half_cycle_time: list[float] = []
        end_status = "TIME_DURATION_REACHED"

    class FailedResults(PartialResults):
        end_status = "LOW_CAPACITY"

    class FakeProtocol:
        result: object = PartialResults()

        def __init__(self, **_kwargs: object) -> None:
            pass

        def run(self, **_kwargs: object) -> object:
            return self.result

    monkeypatch.setattr(oracle, "ZeroDModel", lambda **_kwargs: object())
    monkeypatch.setattr(oracle, "ConstantCurrent", FakeProtocol)

    partial = RFBZeroOracleAdapter().execute(CONFIG, ACTION)
    assert partial == RFBOutcomeV1(
        status="invalid",
        delivered_discharge_energy_J=None,
        round_trip_efficiency=None,
        capacity_retention=None,
        elapsed_duration_s=1.0,
        qc_flags=("rfbzero_partial_execution",),
    )

    FakeProtocol.result = FailedResults()
    failed = RFBZeroOracleAdapter().execute(CONFIG, ACTION)
    assert failed == RFBOutcomeV1(
        status="failed",
        delivered_discharge_energy_J=None,
        round_trip_efficiency=None,
        capacity_retention=None,
        elapsed_duration_s=1.0,
        qc_flags=("rfbzero_end_status:low_capacity",),
    )


def test_engine_exception_and_manifest_identity_are_project_owned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_from_model(**_kwargs: object) -> object:
        raise RuntimeError("synthetic engine error")

    monkeypatch.setattr(oracle, "ZeroDModel", raise_from_model)

    outcome = RFBZeroOracleAdapter().execute(CONFIG, ACTION)
    identity = RFBZeroOracleAdapter.manifest_identity()

    assert outcome == RFBOutcomeV1(
        status="failed",
        delivered_discharge_energy_J=None,
        round_trip_efficiency=None,
        capacity_retention=None,
        elapsed_duration_s=None,
        qc_flags=("rfbzero_exception:RuntimeError",),
    )
    assert identity["adapter_id"] == ADAPTER_ID
    assert identity["adapter_version"] == ADAPTER_VERSION
    assert identity["reducer_id"] == REDUCER_ID
    assert identity["reducer_version"] == REDUCER_VERSION
    assert set(identity["runtime_dependencies"]) == {"python", "numpy", "scipy", "rfbzero"}
