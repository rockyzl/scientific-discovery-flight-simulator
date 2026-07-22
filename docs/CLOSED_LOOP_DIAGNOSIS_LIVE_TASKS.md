# Closed-loop CV diagnosis — live team tasks

Status date: 2026-07-21
State: implementation complete / independent final QA approved / ready for local commit

## Goal

Turn the existing CV evidence workbench into the smallest honest Scientific Discovery Flight
Simulator loop: an agent must diagnose why an initially abnormal CV shows enlarged peak separation,
choose experiments under a fixed budget, observe noisy or failed results, update competing
hypotheses, and decide what to do next.

The existing TEMPO page remains the evidence engine. This feature adds the decision loop above it;
it does not replace or weaken the existing provenance, model-boundary, or fail-closed controls.

## Team brief

- Scientific architect: hidden-state world, hypotheses, experiment action space, observation model,
  exact API/state contract, leakage controls, and quantitative evaluation.
- Product/UX and documentation: ten-second comprehension, lab-bench journey, beginner/expert
  disclosure, copy, responsive behavior, and durable task/status documentation.
- Independent QA: scientific identifiability, hidden-truth leakage, reproducibility, fair planner
  comparison, accessibility, and release verdict.
- Lead/integrator: freezes interfaces, assigns disjoint implementation ownership, validates the live
  system, and permits a local commit only after independent approval.

## Active coordination

- Frontend/documentation owns `demo/index.html`, `demo/app.js`, `demo/styles.css`,
  `tests/test_closed_loop_ui_contract.py`, `docs/demo-guide.md`, and this board.
- HTTP adapter owns `demo/serve.py` and `tests/test_diagnosis_server.py`.
- The originally planned separate intake worker was superseded by four independent contract-review
  rounds and the completed implementation-level final QA.
- Independent plan review v4 returned **APPROVE** in
  [`docs/reviews/closed-loop-diagnosis-plan-review-v4.md`](reviews/closed-loop-diagnosis-plan-review-v4.md).
  B1–B8, commitment opening, preterminal secrecy, and scoped idempotency are approved.
- Independent plan review v3 is retained in
  [`docs/reviews/closed-loop-diagnosis-plan-review-v3.md`](reviews/closed-loop-diagnosis-plan-review-v3.md).
- Independent plan review v2 is retained in
  [`docs/reviews/closed-loop-diagnosis-plan-review-v2.md`](reviews/closed-loop-diagnosis-plan-review-v2.md).
- The original independent review is retained in
  [`docs/reviews/closed-loop-diagnosis-plan-review.md`](reviews/closed-loop-diagnosis-plan-review.md).
- Independent implementation QA returned **APPROVE** in
  [`docs/reviews/closed-loop-diagnosis-final-qa.md`](reviews/closed-loop-diagnosis-final-qa.md).
- No commit, deployment, or push is authorized by this implementation slice.

## Proposed restricted v1

- One flagship question: what causes the increase in apparent CV peak separation relative to a
  frozen synthetic healthy/control comparator?
- Competing hypotheses: slow electron-transfer kinetics, uncompensated resistance, reference drift,
  electrode fouling, and concentration/preparation error.
- Candidate actions: repeat CV at one of six scan rates, measure independent Ru, check the reference,
  run a blank, dilute and repeat, clean and repeat, or run a control sample.
- Every action has a cost and may return noise or an explicit failure.
- The system shows belief updates, evidence, remaining budget, recommendation, and stopping reason.
- Published TEMPO scalars, synthetic simulator output, and derived evidence remain visibly separate.

## Product/UX handoff

- [x] Ten-second beginner journey, text wireframe, exact labels/copy, states, responsive behavior,
  accessibility, provenance, Supporting Measurements, and implementation map documented in
  [`docs/design/closed-loop-diagnosis-ux-plan.md`](design/closed-loop-diagnosis-ux-plan.md).
- [x] Beginner view is one diagnosis loop with central full synthetic CV arrays supplied and hashed
  by the backend; the browser never reconstructs a curve from peak markers. Planner comparison and
  detailed replay metadata move behind expert/audit disclosure or to a separate benchmark surface.
- [x] Conductivity is placed under **Supporting Measurements** and remains linked to the strict
  independent-measurement workflow rather than inferred from CV.
- [x] Explicit scope cuts and contract dependencies are recorded; no UX example value is frozen as
  scientific truth.

