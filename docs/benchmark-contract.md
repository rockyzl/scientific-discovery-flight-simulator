# Benchmark contract

## Comparison rule

Every planner in one comparison receives the same:

- public world specification and initial observations;
- attempt and measurement budgets;
- experiment constraints and instrument capabilities;
- condition-indexed noise schedule;
- attempt-indexed failure schedule;
- success and stopping definitions; and
- private hidden world, which is visible only to the environment and evaluator.

Only the planner policy and planner seed may differ. This is a paired simulated comparison, not a
comparison of unrelated runs.

## Frozen v0 campaign

The flagship scenario asks a planner to choose CV scan rates to distinguish a synthetic hidden
mechanism:

- diffusion-like response proportional to the square root of scan rate;
- surface-like response proportional to scan rate; or
- a mixed response composed from both terms.

These equations form a transparent teaching emulator. They are not a complete electrochemical cell
model and have not been validated as a predictive model for a particular material or instrument.

The included planners are:

- `random`: sample a valid action using its isolated planner RNG;
- `fixed_grid`: follow a predetermined log-spaced design; and
- `information_gain`: choose the valid action with the highest expected reduction in uncertainty
  under the emulator's candidate hypotheses.

No LLM is used or claimed.

## Cost semantics

Attempt cost and measurement cost remain separate:

| Outcome | Attempt cost | Measurement cost | Observation returned |
| --- | ---: | ---: | --- |
| Validator rejects request | 1 | 0 | No |
| Executed operation fails | 1 | 1 | Failure observation only |
| Executed calibration succeeds | 1 | 1 | Simulated calibration observation |
| Executed measurement succeeds | 1 | 1 | Simulated measurement |
| Planner stops | 0 | 0 | Stop decision |

A rejected request therefore cannot be used to search constraints for free. Measurement cost means
an executed instrument operation, including calibration and failed operations; it does not mean only
a successful scientific measurement.

## Randomness contract

Randomness is split into explicit seeds for:

- world selection or private parameters;
- observation noise;
- instrument failures; and
- each stochastic planner.

Noise is keyed by requested condition, and failures are keyed by attempt index. One planner's extra
RNG calls must not change another planner's observations or failure schedule.

## Hidden-state contract

`PublicCampaignState` never contains hidden truth, future schedules, or evaluator fields. The
manifest may identify the scenario and commitment hash, but the public planner input must not carry
private truth. After all evaluations complete, the final summary may contain the only public reveal
payload:

```json
{
  "post_run_reveal": {
    "available": true,
    "kind": "mechanism",
    "label": "Hidden benchmark truth",
    "value": "diffusion",
    "provenance": "simulated",
    "replay_key": "<private replay key>",
    "private_seeds": {
      "world_seed": 1701,
      "noise_seed": 2718,
      "failure_seed": 3141
    },
    "planner_seed": 5772
  }
}
```

`post_run_reveal` never appears in a ledger, manifest, or planner-visible state. The browser keeps
it concealed until all artifacts load, every campaign has either stopped or exhausted its budget,
and the visitor explicitly selects reveal.

## Artifact contract

The CLI writes to a new directory and refuses to overwrite it:

```text
manifest.json
summary.json
ledgers/random.json
ledgers/fixed_grid.json
ledgers/information_gain.json
```

Each file declares `provenance: simulated`, schema and component versions, a public planner seed,
private-seed commitments, and integrity hashes. The completed reveal contains the replay key and
private seeds that open those commitments. The manifest binds the summary and ledgers by file hashes; the summary binds
each result to its ledger payload hash. Metrics remain separate rather than being collapsed into one
unexplained leaderboard score.
