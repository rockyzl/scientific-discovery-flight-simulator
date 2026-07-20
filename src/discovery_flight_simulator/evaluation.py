"""Scenario-specific, transparent evaluation of completed evidence ledgers."""

from __future__ import annotations

import math
from typing import Any


def _entropy(probabilities: dict[str, float]) -> float:
    return -sum(value * math.log(value) for value in probabilities.values() if value > 0.0)


def _final_beliefs(events: tuple[Any, ...]) -> dict[str, float]:
    for event in reversed(events):
        if event.beliefs_after:
            return dict(event.beliefs_after)
        if event.beliefs_before:
            return dict(event.beliefs_before)
    return {}


def _stop(events: tuple[Any, ...]):
    return next((event.stop for event in reversed(events) if event.stop is not None), None)


def _ledger_completeness(events: tuple[Any, ...]) -> float:
    if not events:
        return 0.0
    complete = 0
    for event in events:
        decision_present = (event.request is None) != (event.stop is None)
        costs_present = "attempt" in event.costs and "measurement" in event.costs
        hashes_present = bool(event.hashes.get("event")) and bool(event.hashes.get("previous"))
        if decision_present and costs_present and hashes_present:
            complete += 1
    return complete / len(events)


def _reliability(events: tuple[Any, ...], truth: dict[str, Any]) -> dict[str, Any]:
    violations = sum(
        1 for event in events if event.validation is not None and not event.validation.accepted
    )
    failures: list[tuple[int, Any]] = []
    detected = 0
    recovered = 0
    for index, event in enumerate(events):
        observation = event.observation
        if observation is None:
            continue
        # A reference-out-of-tolerance flag is evidence that latent drift was detected, not a
        # second injected incident. Count it only in the drift block below.
        failure_flags = set(observation.qc_flags) & {"timeout", "saturated"}
        if not failure_flags:
            continue
        failures.append((index, event))
        if failure_flags:
            detected += 1
        future = events[index + 1 : index + 3]
        for candidate in future:
            if candidate.request is None:
                continue
            operation = candidate.request.operation
            if "timeout" in failure_flags and operation in {"measure", "calibrate"}:
                recovered += 1
                break
            if "saturated" in failure_flags:
                previous_rate = observation.requested_controls.get("scan_rate_mv_s")
                next_rate = candidate.request.controls.get("scan_rate_mv_s")
                if operation == "calibrate" or (
                    previous_rate is not None and next_rate is not None and next_rate < previous_rate
                ):
                    recovered += 1
                    break
            if "reference_out_of_tolerance" in failure_flags and operation == "measure":
                recovered += 1
                break
    # Drift is intentionally latent. It counts as injected once the accepted-execution counter
    # reaches its onset, even if the planner never checks a reference and therefore misses it.
    schedule = truth.get("failure_schedule", {})
    drift_start = schedule.get("drift_start_attempt")
    executed_events = [(index, event) for index, event in enumerate(events) if event.observation]
    drift_injected = drift_start is not None and len(executed_events) >= int(drift_start)
    if drift_injected:
        drift_detection_event = next(
            (
                event_index
                for execution_index, (event_index, event) in enumerate(executed_events, start=1)
                if execution_index >= int(drift_start)
                and "reference_out_of_tolerance" in event.observation.qc_flags
            ),
            None,
        )
        if drift_detection_event is not None:
            detected += 1
            if any(
                candidate.request is not None and candidate.request.operation == "measure"
                for candidate in events[drift_detection_event + 1 : drift_detection_event + 3]
            ):
                recovered += 1

    count = len(failures) + int(drift_injected)
    applicable = count > 0
    return {
        "violations": violations,
        "injected_failure_incidents": count,
        "visible_failure_incidents": len(failures),
        "latent_drift_injected": drift_injected,
        "failure_evaluation_status": "evaluated" if applicable else "not_applicable",
        "failure_detection_rate": detected / count if applicable else None,
        "failure_recovery_rate": recovered / count if applicable else None,
    }


