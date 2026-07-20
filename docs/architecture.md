# Architecture

## Purpose

The system isolates three concerns: choosing an experiment, executing it in a hidden simulated
world, and evaluating the resulting campaign. The isolation is the central trust boundary: a
planner must not read the answer it is meant to infer.

```text
Scenario
├── PublicWorldSpec ───────────────┐
├── InstrumentCapabilities ────────┤
├── budget and stopping contract ──┤
└── private ScenarioTruth          │
                                   ▼
PublicCampaignState ──> Planner.propose()
                              │
                              ▼
                    ProtocolValidator.validate()
                              │ valid request
                              ▼
                    CampaignEnvironment.execute()
                              │
                              ▼
                         Observation
                              │
                              ▼
                       EvidenceLedger
                              │
                              ▼
                  Evaluator.score(private truth)
```

## Core engine

The core is domain-neutral and owns:

- immutable public campaign state supplied to planners;
- request, stop, validation, observation, and ledger contracts;
- budget accounting for attempts and measurements;
- deterministic seed routing;
- sequential campaign execution;
- evidence-ledger serialization and artifact hashing; and
- evaluator orchestration without exposing private truth to planners.

The runner accepts a planner and scenario through interfaces. It should not contain CV-specific or
microscopy-specific branches.

## World packages

A world package owns the scientific teaching emulator and its instrument semantics:

- public control ranges, supported operation names, budgets, and constraints;
- private response mechanism and parameters;
- instrument capabilities;
- condition-indexed noise and attempt-indexed failure behavior;
- conversion of a valid request into an observation; and
- world-specific evaluation quantities.

The flagship package is a synthetic CV mechanism world. The microscopy fixture is intentionally
small and exists only to demonstrate that a second world can implement the same core interfaces.

## Planner boundary

The planner receives exactly these `PublicCampaignState` fields plus its own RNG:

- `spec`: the `PublicWorldSpec` with controls, operations, and total budgets;
- `observations`: prior `Observation` objects from executed operations;
- `remaining_attempt_budget` and `remaining_measurement_budget`; and
- `public_beliefs`: the current public hypothesis scores.

`PublicCampaignState` does not contain prior `ValidationResult` objects or accumulated-cost fields.
Those are recorded in ledger events; remaining budgets are computed by the runner before it builds
the next public state. The planner must not receive:

- hidden mechanism identity or parameters;
- noiseless response values;
- future noise values or failure schedule;
- evaluator output; or
- another planner's campaign.

This boundary must be enforced by typed data contracts and tests, not by a prompt or documentation
convention.

## Artifact-only demo

The browser demo is deliberately outside the execution path. It reads a frozen `manifest.json`,
`summary.json`, and three ledger JSON files from a completed CLI run. It cannot propose experiments,
change the world, or call an LLM. `demo/serve.py` uses Python's standard library and limits artifact
requests to the selected artifact directory.

## Relationship to scientific-agent-lab

`scientific-agent-lab` addresses report-level evidence, assumptions, uncertainty, human review, and
reproducibility. This project addresses stateful hidden worlds, sequential experiment campaigns,
instrument failures, planner comparison, and stopping behavior. Keeping them separate prevents two
different evaluation questions from becoming one ambiguous agent framework.

An optional future adapter could translate an evidence ledger into a report-evaluation input. That
possibility is not implemented or required in v0.
