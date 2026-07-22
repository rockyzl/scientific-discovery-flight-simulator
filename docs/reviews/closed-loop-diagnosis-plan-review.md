# Independent plan review — closed-loop CV diagnosis restricted v1

Review date: 2026-07-21

Reviewer role: independent scientific, API, product, leakage, and feasibility QA

Reviewed artifacts:

- `docs/design/closed-loop-diagnosis-contract.md`
- `docs/design/closed-loop-diagnosis-ux-plan.md`
- `docs/CLOSED_LOOP_DIAGNOSIS_LIVE_TASKS.md`
- current implementation boundaries in `demo/index.html`, `demo/app.js`, `demo/styles.css`,
  `src/discovery_flight_simulator/contracts.py`, `runner.py`, `ledger.py`, current world/planner
  code, and the existing TEMPO API/UI tests

## 1. Verdict

**REQUEST CHANGES.**

The scientific boundary is unusually clear and the proposed beginner journey is directionally
strong, but implementation must not begin against the present pair of documents. The frozen
contract and UX disagree about the central evidence object, the recommendation used to create the
next request is not specified, several HTTP/event semantics conflict internally, and a frozen stop
test uses an impossible probability vector. These are executable-contract defects, not polish.

Approval conditions are the closure of blocking findings B1–B8 below, executable acceptance tests
for the resulting exact schemas, and a second independent contract/UX alignment review. No source
implementation should be treated as conforming before then.

## 2. Blocking findings

### B1 — The UI requires a full CV curve that the contract expressly does not produce

References:

- Contract sections 4, 6, 8, and 16 define only a reviewed peak summary, call the response model a
  “compact diagnostic signature table, not a generated CV curve,” and postpone raw or generated
  full curves.
- UX sections 2, 4, 5 “Central CV,” 6, 7, 9, 10, 12, and 14 require a complete forward/reverse
  curve, “Starting curve” and “Latest valid curve,” dynamic SVG descriptions, and a central full-CV
  implementation.

Required change: choose one contract-authorized visual representation before implementation.
For minimum restricted v1, replace the full-curve requirement with a prominent **synthetic peak
summary visualization** that shows Epa/Epc, ipa/ipc, apparent midpoint, and delta_Ep without joining
them into a plausible curve. If a full curve is a non-negotiable product requirement, unfreeze the
scientific contract and specify the complete potential grid, forward/reverse current generator,
units, noise covariance, QC, hashes, and whether any curve features enter the posterior. Do not draw
a generic smooth curve from peak markers.

### B2 — No executable recommendation contract exists

References:

- Contract sections 5, 9, 10, and 13 define action requests, public beliefs, stop rules, and HTTP
  endpoints, but not the recommendation object, recommendation algorithm, action eligibility,
  display-name mapping, reason codes, or recommendation identity.
- UX section 5 requires an approved reason-code template; section 6 enables Run only when
  recommendation ID, state version, and input hash agree; sections 11 and 14 require a verified next
  recommendation.
- The request contract currently permits an arbitrary non-empty `rationale`, which conflicts with
  the UX prohibition on unrestricted generated prose.

Required change: freeze a server-owned `Recommendation` schema and include it in campaign creation,
campaign state, and every accepted/failure response that remains active. At minimum it needs
`recommendation_id`, `state_version`, `planner_id`, `operation`, exact `controls`, `reason_code`,
approved rendered `reason_text`, costs, and a canonical `action_input_hash`. Freeze the flagship
planner ID/version and exact selection/tie-breaking rule, including expected-information-gain
calculation and repeated-action eligibility. Either remove request `rationale` from client authority
or require it to equal the server-issued reason code/text. Manual alternatives, if retained, need
their own server-issued eligible-action objects and identities.

### B3 — Important HTTP schemas and integrity fields are only described, not frozen

References:

