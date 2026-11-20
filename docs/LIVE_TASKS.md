# Scientific Discovery Flight Simulator — live tasks

Status date: 2026-07-20
Project state: public MVP published and registered locally
Source memo: `../../../../sciencesloop-lab/journal/2026-07-19-scientific-discovery-flight-simulator.md`

## Objective

Create a public, reproducible first version of a Scientific Discovery Flight Simulator: a
controlled sandbox for comparing experiment-selection strategies, protocol validation, failure
recovery, evidence trails, and stopping decisions without controlling real instruments.

## Non-negotiable boundaries

- Simulated measurements are never presented as laboratory measurements.
- The system does not control real instruments and is not called an autonomous laboratory.
- The planner cannot inspect hidden world truth.
- The first release compares against non-LLM baselines.
- The MVP must be small enough to understand, test, and demonstrate end to end.
- Existing `projects/scientific-agent-lab` must be inspected before defining overlap or reuse.

## Team brief

Task: discuss, plan, build, test, document, and publish the first project version.
Type: architecture + build
Complexity: M
Roles: Scientific Architect; Simulation/Benchmark Engineer; Product/Documentation Designer; QA
Reviewer.
Phases: independent intake → contracts/ownership → parallel build → QA → lead validation → GitHub.

## Intake questions

- What is the smallest scientific claim the MVP can honestly support?
- Which first world gives both scientific depth and a clear public demo?
- Which second micro-world is sufficient to demonstrate interface transfer?
- What should be core engine versus domain package?
- What baselines and metrics prevent the demo from becoming an LLM theater piece?
- What overlap exists with `scientific-agent-lab`, and what should be reused versus kept separate?

## Tasks

- [x] Preserve the research-only Maker memo.
- [x] Create team coordination state.
- [x] Complete independent team intake.
- [x] Freeze MVP scope and exact interfaces.
- [x] Initialize package, tests, and public documentation.
- [x] Implement core engine and first world.
- [x] Implement a small transfer world and public demo.
- [x] Run independent QA and targeted correction rounds.
- [x] Validate the complete project locally.
- [x] Create the GitHub repository and push the validated project.
- [x] Register the project in the local project hub only after the repository is usable.

## Product and documentation deliverables

- [x] Publish the one honest claim, non-claims, project boundary, and local quickstart in `README.md`.
- [x] Document architecture, fairness, evidence-ledger semantics, evaluation, reproducibility,
  limitations, demo interpretation, and reference-safety boundaries.
- [x] Implement an artifact-only, accessible single-page comparison and evidence replay.
- [x] Keep benchmark truth disabled and concealed until every ledger is complete, then read it only
  from `summary.json.post_run_reveal` after an explicit visitor action.
- [x] Implement a standard-library demo server that confines artifact requests beneath the selected
  output directory and rejects traversal and symlink escapes.
- [x] Add owned documentation, accessibility, server, provenance, and path-safety tests.

Product/doc validation on 2026-07-20: 16 owned tests passed; the integrated suite now passes 62 tests;
Ruff, Node JavaScript syntax checking, Python compilation, HTML parsing, a real CV artifact run, and
local HTTP/artifact/traversal smoke checks passed.

### QA correction log — 2026-07-20

- Replaced the metric formatter with JavaScript's shortest round-trip number representation and
  added Node-backed regressions for `1e-10`, `1e-20`, negative small values, and large values.
- Made the demo server call core `verify_artifact_bundle(Path)` before binding; startup now rejects
  modified manifest, summary truth, ledger, hashes, identities, commitments, incomplete bundles, and
  missing or unexpected files.
- Removed raw private world/noise/failure seeds from the pre-reveal UI. It shows HMAC commitments and
  the public planner seed; the completed reveal shows replay material with a synthetic-data warning.
- Completed the WAI-ARIA tablist/tab/tabpanel relationships, stable IDs, roving focus, focusable
  reveal region, and live announcement behavior.
- Aligned documentation with schema version `1`, `status: complete`, `completion_status`, flat metric
  fields, public seed commitments, private reveal fields, and executed-operation measurement cost.
