# Evaluation

## Evaluation question

Under one fixed synthetic scenario, how do the included experiment-selection policies differ in
scientific utility, resource use, constraint handling, failure recovery, and stopping behavior?

The evaluator may read private scenario truth after a campaign. The planner may not.

## Serialized v0 metrics

`summary.json.results.<planner>.metrics` contains flat, explicit fields rather than an opaque total.
For the CV world these include:

```text
mechanism_correct, predicted_mechanism, brier_score, log_loss,
initial_entropy, final_entropy, entropy_reduction, final_confidence,
attempts, measurement_cost, violations,
injected_failure_incidents, visible_failure_incidents,
failure_detection_rate, failure_recovery_rate, latent_drift_injected,
stopped_explicitly, false_stop, stop_quality,
ledger_complete, ledger_completeness, world_type
```

The microscopy transfer fixture reports its world-appropriate primary outcome, including boundary
localization error, while retaining the common costs, reliability, stop, and completeness fields.

## Interpretation

The summary reports dimensions separately:

| Dimension | What it asks |
| --- | --- |
| Hypothesis outcome | Did the final ranking identify the benchmark's hidden mechanism? |
| Uncertainty reduction | How much did the policy reduce its stated uncertainty? |
| Sample efficiency | How much executed-operation measurement cost was used? |
| Attempt efficiency | How many proposals, including rejected and failed attempts, were used? |
| Constraint safety | How many invalid requests were proposed or blocked? |
| Failure recovery | Did the campaign detect and respond to injected instrument failures? |
| Evidence consistency | Are conclusions traceable to successful observations? |
| Stopping quality | Did the policy stop only when the scenario's evidence criterion was met? |
| Reproducibility | Does the same frozen configuration reproduce the same artifact identity? |

An overall score, if added later, must not replace these component metrics. Different applications
may assign different values to cost, safety, and information gain.

## Fairness checks

A valid comparison and artifact bundle requires automated checks that:

- all planners reference the same scenario and public specification;
- world, noise, and failure seeds match;
- budgets and cost rules match;
- hidden truth is absent from planner-visible state;
- summary metrics can be recomputed from the ledgers; and
- a failure is charged consistently across planners.

The local demo server calls the core bundle verifier before serving. A modified manifest, summary,
ledger, hash, scenario identity, or commitment makes startup fail rather than displaying an
untrusted comparison.

A comparison that fails one of these checks should be marked invalid rather than ranked.

## Reading the result

The expected-information-gain planner is not assumed to win. If a fixed grid or random policy is
equally effective at lower complexity, that is a meaningful result. A planner performing well on
this one emulator does not demonstrate causal understanding or transfer to real electrochemistry.

The microscopy fixture tests software interface transfer only. It is not evidence that performance
or scientific reasoning transfers between domains.