- Contract section 13 gives a complete-looking example only for campaign creation, action success,
  and a generic error. The exact response bodies for scenario, campaign state, stop, ledger, reveal,
  action rejection, terminal state, and QC failure are absent.
- Contract section 8 calls the observation form an “exact conceptual shape,” which is not an exact
  wire schema.
- UX section 6 requires response/run/state/hash verification, but the API does not define a
  response hash, previous ledger hash, recommendation identity, or exact reconciliation procedure.

Required change: publish closed JSON schemas (or equivalently exhaustive field tables) for every
request and response. Define required versus omitted fields for every result state, exact status
identifiers, canonical JSON/byte hashing inputs, previous/current ledger hashes, campaign/scenario
identity, and verification order. The browser must be able to verify a response using only the
documented public response and its previously verified state. Unknown response fields must fail
closed where integrity is claimed.

### B4 — Retry and duplicate-request behavior is contradictory and unsafe after an ambiguous network failure

References:

- Contract section 5 says duplicate request IDs cost `1/0` on their first rejection response.
- Contract section 13 maps `DUPLICATE_REQUEST_ID` to HTTP 409, then says all 409 errors create no
  event and consume no budget.
- UX sections 6 and 11 offer “Retry same experiment” after network or integrity errors.
- Current `runner.py` lines 116–124 implements duplicate IDs as a new rejected, charged event,
  illustrating the incompatibility with the proposed HTTP rule.

Required change: freeze idempotency semantics. Recommended minimum: the same `request_id` with the
same exact body returns the original recorded response without a new event, state increment, noise
draw, or cost; reuse with different bytes returns 409 without mutation. The UI must reuse both the
same request ID and identical serialized bytes, then reconcile with GET state/ledger before deciding
that no mutation occurred. If this is not chosen, remove “Retry same experiment” and define a safe
recovery protocol.

### B5 — Rejected-request state/version semantics conflict with the response example and UX state machine

References:

- Contract sections 5 and 12 say a rejected 422 request is appended, costs `1/0`, and increments
  state version.
- The section 13 error example shows remaining attempt budget reduced to 11 but leaves
  `state_version: 0`.
- UX section 6 has no `REQUEST_REJECTED` transition and groups request errors under “no state
  advance”; section 11 likewise has no charged validator-rejection state.

Required change: make the example return the incremented state version and define a distinct
`REQUEST_REJECTED` UI transition. A 422 rejection must append one timeline event, decrease attempt
budget, preserve measurement budget and beliefs, and render the exact rejection reason. Transport,
404, and 409 errors remain non-mutating and must not use the same copy. Freeze stop-rejection response
semantics separately if its request shape differs.

### B6 — The stopping and completion vocabulary is not aligned

References:

- Contract section 10 defines explicit reasons `confident_diagnosis`,
  `low_expected_information`, and `insufficient_budget`, plus automatic `budget_exhausted`.
- Contract section 12 defines completion status only as `stopped`, `budget_exhausted`, or
  `incomplete`.
- UX sections 5 and 11 additionally render “evidence threshold reached,” “no eligible action,” and
  a generic “contract reason.” No `no_eligible_action` transition exists in the contract.

Required change: publish a one-to-one mapping from exact stop/completion identifiers to approved
visible copy and remove invented states. If `no_eligible_action` is required, add its exact server
rule and terminal identifier. Define “still-valid action” and repeat eligibility so the
`low_expected_information` calculation is reproducible.

### B7 — Frozen stop vector F is mathematically impossible

Reference: contract section 14.F uses maximum posterior `0.91` and runner-up `0.10`; these already
sum to `1.01` before the remaining three probabilities, contrary to section 9’s normalized
five-probability requirement.

Required change: replace vector F with a complete five-value normalized posterior. Preserve the
intended pass/fail boundaries, for example a maximum of `0.91`, runner-up no greater than `0.09`,
and explicitly listed remaining probabilities summing to one. Test the exact complete vector rather
than two independently asserted values.

