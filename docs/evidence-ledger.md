# Evidence ledger

## Why a ledger exists

A final accuracy number cannot explain whether a planner violated a constraint, encountered a
failure, retried responsibly, or stopped for a defensible reason. Each planner therefore produces an
ordered ledger that is both the replay source and the evaluator's campaign record.

## Serialized v0 shape

Ledger schema version `1` has these top-level fields:

```text
schema_version, provenance, world, planner, seeds,
scenario_identity, completion_status, events, ledger_sha256
```

`world` is the exact public world specification. `planner` contains `name` and `version`. `seeds`
contains only `planner_seed` and HMAC commitments for the private world/noise/failure seeds.
`scenario_identity` carries the scenario commitment, version, and reproducibility identity.
`completion_status` is exactly `stopped`, `budget_exhausted`, or `incomplete`.

Each event has exactly these top-level fields:

```text
sequence, request, stop, validation, observation,
beliefs_before, beliefs_after, costs, hashes
```

An event contains exactly one of `request` or `stop`. A stop event has no validation or observation.
If a campaign exhausts its budget, its ledger can end without an explicit stop event; completion is
then determined from cumulative costs and the public world budgets.

## Event meaning

An event records, as applicable:

- `sequence`, the zero-based event index;
- `request`, containing `request_id`, `operation`, numeric `controls`, and `rationale`, or `stop`,
  containing `reason`, `final_hypothesis`, and `confidence`;
- `validation`, containing `accepted`, `reasons`, `attempt_cost`, and `measurement_cost` for request
  events;
- `observation`, containing `status`, `requested_controls`, `executed_controls`, `value`,
  `standard_error`, `qc_flags`, the two operation costs, and `provenance`, when an operation executes;
- `beliefs_before` and `beliefs_after`, the public hypothesis-score mappings;
- `costs`, containing per-event and cumulative attempt/measurement costs; and
- `hashes.previous` and `hashes.event`, forming the append-only event chain.

The ledger does not persist the full `PublicCampaignState`, explicit unit fields, instrument state,
a recovery-action field, or remaining-budget fields. The UI derives remaining budget from public
world totals minus cumulative costs. The evaluator derives failure incidents, detection rate,
recovery rate, violations, and stopping-quality metrics from the event sequence; those fields live in
`summary.json.results.<planner>.metrics`, not in the ledger.

## Required status language

Replay status is conveyed with text, not color alone. The UI derives labels such as:

- `PROPOSED`
- `ACCEPTED`
- `BLOCKED`
- `MEASUREMENT_SUCCEEDED`
- `MEASUREMENT_FAILED`
- `STOPPED`

An absent observation must never be rendered as a numeric zero. `observation.status` is `ok` or
`failed`; a failed operation must remain a failure event and must not silently become training
evidence. `measurement` cost is charged for any executed instrument operation, including calibration
and failed operations. Rejected requests consume attempt cost but no measurement cost.

## Provenance and integrity

Every ledger is labeled `provenance: simulated`. `ledger_sha256` covers the ledger payload, while
each event is chained to the preceding event hash. The manifest binds the serialized files to the
same scenario, versions, seeds, and run identity through file hashes. Server startup verifies the
entire bundle before exposing it. Hashes detect changes; they are not a digital signature and do not
prove who created an artifact.

## Hidden information

The ledger contains what the planner observed and did. It must not contain future failures, private
world parameters, or noiseless answers. If benchmark truth is published, its only artifact location
is `summary.json.post_run_reveal`, produced after all evaluations complete. The demo does not search
the ledger or manifest for truth-like fields.

## Replay versus rerun

- **Replay** renders the frozen event sequence already stored in a ledger.
- **Rerun** executes a new campaign from a frozen configuration in a new output directory.

The web demo performs replay only. This distinction prevents an animation of saved events from being
misrepresented as a live experiment.
