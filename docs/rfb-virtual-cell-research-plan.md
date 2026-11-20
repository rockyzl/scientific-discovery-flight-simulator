# Virtual RFB Cell Campaign: architecture record

**Status:** active build, 2026-07-20. This document records decided architecture
only; it does not mark in-progress route, orchestration, artifact, or replay
integration as complete.

## Scope and non-claims

The campaign is a deterministic simulated 0D redox-flow-battery (RFB) virtual
cell benchmark. It compares a constrained BO policy with paired deterministic
random and fixed-grid policies under one frozen scenario. A human must record a
decision before an approved virtual-cell action can run.

It is not a digital twin, laboratory measurement, calibrated physical model,
autonomous laboratory, self-driving laboratory, hardware controller, or basis
for chemical, laboratory, engineering, or operational decisions. It makes no
claim that a policy generalizes beyond its frozen simulated scenario.

## Frozen V1 experiment contract

- `rfbzero==1.0.1` supplies deterministic simulated numerical outcomes through
  the project adapter. It is not exposed as a public RFBzero API or a claim of
  calibration.
- The public scenario is `rfbzero_cell_v0`, with `provenance: simulated` and
  `model_dimension: 0D`.
- Every action serializes exactly, and in this order:
  `charge_current_A`, `discharge_current_A`, `charge_voltage_limit_V`,
  `discharge_voltage_limit_V`, and `protocol_duration_s`.
- V1 varies only `charge_current_A` and `discharge_current_A`. The voltage
  limits and duration are scenario-fixed but remain present in every action.
- The public candidate set, validator envelope, candidate identities, action
  order, budgets, cost model, and utility configuration are frozen with the
  campaign. An action outside the declared candidate set is not executable.
- A valid execution costs one attempt and one measurement. An invalid protocol
  consumes one attempt and zero measurements. Review decisions themselves do
  not consume either cost.

The utility is a single public scalar, not a Pareto objective:

```text
0.45 * clip(delivered_discharge_energy_J / energy_reference_J)
+ 0.25 * clip(round_trip_efficiency)
+ 0.20 * clip(capacity_retention)
- 0.10 * clip(elapsed_duration_s / duration_reference_s)
```

Complete scoreable outcomes range from `-0.10` to `0.90`. Failed, invalid,
QC-flagged, missing, non-finite, or not-applicable outcomes persist `-1.0` with
the canonical outcome and QC record; values are never imputed.

## Architecture and data boundary

SQLite stores the authoritative RFB campaign state, canonical journal, event
chain, decisions, executions, costs, and private execution leases. LangGraph
and the SQLite checkpointer orchestrate durable recommend -> interrupt for human
review -> resume; they do not own campaign truth and cannot override SQLite.
No LLM planner, hardware driver, network action, or laboratory control path is
part of the RFB workflow.

Planners receive only public scenario data, completed public outcomes, rejected
action identities, current event head, revision, and remaining public budgets.
Private oracle parameters, execution identities, lease tokens, worker state,
and checkpoint internals are not planner-visible or exported as public campaign
state. Public records retain simulated provenance, immutable identities,
recommendations, decisions, outcomes, utility records, costs, and logical event
hashes.

The durable state progression is:

```text
awaiting_recommendation -> awaiting_review -> approved -> executing
executing -> awaiting_recommendation
awaiting_review -> awaiting_recommendation  (reject)
awaiting_review -> awaiting_review          (approve_with_edit)
awaiting_review -> aborted                  (abort)
```

An unchanged `approve` records a decision only. It cannot invoke RFBzero or
spend an execution cost. `resume` is the only workflow entry that may claim the
approved action, run the deterministic oracle, derive utility, and commit the
single logical execution.

Strict benchmark mode starts every campaign as ranking-eligible. Any
`approve_with_edit` or `reject` records human intervention, changes the campaign
to `workflow_case_study`, and makes the comparison unrankable. There is no
partial policy ranking after intervention.

## Reproducibility

Every record is bound to the public scenario/candidate/utility identities,
policy and version, campaign revision, event-chain head, action identity,
decision identity, canonical outcome, utility record, and cost record. The
execution identity separately pins the adapter and dependency environment,
including `rfbzero==1.0.1`.

Replay is logical: it verifies the identity and event chain, then applies the
captured decision records to deterministic simulation. Timestamps are audit
metadata only and are excluded from event-content hashes. A changed timestamp
must not change a logical event hash; any changed canonical content, prior hash,
or identity must fail verification.

The exact planned browser API, response/error shapes, state authority, and
acceptance criteria are in [the workflow contract](decisions/rfb-workflow-contract.md).

## Remaining work

- Finish and verify the RFB domain, validation, oracle, policies, SQLite store,
  and execution claim/commit integration currently in progress.
- Wire the canonical HTTP routes and LangGraph SQLite pause/resume flow without
  making the checkpointer authoritative.
- Integrate the separately owned RFB artifact and replay implementation.
- Demonstrate route, restart, concurrency, public/private-boundary, and replay
  acceptance criteria before claiming the campaign workflow complete.