### B8 — The scientific question asserts an increase without a defined comparator

References:

- Contract section 4 provides one initial synthetic peak summary with `delta_Ep=0.100 V`, explicitly
  not a likelihood update, but no prior/reference peak separation from which it “grew.”
- UX sections 1, 2, and 5 ask why the separation “grew” and state that it is larger than the
  starting/reference state.

Required change: either define a public synthetic reference observation and its non-likelihood role,
or change the question to “What best explains this enlarged apparent peak separation in the frozen
synthetic benchmark?” The initial trigger’s intentionally non-generative/non-discriminating status
must be visible so visitors do not interpret a later 25 mV/s result as a physically continuous
change from the trigger.

## 3. Nonblocking findings

1. **Model-relative beliefs are responsibly framed.** Contract sections 1–2 and UX sections 5 and
   8 correctly avoid real-sample diagnosis, hard reversibility classes, and calibrated-confidence
   language. Keep “working belief within the five predefined synthetic hypotheses” adjacent to the
   bars, not only in a footer.
2. **The hidden-truth boundary is well conceived.** Contract sections 3, 9, 11–13 and UX sections
   6–8 agree that truth, raw seeds, future failures, and evaluator results stay unavailable until
   terminal state plus an explicit reveal action. The reveal response still needs the exact schema
   and commitment-verification algorithm requested in B3.
3. **Failure realism is intentionally narrow, not realistic.** One attempt-indexed timeout is enough
   to teach failure accounting, but cannot support a claim of realistic instrument behavior or
   robust recovery under drift, saturation, carryover, calibration failure, or correlated noise.
   State this limitation beside any failure-recovery metric.
4. **The Gaussian model assumes independent features.** Contract sections 6 and 9 use diagonal
   standard errors even though Epa/Epc-derived quantities are algebraically related. This is valid as
   a declared benchmark construction only because belief features are midpoint, separation, and
   absolute anodic current rather than all redundant peak fields. Tests must ensure derived fields
   never enter likelihood twice.
5. **The initial trigger is deliberately off-model.** That makes it suitable as a common trigger,
   but it should be labeled as such in the public state and ledger. It must never silently acquire a
   likelihood or be represented as a sample from the selected hypothesis.
6. **Current code is a foundation, not a drop-in implementation.** The current scalar
   `Observation` (`contracts.py` lines 118–145), planner-owned beliefs (`runner.py` lines 24–32,
   82–90, 143–149), batch runner, and three-planner saved-artifact UI (`demo/index.html` lines
   251–365; `demo/app.js` lines 1–16 and 800 onward) require additive diagnosis-specific contracts,
   an in-memory campaign service, central inference, and a new renderer. Existing types must not be
   weakened to force-fit structured evidence.
7. **Accessibility plan is strong but needs an error-summary focus rule.** The plan defines status
   and alert regions, reduced motion, semantic ordered timeline, native details, dynamic SVG text,
   keyboard reachability, and 320 px behavior. Add a visible text/table equivalent for the peak
   visualization selected under B1 and ensure an integrity alert is focused only when necessary,
   with focus return to Run/Retry documented.
8. **Conductivity placement is correct.** Keep it as a link to `/tempo/#conductivity`; do not embed or
   replicate the strict provenance form in this release. `measure_ru` in the diagnosis world is a
   simulated diagnostic scalar and must not be passed off as the independently reviewed record used
   by the real TEMPO conductivity calculator.

## 4. Contract-to-UI alignment table