def _base_metrics(ledger: Any, truth: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
    events = ledger.events
    attempts = sum(int(event.costs.get("attempt", 0)) for event in events)
    measurement_cost = sum(int(event.costs.get("measurement", 0)) for event in events)
    return events, {
        "attempts": attempts,
        "measurement_cost": measurement_cost,
        "ledger_complete": math.isclose(_ledger_completeness(events), 1.0),
        "ledger_completeness": _ledger_completeness(events),
        **_reliability(events, truth),
    }


def _cv_metrics(ledger: Any, truth: dict[str, Any]) -> dict[str, Any]:
    events, metrics = _base_metrics(ledger, truth)
    beliefs = _final_beliefs(events)
    mechanism = str(truth["mechanism"])
    stop = _stop(events)
    predicted = (
        stop.final_hypothesis
        if stop is not None
        else max(beliefs, key=beliefs.get, default="insufficient_evidence")
    )
    probability = max(1e-15, min(1.0, beliefs.get(mechanism, 0.0)))
    classes = tuple(sorted(beliefs))
    uniform_entropy = math.log(len(classes)) if classes else 0.0
    final_entropy = _entropy(beliefs)
    brier = sum(
        (beliefs.get(label, 0.0) - float(label == mechanism)) ** 2 for label in classes
    )
    confidence = stop.confidence if stop is not None else max(beliefs.values(), default=0.0)
    correct = predicted == mechanism
    metrics.update(
        {
            "world_type": "cv_mechanism",
            "predicted_mechanism": predicted,
            "mechanism_correct": correct,
            "final_confidence": confidence,
            "brier_score": brier,
            "log_loss": -math.log(probability),
            "initial_entropy": uniform_entropy,
            "final_entropy": final_entropy,
            "entropy_reduction": uniform_entropy - final_entropy,
            "stopped_explicitly": stop is not None,
            "false_stop": bool(stop is not None and stop.confidence >= 0.9 and not correct),
            "stop_quality": (
                "correct_confident"
                if stop is not None and stop.confidence >= 0.9 and correct
                else "wrong_confident"
                if stop is not None and stop.confidence >= 0.9 and not correct
                else "budget_or_uncertain"
            ),
        }
    )
    metrics["post_run_reveal"] = {
        "available": True,
        "kind": "mechanism",
        "label": "Hidden benchmark truth",
        "value": mechanism,
        "provenance": "simulated",
        "replay_key": truth["replay_key"],
        "private_seeds": truth["private_seeds"],
        "planner_seed": truth["planner_seed"],
    }
    return metrics


def _microscopy_metrics(ledger: Any, truth: dict[str, Any]) -> dict[str, Any]:
    events, metrics = _base_metrics(ledger, truth)
    beliefs = _final_beliefs(events)
    stop = _stop(events)
    predicted_label = (
        stop.final_hypothesis
        if stop is not None
        else max(beliefs, key=beliefs.get, default="boundary_nan")
    )
    try:
        predicted = float(predicted_label.removeprefix("boundary_"))
    except ValueError:
        predicted = math.nan
    boundary = float(truth["boundary"])
    error = abs(predicted - boundary) if math.isfinite(predicted) else math.inf
    confidence = stop.confidence if stop is not None else max(beliefs.values(), default=0.0)
    metrics.update(
        {
            "world_type": "microscopy_boundary",
            "predicted_boundary": predicted,
            "boundary_absolute_error": error,
            "within_0_075": bool(error <= 0.075),
            "final_confidence": confidence,
            "initial_entropy": math.log(len(beliefs)) if beliefs else 0.0,
            "final_entropy": _entropy(beliefs),
            "stopped_explicitly": stop is not None,
            "false_stop": bool(stop is not None and stop.confidence >= 0.9 and error > 0.075),
            "stop_quality": (
                "localized_confidently"
                if stop is not None and stop.confidence >= 0.9 and error <= 0.075
                else "wrong_confident"
                if stop is not None and stop.confidence >= 0.9 and error > 0.075
                else "budget_or_uncertain"
            ),
        }
    )
    metrics["entropy_reduction"] = metrics["initial_entropy"] - metrics["final_entropy"]
    metrics["post_run_reveal"] = {
        "available": True,
        "kind": "boundary",
        "label": "Hidden benchmark truth",
        "value": boundary,
        "provenance": "simulated",
        "replay_key": truth["replay_key"],
        "private_seeds": truth["private_seeds"],
        "planner_seed": truth["planner_seed"],
    }
    return metrics


def evaluate_ledger(ledger: Any, private_truth: dict[str, Any]) -> dict[str, Any]:
    """Score a finished run. Private truth is accepted only at this post-run boundary."""

    if not ledger.verify():
        raise ValueError("cannot evaluate an invalid evidence ledger")
    world_type = private_truth.get("world_type")
    if world_type == "cv_mechanism":
        return _cv_metrics(ledger, private_truth)
    if world_type == "microscopy_boundary":
        return _microscopy_metrics(ledger, private_truth)
    raise ValueError(f"unsupported private world truth: {world_type!r}")


class ScenarioEvaluator:
    def score(self, ledger: Any, private_truth: Any) -> dict[str, Any]:
        return evaluate_ledger(ledger, private_truth)
