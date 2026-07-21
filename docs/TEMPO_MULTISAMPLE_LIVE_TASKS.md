# TEMPO multi-sample redox inference — live team tasks

Status date: 2026-07-21
State: local release approved / production deployment pending

## Goal

Extend the CV workbench from one published example into an honest multi-sample molecular-redox
inference demo, starting with TEMPO-family candidates. The demo should estimate only properties
supported by the supplied measurements and assumptions.

## Core outputs under study

- Formal/apparent redox potential from anodic/cathodic peak positions.
- Diffusion coefficient from a multi-scan-rate peak-current model when required metadata exist.
- Reversibility evidence: peak separation, peak-current ratio, and peak-position drift with scan
  rate, without a categorical reversible / quasi-reversible / irreversible classification.
- Optional iR correction with raw/corrected comparison, resistance provenance, compensation fraction,
  and sensitivity; never infer or silently invent uncompensated resistance.
- Optional electrolyte conductivity from an independently measured resistance plus a verified cell
  constant/geometry. EIS high-frequency resistance may be used only with its measurement and cell
  context; CV alone is not a conductivity measurement.
- Related properties only when supported: regression quality, uncertainty/sensitivity, and clearly
  labeled derived diagnostics rather than unrelated molecular-property predictions.

## Non-negotiable scientific boundaries

- One CV at one scan rate cannot establish diffusivity or scan-rate dependence.
- Randles-Sevcik-style inference requires a stated electrochemical regime and metadata such as
  concentration, electrode area, electron count, temperature, and scan-rate units.
- Reversibility is an evidence-based assessment, not a universal yes/no label from one curve.
- iR compensation must preserve the raw data, state the resistance source and correction fraction,
  and warn about over-compensation; missing resistance means no correction.
- Conductivity inference requires resistance and a cell constant or defensible geometry. It must not
  relabel uncompensated CV resistance as an intrinsic molecular property.
- Solvent, electrolyte, reference electrode, concentration, temperature, and molecular form must
  remain attached to every sample and must not be pooled as if interchangeable.
- Published experimental values, user-supplied measurements, and synthetic teaching examples must
  remain visibly distinct.

## Team brief

Task: study, plan, then build a TEMPO-family multi-sample CV inference workbench.

Type: build | Complexity: M | Ceremony: full intake, frozen contract, implementation, independent QA.

Roles:

- Electrochemistry/data researcher: primary-source evidence, equations, required metadata, valid
  property boundaries, TEMPO candidate data.
- Scientific architect/data modeler: exact sample/series/inference contracts and computational tests.
- Product/UX + documentation worker: user journey, provenance language, live-task maintenance, and
  durable design/implementation plan.
- Independent QA: scientific claims, leakage/provenance, numerical checks, accessibility, browser
  workflow, and final verdict.

## Tasks

- [x] Complete the multi-sample UX study: workflow, exact labels, provenance, missing-metadata
  refusal states, comparison, uncertainty, mobile behavior, and implementation file plan. See
  `docs/design/tempo-multisample-ux-plan.md`.
- [x] Primary-source study of TEMPO-family CV and transport data.
- [x] Freeze the supported-property and required-metadata matrix.
- [x] Freeze raw/iR-corrected/reversibility/diffusivity computation contracts.
- [x] Freeze multi-sample UX and provenance contract.
- [x] Independent plan review and restricted-v1 reconciliation.
- [x] Implement data model, calculations, server routes, UI, and tests.
- [x] Validate numerical examples, exact-body request hashes, and browser interactions.
- [x] Validate 390 px and 320 px document width with the peak table contained in its own scroller.
- [x] Update user-facing data and inference documentation.
- [x] Replace free-text iR provenance with reviewed, independently identified resistance and CV
  records that must match sample, cell, geometry, electrolyte, and condition.
- [x] Require auditable conductivity calibration plus matching resistance/measurement records; reject
  generic placeholders, boolean-only claims, and mismatched contexts.
- [x] Add valid, placeholder-rejection, and field-mismatch tests for both optional calculations.
- [x] Replace the browser's old free-text optional inputs with explicit record IDs, allowed method
  selectors, and matching structured records for the strict API.
- [x] Add clearly labelled synthetic teaching-record loaders that never set review state; require
  explicit user confirmation for iR and separate calibration/resistance confirmations for
  conductivity.
- [x] Clear stale request and response audits whenever any upstream optional input changes.
- [x] Add a visible backlink between the current CV explainer and `/tempo/`.
- [x] Independent final QA. APPROVE recorded in
  [`docs/reviews/tempo-final-qa.md`](reviews/tempo-final-qa.md).

## Release gate

Implementation used the second scientifically defensible data path:

1. attributed published scalar values with no reconstructed publisher curves; and
2. an explicitly synthetic teaching dataset with reviewed manual peak assignments.

## Frontend implementation slice

- [x] Add the sibling `demo/tempo.html` study route surface.
- [x] Add responsive `demo/tempo.css` with provenance, mobile, keyboard, and 44 px target rules.
- [x] Add `demo/tempo.js` with fail-closed atlas loading, authoritative request/response validation,
  stale-result invalidation, synthetic peak input, and separate conductivity calls.
- [x] Add the five-sample no-ranking atlas interaction and visible `not reported` states.
- [x] Add the six-row synthetic manual peak table and illustrative non-data CV sketch.
- [x] Add user documentation for the data and inference boundaries.
- [x] Add executable UI contract checks for provenance separation, the frozen five-sample atlas,
  six-rate inputs, nested response schema, refusal/stale behavior, responsive controls, and
  JavaScript syntax.
- [x] Integrate the route and JSON/API endpoints into the server and add the backlink from
  `demo/index.html`.
- [x] Complete backend/core integration and numerical/browser integration checks.
- [x] Complete independent final release QA.

## Final local release evidence

- Independent verdict: **APPROVE** — see
  [`docs/reviews/tempo-final-qa.md`](reviews/tempo-final-qa.md).
- Automated regression: **147 tests passed**.
- Browser review: completed in visible Chrome, including the structured iR and conductivity flows.
- Release boundary: local release only; no production deployment or push was performed by this QA
  closeout.