| Concern | Contract | UX plan | Review disposition |
| --- | --- | --- | --- |
| Scientific question | One abnormal synthetic peak summary; no comparator | Asks why separation “grew” from a reference | **Blocked:** add comparator or change wording (B8) |
| Central evidence | Peak summaries and diagnostic scalars only; full curves postponed | Complete forward/reverse starting/latest CV curves required | **Blocked:** use peak-summary visual or expand contract (B1) |
| Hypotheses | Five labels in frozen order, uniform prior | Same five human-readable labels and bars | Aligned; preserve stable ID-to-label map |
| Belief meaning | Central Gaussian posterior within public model | “Working beliefs,” not real-sample confidence | Aligned, subject to central-engine implementation |
| Action request | Seven operations with exact controls; arbitrary rationale string | One recommendation plus templated reason; optional expert alternatives | **Blocked:** freeze Recommendation and eligibility schemas (B2) |
| Recommendation identity | Not defined | Requires recommendation ID/state/input-hash agreement | **Blocked:** missing fields and selection algorithm (B2–B3) |
| Attempts and operations | 12 attempts, 10 measurement/executed-operation units | Primary operations budget plus attempts | Conditionally aligned; freeze terminology and always show both when they differ |
| Valid observation | Structured peak summary or one diagnostic scalar | Result, optional latest curve, belief delta, timeline | **Blocked only for curve;** scalar/result story otherwise aligns |
| Timeout/QC failure | Costs `1/1`, null numeric evidence, no update | Explicit failure, no fake zero/curve, charged cost | Aligned; show unchanged beliefs explicitly |
| Validator rejection | 422 event, `1/0`, state advances | No distinct state; request errors said not to advance | **Blocked:** add rejected transition/copy (B5) |
| Duplicate/retry | Contradictory charged duplicate versus non-mutating 409 | Retry same experiment | **Blocked:** freeze idempotent recovery (B4) |
| Stop reasons | Three explicit codes plus automatic budget exhaustion | Generic evidence/no-action/contract reasons | **Blocked:** exact one-to-one mapping required (B6) |
| Conductivity | Separate, never belief/ranking/evaluation evidence | Supporting Measurements link with limitation | Aligned; link only in restricted v1 |
| Derived apparent D | Optional after three distinct rates; never likelihood evidence | Expert/audit context implied | Aligned if omitted from MVP; if shown, preserve branch/QC/limitation data |
| Truth reveal | Only terminal plus explicit reveal; absent from state/ledger/manifest | Expert-only explicit reveal after terminal state | Aligned, pending exact reveal schema/verification |
| Stale response | Stale state is 409/non-mutating | Abort/discard late client response, preserve verified UI | Aligned in intent, pending exact reconciliation fields |
| Integrity failure | Fail closed; ledger/hash verification required | Preserve previous verified state and alert | Aligned in intent, pending wire-level hash contract (B3) |
| Planner comparison | Evaluation supports separate metrics; fairness objective mentioned | Removed from beginner view; leaderboard postponed | Keep out of restricted-v1 public path; offline evaluation only |
| Provenance | `simulated` and `derived_from_simulated`; published context excluded | Object-level synthetic/derived/published marks | Aligned; test each rendered object, not only page-level copy |

## 5. Required adversarial test matrix