## Plan-review B1–B8 closure mapping

- [x] **B1:** Contract and UX use the same exhaustive 122-point Curve, extracted Peak, Observation,
  comparator/trigger, exact grid/unit/hash/nullability, and discrete argmax/argmin QC rules.
- [x] **B2:** UX consumes an exact server recommendation identity, reason code/text, costs, controls,
  and action hash; browser-computed recommendations, reasons, rationale, and eligibility are banned.
- [x] **B3:** Contract and UX use one closed Envelope/Payload decoder for every endpoint and error,
  with exhaustive enums, nullable fields, canonical hashes, and one atomic verification order.
- [x] **B4:** Idempotency is scoped by uppercase method, canonical path, campaign ID, and request ID;
  exact raw-body bytes are hashed into the public input identity, so cross-endpoint bodies cannot
  collide and changed bytes produce non-mutating 409.
- [x] **B5:** Only parseable base requests can produce a 422; its sanitized nullable Event, exact
  reason enum/message, `1/0` cost, incremented version, and unchanged beliefs are shared by both docs.
- [x] **B6:** Unreachable `insufficient_budget` is removed. Both docs freeze terminal precedence and
  a non-mutating Reveal that returns the original commitment preimage; the browser recomputes the
  original commitment before truth is shown.
- [x] **B7:** UX validates but never normalizes or repairs the server's complete five-value belief
  vector; the corrected normalized acceptance vector remains an architect/test gate.
- [x] **B8:** The question and chart explicitly compare the abnormal synthetic CV with the frozen
  synthetic healthy/control comparator supplied by the contract.
- [x] Scientific contract revisions for B1–B8 completed.
- [x] Independent QA4 approves the final protocol correction.

## Implementation checkpoint

- [x] Closed-loop diagnosis is the first/main screen; the real CV workflow and three-planner replay
  remain below as explicitly separate supporting material.
- [x] Browser auto-load/create, closed Envelope decoder, response/event/evidence/curve hashes,
  exact recommendation bytes, 422 state application, stale guard, scoped idempotent reconciliation,
  explicit reveal verification, full curves, five beliefs, budgets, result, timeline, audit, and
  Supporting Measurements link are implemented.
- [x] 320/390 px layout, text-equivalent curve table, status/alert regions, keyboard controls, and
  reduced-motion behavior are represented in HTML/CSS.
- [x] Thin HTTP routes relay core status/body bytes, preserve raw POST bytes, use private state
  outside the public artifact root, and return `Cache-Control: no-store` on routed API responses.
- [x] Focused checkpoint: Node syntax passed; 27 frontend/cartoon/HTTP adapter tests passed.
- [x] Real `DiagnosisService` core is present. A live scenario → campaign → recommended action →
  122-point CV → ledger request succeeds through the HTTP adapter with no-store responses.
- [x] Visible desktop browser review passed: campaign auto-created, all five hypotheses and exact
  recommendation displayed, action executed, and curve/budget/belief/timeline updated.
- [x] Core verification has 7/7 tests passing. Idempotency is keyed by the approved
  `(method, canonical_path, campaign_id, request_id)` scope: same-scope/same-byte requests replay,
  same-scope/changed-byte requests return non-mutating 409, and different endpoints do not collide.
- [x] Visible 390/320 browser review passed: no horizontal overflow; diagnosis, hypotheses,
  recommendation, curve, timeline, Supporting Measurements, and run control remain visible.
- [x] Independent implementation QA pass.

## Phase gates

- [x] Scientific contract completed.
- [x] Product/UX plan completed.
- [x] Independent intake requirement superseded by repeated contract QA and final implementation QA.
- [x] Contract and plan independently approved by QA4.
- [x] Backend/world implementation completed, including route-scoped idempotency.
- [x] Frontend closed-loop UI implementation completed and live core integration works.
- [x] Full automated and adversarial leakage suite passed: 175 tests, plus Node syntax and Ruff.
- [x] Visible desktop/mobile browser review passed at desktop, 390 px, and 320 px widths.
- [x] Independent final QA approved.
- [ ] Local commit created; production deployment and push remain separate actions.

## Release boundary

The approved contract is live through the frontend, HTTP adapter, and core. Automated verification,
adversarial HTTP checks, visible desktop/mobile browser QA, and independent final QA all pass. The
local implementation is ready to commit. No production deployment or push is authorized by this
task.
