# Scientific Discovery Flight Simulator

**Test how a scientific agent chooses the next useful experiment, updates competing explanations,
and stops under a fixed synthetic budget.**

> **SIMULATED RUN — NOT A LAB MEASUREMENT.** This statement applies to the diagnosis and policy
> benchmark surfaces. A separately labeled chart uses cited, published experimental CV data.

This repository is an offline, deterministic research prototype for replaying scientific campaigns.
Its flagship world is a closed-loop cyclic-voltammetry (CV) diagnosis benchmark: an agent must
distinguish five predefined explanations for enlarged apparent peak separation by selecting
experiments under fixed attempt and measurement budgets. The server returns full synthetic CV
curves or explicit failures, updates a five-hypothesis belief vector, recommends the next action,
and records an auditable evidence ledger.

The earlier random, fixed-grid, and expected-information-gain scan-rate comparison remains below
the flagship loop as a separate policy-replay teaching example.

## The one honest claim

This project can test the included closed-loop diagnosis policy and compare the included
experiment-selection policies under fixed synthetic benchmark contracts. It records every proposal,
validation decision, simulated observation, QC flag, cost, belief update, and stopping decision.
Failure-detection and recovery behavior can therefore be inspected and repeated.

It does **not** show that an agent can make discoveries in a real laboratory. It does not control
instruments, generate laboratory measurements, validate a mechanistic CV model, or establish general
scientific reasoning.

The restricted-v1 Gaussian likelihood model is intentionally narrow and can produce an extremely
sharp posterior after one synthetic observation. Those values are working beliefs inside five
predefined toy hypotheses, not calibrated confidence about a real electrochemical system.

## What the demo shows

The browser demo serves a private local campaign state plus a completed artifact directory and a
bundled, cited real-data reference. It does not control an instrument or run a laboratory
experiment.

1. Start from one visible scientific question: why did apparent CV peak separation grow relative to
   a frozen healthy/control comparator?
2. Compare five predefined synthetic explanations and see the remaining operation and attempt
   budgets.
3. Run the server-recommended experiment, inspect a complete 122-point synthetic CV or an explicit
   failure, and see how the evidence changes the working beliefs.
4. Follow every experiment, failure, cost, belief update, and stopping decision in the campaign
   timeline and expert audit view.
5. Reveal the hidden synthetic cause only after the campaign is terminal and verify it against the
   original cryptographic commitment.
6. Inspect three published all-iron RFB anolyte CV curves and play the physical sample-change and
   measurement workflow step by step in the separate real-context section.
7. Compare `random`, `fixed_grid`, and `information_gain` in the separate saved policy replay.

See [the demo guide](docs/demo-guide.md) for how to interpret the page.

## Quickstart

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

python -m discovery_flight_simulator.cli compare \
  --scenario scenarios/cv_mechanism_v0.json \
  --output outputs/cv-demo

python demo/serve.py --artifacts outputs/cv-demo
```

Open <http://127.0.0.1:8000>. The server exposes the static demo, files beneath the selected artifact
directory, and a local closed-loop diagnosis API. Diagnosis state is stored outside the public
artifact directory, and routed API responses use `Cache-Control: no-store`.

Expected artifacts:

```text
outputs/cv-demo/
├── manifest.json
├── summary.json
└── ledgers/
    ├── random.json
    ├── fixed_grid.json
    └── information_gain.json
```

## Architecture at a glance

```text
public diagnosis state ──> recommendation policy ──> protocol validator
                                                       │
                                                       ▼
private committed truth ──> synthetic lab world ──> observation / failure
          │                                                   │
          └──────── belief update + stop rule <── evidence ledger
```

The diagnosis UI receives only public campaign state. The hidden cause, simulator seeds, reveal
nonce, and future failure schedule remain server-side until an explicit post-terminal reveal. The
older planner comparison follows the same public/private separation. See
[the closed-loop diagnosis contract](docs/design/closed-loop-diagnosis-contract.md),
[architecture](docs/architecture.md), and the earlier [benchmark contract](docs/benchmark-contract.md).

## Reproduce and inspect

Every output carries `provenance: simulated`, versions, a public planner seed, private-seed
commitments, and hashes. Private world/noise/failure seeds and their replay key are confined to the
completed post-run reveal. The CLI refuses to overwrite an existing output directory.

The default command generates a new private replay key on every run, so two default invocations are
not expected to produce byte-identical artifacts. For an exact replay, first create the original:

```bash
python -m discovery_flight_simulator.cli compare \
  --scenario scenarios/cv_mechanism_v0.json \
  --output outputs/original
```

Then copy `post_run_reveal.replay_key` from `outputs/original/summary.json` and use that revealed key
with a new output directory:

```bash
python -m discovery_flight_simulator.cli compare \
  --scenario scenarios/cv_mechanism_v0.json \
  --output outputs/exact-replay \
  --private-seed-key '<revealed-key>'
```

See [reproducibility](docs/reproducibility.md) for the environment and verification boundaries.

## Project boundary

This repository owns stateful simulated worlds, sequential experiment selection, campaign budgets,
failure injection, and fair planner comparison. It remains separate from
[`scientific-agent-lab`](https://github.com/rockyzl/scientific-agent-lab), which evaluates evidence,
assumptions, uncertainty, review, and reproducibility in scientific reports. A future export adapter
could connect their artifacts; v0 has no runtime dependency.

## Documentation

- [Architecture](docs/architecture.md)
- [Benchmark contract](docs/benchmark-contract.md)
- [Evidence ledger](docs/evidence-ledger.md)
- [Evaluation](docs/evaluation.md)
- [Reproducibility](docs/reproducibility.md)
- [Limitations](docs/limitations.md)
- [References and attribution](docs/references.md)
- [Real CV reference data](docs/real-cv-reference.md)

## Status and safety

Early independent research prototype. Synthetic outputs are for software and benchmark evaluation,
not chemical, operational, safety, or investment decisions. No affiliation with or endorsement by
Argonne National Laboratory, the U.S. Department of Energy, or the referenced open-source projects
is implied.