| Area | Adversarial case | Required fail-closed result |
| --- | --- | --- |
| Request schema | Unknown/missing top-level field; unknown operation/control; bool, NaN, infinity, string numeric, wrong exact enum | Correct 400/422 code; no execution; only contract-authorized rejection cost/state mutation |
| Operation controls | Extra control on `{}` action; wrong fixed dilution/rate; valid repeat rate with float/int spelling | Exact accepted/rejected behavior and canonical control representation |
| Recommendation binding | Alter operation, controls, state version, recommendation ID, reason code, or input hash after render | Request refused; no observation/noise draw; charged or uncharged behavior exactly follows frozen rule |
| Server recommendation | Tied scores, repeated action, near-zero probabilities, one remaining budget unit | Deterministic frozen tie-break, legal action, finite reason code, exact cost |
| Posterior isolation | Change/remove private truth after generating the same public observation | Posterior and recommendation remain byte-equivalent |
| Posterior numeric safety | Extreme likelihoods, zero/negative/nonfinite SE, missing feature, redundant derived field | Log-space finite normalized result or explicit rejection; never NaN/uniform fallback |
| Feature whitelist | Add conductivity, derived D, Epa/Epc duplicates, timeout, failed-QC numeric debris, or initial trigger | No posterior or recommendation change from forbidden evidence |
| Identifiability | Execute each discriminating operation against each of five hidden causes over multiple frozen noise seeds | Report confusion/posterior behavior without claiming universal identification; no label privileged by ordering except documented ties |
| Failure schedule | Timeout on frozen accepted-execution attempt; precede it with rejected requests | Failure occurs according to the exact accepted-attempt definition, not leaked or shifted by invalid requests unless explicitly specified |
| Failure/retry | Timeout then repeat same condition | No update on failure; charged `1/1`; successful-repeat index remains zero; next valid value matches no-timeout reference |
| Ambiguous HTTP retry | Server records action but client loses response, then sends identical request ID/body | Original result recovered without second event, cost, noise, or belief update under the B4 rule |
| Request-ID attack | Reuse request ID with changed whitespace/body/action/controls | 409, no event, cost, state change, or secret-bearing error |
| Rejection accounting | Invalid action and invalid stop from initial state | One rejection event, attempt budget decremented, state version incremented, beliefs/measurement budget unchanged |
| Stale concurrency | Two valid requests use same expected version; response A arrives after UI reset or mode switch | At most one server mutation; late/unmatched response changes no DOM, budget, beliefs, curve/summary, or timeline |
| Terminal mutation | Action/stop/reveal before allowed; action after stop/budget exhaustion; repeated reveal | Exact 409/422 behavior; no unauthorized mutation; reveal only after terminal and explicit request |
| Truth leakage | Recursive keys and serialized values across typed state, all endpoints, errors, logs, ledger, manifest, DOM, storage, source maps, service-worker cache, and prefetch | No cause, raw seeds, future timeout, selected noiseless column, evaluator output, or replay key before explicit terminal reveal |
| Commitment tamper | Change cause, any seed, scenario, event, evidence, belief, cost, version, hash, or reveal commitment | Verification fails closed; previous verified state remains; no partial render |
| Evidence shape | Missing/extra peak field; inconsistent Epa/Epc/midpoint/delta/ratio; scalar wrong unit/name; failed evidence non-null | Reject response as integrity failure; never synthesize missing values in browser |
| Visualization | Only peak summary is available; failed/non-CV action follows a valid repeat CV | No invented full curve, no zero curve, no stale curve labeled “latest”; visible text identifies the last valid evidence kind |
| Stop boundaries | Exact values just below/at 3 successes, 2 distinct operations, 0.90 max, 0.25 margin, 0.01 nat EIG, and exhausted budget | Exact accept/reject result, reason code, cost, final hypothesis, and confidence/posterior equality |
| Determinism | Same seeds/actions with different planner RNG call counts/order; different condition ordering; replay from ledger | Same condition-indexed observations and hashes where specified; planner RNG cannot perturb world RNG |
| Planner fairness | Separate campaign instances with same public scenario/commitments and isolated planner seeds; one planner attempts mutation | No shared observations/state; same world/noise/failure rules; mutation cannot affect another run |
| Conductivity boundary | Supply high/low/malformed conductivity or diagnosis Ru to belief engine and evaluator | No belief, recommendation, stop, score, or success change; link remains separate |
| Accessibility | Keyboard-only run/retry/details/reveal; screen reader through success/failure/stale; reduced motion; 200% zoom; 320/390 px | Logical focus/order, correct live/alert announcement, text equivalent, no autoplay or document overflow |
| Ten-second comprehension | At least five first-time users after verified load | Each identifies question, five candidates, next experiment/reason, result/change without opening Expert; record failures and revise before release |

## 6. Minimum publishable evidence and explicit claim limits

Minimum evidence before a public demo is described as complete:

1. Executable vectors for initial arithmetic, every operation and evidence kind, public-only Bayes
   update, failure/retry, stop boundaries, exact costs/state versions, and terminal reveal.
