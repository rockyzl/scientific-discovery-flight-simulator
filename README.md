# Scientific Discovery Flight Simulator

**Compare how experiment-selection policies behave under the same simulated world, budget,
constraints, noise, and instrument failures.**

> **SIMULATED RUN — NOT A LAB MEASUREMENT.** This statement applies to the policy benchmark. A
> separately labeled chart uses cited, published experimental CV data.

This repository is an offline, deterministic research prototype for replaying scientific campaigns.
Its first world is a transparent cyclic-voltammetry (CV) teaching emulator in which a planner must
choose scan rates that distinguish among diffusion-like, surface-like, and mixed responses. Random,
fixed-grid, and expected-information-gain policies receive the same experimental contract and are
scored from separate, auditable evidence ledgers.

## The one honest claim

This project can compare the behavior of the included experiment-selection policies under a fixed,
synthetic benchmark contract. It records every proposal, validation decision, simulated observation,
QC flag, cost, belief update, and stopping decision. Failure-detection and recovery metrics are
derived from that ledger so the comparison can be inspected and repeated.

It does **not** show that an agent can make discoveries in a real laboratory. It does not control
instruments, generate laboratory measurements, validate a mechanistic CV model, or establish general
scientific reasoning.

## What the demo shows

The browser demo reads a completed artifact directory and a bundled, cited real-data reference; it
does not control an instrument or run a new laboratory experiment.

1. Inspect three published all-iron RFB anolyte CV curves and play the physical sample-change and
   measurement workflow step by step.
2. See the exact boundary between that real-data reference and the separate synthetic mechanism
   benchmark.
3. Compare `random`, `fixed_grid`, and `information_gain`: selected scan rate, simulated response,
   changing mechanism probabilities, final answer, and attempts used.
4. Inspect each campaign event in order, including rejected requests and injected failures.
5. See the scenario, budget, public planner seed, private-seed commitments, versions, and artifact
   identity.
6. Download the manifest, summary, and planner ledgers as JSON.
7. Reveal benchmark hidden truth only after all completed artifacts have loaded.

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

Open <http://127.0.0.1:8000>. The server exposes only the static demo and files beneath the selected
artifact directory.

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
public campaign state ──> planner ──> protocol validator
                                              │
                                              ▼
private scenario truth ──> campaign environment ──> observation
          │                                            │
          └──────────── evaluator <── evidence ledger ─┘
```

The planner receives only public state. Hidden mechanism parameters, noiseless response, future
failure schedule, and evaluator remain private. See [architecture](docs/architecture.md) and the
[benchmark contract](docs/benchmark-contract.md).

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