- Re-ran real-bundle server and tamper smoke checks; all targeted corrections passed.

### Final documentation consistency correction — 2026-07-20

- Corrected the replay procedure: default CLI runs generate different private replay keys, so exact
  byte replay requires `--private-seed-key '<revealed-key>'` from the completed original summary.
- Replaced the two misleading default rerun commands with an original command and an explicit-key
  replay command in both README and reproducibility guidance.
- Restricted the architecture description of `PublicCampaignState` to its actual fields: public
  spec, observations, remaining attempt/measurement budgets, and public beliefs.
- Restricted the evidence-ledger description to actual `ExperimentEvent` fields and clearly marked
  remaining budget, failure recovery, violations, and stopping quality as UI/evaluator derivations
  rather than persisted event fields.

## Decisions

- All three intake reviewers voted `approve-with-conditions`.
- Honest claim: an offline deterministic benchmark/demo that compares experiment-selection
  policies under the same synthetic hidden world, budget, constraints, noise, and failure schedule
  with an auditable replay.
- Flagship world: synthetic Virtual CV Mechanism Lab. The hidden mechanism is
  `diffusion ~ sqrt(scan_rate)`, `surface ~ scan_rate`, or a mixed response. It is a transparent
  teaching emulator, not a complete or validated CV model.
- Planners: random valid action, fixed log-spaced grid, and expected information gain. No LLM is
  required or claimed in v0.
- Transfer fixture: one-dimensional microscopy phase-boundary localization, used only to prove
  that the core interfaces transfer.
- One rejected request consumes one attempt cost but no measurement cost. A failed measurement
  consumes both attempt and measurement cost. All decisions and costs remain in the ledger.
- Randomness is separated into world, noise, failure, and planner seeds. Before reveal, artifacts
  expose only the public planner seed and commitments to the private world/noise/failure seeds. The
  completed summary reveal contains the replay key and private seeds. A condition-indexed noise
  schedule and attempt-indexed failure schedule make paired planner comparisons reproducible.
- Existing `scientific-agent-lab` remains separate. This project owns stateful worlds, instruments,
  sequential experiment selection, campaign budgets, failure injection, and planner comparison.
  A future adapter may export compatible evidence, but v0 has no runtime dependency.
- Minimal stack: Python 3.11+, NumPy, pytest/ruff for development, and vanilla HTML/CSS/JS.

## Frozen interfaces

Core Python contract:

```text
Planner.propose(PublicCampaignState, planner_rng)
  -> ExperimentRequest | StopDecision

ProtocolValidator.validate(ExperimentRequest, PublicWorldSpec, InstrumentCapabilities)
  -> ValidationResult

CampaignEnvironment.execute(valid ExperimentRequest)
  -> Observation

CampaignRunner.run(planner, scenario)
  -> EvidenceLedger

Evaluator.score(EvidenceLedger, private ScenarioTruth)
  -> EvaluationResult
```

Hidden truth, future failure schedule, noiseless response, and evaluator are never included in
`PublicCampaignState` or passed to a planner.

CLI contract:

```text
python -m discovery_flight_simulator.cli compare \
  --scenario scenarios/cv_mechanism_v0.json \
  --output <NEW_OUTPUT_DIR>

<NEW_OUTPUT_DIR>/manifest.json
<NEW_OUTPUT_DIR>/summary.json
<NEW_OUTPUT_DIR>/ledgers/random.json
<NEW_OUTPUT_DIR>/ledgers/fixed_grid.json
<NEW_OUTPUT_DIR>/ledgers/information_gain.json
```

The output directory is new and fail-closed. Every JSON artifact includes
`provenance: simulated`, schema/world/planner versions, the public planner seed, private-seed
commitments, and hashes. Raw private seeds and the replay key appear only in the completed
`summary.json.post_run_reveal`. `summary.json` reports separate metrics rather than hiding behavior
behind one opaque score.

Demo contract:

```text
python demo/serve.py --artifacts <OUTPUT_DIR>
GET /                         -> accessible single-page comparison UI
GET /artifacts/manifest.json  -> frozen run manifest
GET /artifacts/summary.json   -> planner comparison
GET /artifacts/ledgers/<name>.json -> planner replay
```