2. A closed-schema test for every HTTP request/response and status code, including raw-body hashes,
   ambiguous retry, stale concurrency, and terminal mutation.
3. Independent recomputation of every posterior and ledger hash from public evidence only, plus
   deliberate mutation tests that fail closed.
4. Automated recursive leakage scans across Python objects, JSON, HTTP, browser DOM/storage/logs,
   build output, manifest, ledger, errors, source maps, caches, and prefetches before reveal.
5. Deterministic replay evidence showing world noise/failure independence from planner RNG and
   action ordering under the documented condition/repeat semantics.
6. Coverage of all five hidden causes across a declared multi-seed evaluation set if any claim is
   made about diagnostic performance. A single frozen fixture is sufficient only to demonstrate the
   interaction and audit loop.
7. Desktop/mobile visible-browser QA, keyboard/screen-reader review, reduced-motion review, 200%
   zoom, 320 px overflow check, and the recorded five-person ten-second comprehension check.
8. Regression proof that existing TEMPO, runner, ledger, world, planner, and leakage suites remain
   unchanged and passing.

Allowed public claim:

> This is a deterministic, auditable synthetic teaching benchmark in which a fixed Bayesian model
> updates five predefined working hypotheses and recommends another simulated diagnostic operation
> under a fixed artificial budget.

Explicitly disallowed claims:

- diagnosis, causal identification, or validation of a real molecule, electrolyte, electrode, or
  laboratory CV;
- a complete/physical CV simulator, realistic instrument digital twin, autonomous laboratory, or
  hardware control;
- calibrated real-world probabilities, uncertainty, transferability, or mechanism discovery;
- proof that `R2 >= 0.98` establishes diffusion control, a hard reversibility classification, `k0`,
  conductivity, stability, lifetime, capacity, or battery performance;
- realistic or equal laboratory cost, broad failure robustness, or recovery from failures other
  than the one declared timeout;
- superiority of a planner from one scenario/run, or a universal best experiment-selection policy;
- Argonne, DOE, publisher, or institutional endorsement.

## 7. Scope cuts and feasibility conclusion

The smallest feasible restricted-v1 implementation is:

- one frozen in-memory synthetic scenario and one frozen server-owned planner;
- one peak-summary visualization, not a generated full CV curve;
- five working-belief rows, two budgets, one bound recommendation, one Run action, one result, and
  one ordered timeline;
- seven exact diagnostic operations, but no unrestricted manual request builder in beginner mode;
- central server-owned inference and ledger verification;
- one deterministic timeout, one explicit QC-failure path, and idempotent network recovery;
- Expert/audit disclosure for exact evidence, beliefs, hashes, and post-terminal explicit reveal;
- a link to the existing strict conductivity workbench, not an embedded duplicate;
- no derived apparent D in the first UI slice even if the service can add it later;
- no published curve overlay, planner leaderboard, three-lane replay, LLM text, upload, accounts,
  persistence across restarts, telemetry, or production deployment.

Planner comparison does **not** belong in the restricted-v1 beginner experience. It may remain as a
separate saved-artifact benchmark only after its scenario set, planner versions, independent
campaign instances, seed routing, failure schedule, cost accounting, and predeclared component
metrics are verified. One committed run may illustrate different paths but cannot rank planners.

Feasibility is **conditional**. The current repository has reusable immutable contracts, seed
routing, validator, budget, hash-chain, artifact, leakage, and TEMPO arithmetic patterns. It does
not yet have the diagnosis-specific structured observation, central inference engine,
recommendation contract, interactive HTTP campaign store, or matching frontend. Those are bounded
additions only after B1–B8 are resolved; attempting to implement against the current documents would
force browser invention or undocumented server behavior.

Final plan-review conclusion: **not approved for implementation yet**. Resolve the contract/UX
interface first, then rerun independent plan QA before code work.