The UI always displays `SIMULATED RUN — NOT A LAB MEASUREMENT`; hidden truth is revealed only after
the completed artifacts are loaded.

## File ownership

- Core worker: package metadata, contracts, validation, runner, ledger, CLI, and core tests.
- Scientific worker: CV/microscopy worlds, planners, scenarios, evaluation, and scientific tests.
- Product/Doc worker: demo, README, public documentation, demo tests, and this live task record.
- Lead: contract decisions, integration, QA coordination, GitHub creation, and final validation.

## Current handoff

The public MVP is available at
`https://github.com/rockyzl/scientific-discovery-flight-simulator`. Implementation,
documentation, independent QA, correction rounds, local validation, publication, and local hub
registration are complete.

## Active milestone - Virtual RFB Cell Campaign

Status: complete. This is a simulated 0D virtual redox-flow-battery cell
benchmark and human-approved workflow, not a digital twin, autonomous or
self-driving lab, hardware controller, or calibrated physical-performance
model.

Completed/frozen architecture:

- RFB V1 is a finite protocol space with five serialized unit-bearing fields;
  only `charge_current_A` and `discharge_current_A` vary.
- The deterministic virtual oracle is pinned to `rfbzero==1.0.1`. The public
  objective is one frozen scalar utility; it is not Pareto optimization.
- SQLite is the campaign source of truth. LangGraph plus its SQLite checkpointer
  is orchestration-only for recommend -> mandatory human approval -> resume.
- An edit or rejection changes the campaign to `human_intervened`/
  `workflow_case_study`, making it unrankable in the strict benchmark.
- Logical replay uses canonical identities and the event chain. Audit timestamps
  are retained but excluded from deterministic event hashes.

Verified:

- RFB domain/scenario, validation, deterministic policies, oracle adapter,
  SQLite campaign journal, and execution claim/commit path are implemented.
- Artifact export and logical replay passed their separate security and
  correctness review. Public artifact metadata uses a closed schema and export
  is fail-closed; the original CV/microscopy artifact contract remains intact.
- Canonical public HTTP routes and LangGraph pause/resume wiring are
  implemented. Approval records a decision only; a decision-scoped explicit
  resume is the only route that can advance an approved simulation.
- An independent API/workflow QA pass approved the HTTP contract after a
  targeted P1 repair: a completed resume now validates the matching durable
  approval revision before returning an idempotent result. Focused tests pass
  and the full suite passed with 184 tests.
- The isolated local UI server and human-review browser UI are implemented over
  the frozen HTTP contract. The published artifact replay demo remains
  unchanged.
- Final independent browser/API QA is complete and approved.
- Final verification: `uv run --extra dev pytest -q` passed with 188 tests;
  `ruff` passed; and Node UI tests passed with 3 tests.
- Existing CV/microscopy CLI, demo, artifact contract, and verifier remain
  unchanged through RFB integration.

### Current HTTP contract — frozen for this integration cycle

```text
POST /api/rfb/campaigns
  {campaign_id, scenario_id, policy_id}
  -> 201 {campaign, event_head_sha256}

POST /api/rfb/campaigns/{campaign_id}/approvals
  {decision_id, expected_revision, decision, ...}
  -> 200 {campaign, event_head_sha256}
  Note: this records a human decision only. It does not claim a lease,
  reserve cost, invoke the virtual oracle, or execute an action.

POST /api/rfb/campaigns/{campaign_id}/resume
  {decision_id, expected_revision}
  -> 202 {campaign, event_head_sha256} for one newly advanced transition
  -> 200 {campaign, event_head_sha256} for an idempotent repeat

GET /api/rfb/campaigns/{campaign_id}
GET /api/rfb/campaigns/{campaign_id}/events
GET /api/rfb/scenario
```

Documentation:

- [Virtual RFB Cell Campaign research plan](rfb-virtual-cell-research-plan.md)
- [RFB workflow contract](decisions/rfb-workflow-contract.md)
