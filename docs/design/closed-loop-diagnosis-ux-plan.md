# Closed-loop CV diagnosis — restricted-v1 UX plan

Status: product/UX plan complete; scientific contract and independent intake remain separate gates

Date: 2026-07-21

Scope: the smallest understandable closed-loop diagnosis experience built on the existing CV demo

Implementation status: plan only; no code, test, deployment, or repository publication is authorized

## 1. Product decision

The flagship should answer one question in ten seconds:

> **Why did this CV peak separation grow relative to the frozen healthy/control comparator, and
> what should we measure next?**

The default screen is one diagnosis loop, not a general autonomous-lab dashboard and not a
three-planner benchmark. It shows:

1. the scientific question and five competing hypotheses;
2. the experiment budget;
3. one recommended next experiment and a one-sentence reason;
4. the contract-supplied full synthetic healthy/control, abnormal, and latest CV curves at the
   visual center;
5. the observed result or explicit failure;
6. the resulting belief change; and
7. a short event timeline.

The current site already has useful building blocks: a prominent full CV chart, explicit
published/synthetic boundaries, saved replay controls, failure states, belief bars, budgets, and an
audit drawer. Restricted v1 should reuse those patterns but remove the competing narratives from
the beginner view.

## 2. Ten-second comprehension test

A first-time visitor should be able to answer all four questions without opening a drawer:

- **What is wrong?** The abnormal synthetic CV has a larger apparent peak separation than the
  frozen synthetic healthy/control comparator displayed beside it.
- **What might explain it?** Five named hypotheses are visible together.
- **What will the system do next?** One experiment and its reason are shown before the Run button.
- **What changed afterward?** The result/failure, belief movement, cost, and next recommendation are
  visible in the same viewport or immediately below it.

If a visitor must understand planners, seeds, hashes, ledgers, electrode cartoons, or the TEMPO
property workflow before answering these questions, the beginner view has failed.

## 3. Information architecture

### Beginner view — open by default

1. **Question strip** — question, provenance, and budget.
2. **Competing explanations** — five compact working-belief bars.
3. **Diagnosis bench** — server recommendation, contract-supplied full CV curves, and result/belief
   update.
4. **Run timeline** — one compact item per attempted experiment.
5. **Supporting Measurements** — collapsed by default but visibly named.
6. **Expert & audit details** — collapsed disclosure at the end.

### Expert & audit drawer — closed by default

- exact public state supplied to the selector;
- all eligible actions and costs;
- exact recommendation score/reason fields defined by the scientific contract;
- observation, validation, QC, exclusions, and failure record;
- before/after belief vector and update method/version;
- remaining attempt and operation budgets;
- run ID, scenario version, committed seeds/hashes, replay identity, and downloads;
- stop rule and post-run synthetic-truth reveal, only when the scientific contract permits it.

The drawer supplements the beginner story. It must not contain information necessary to understand
why the visible next experiment was recommended.

## 4. Desktop text wireframe

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ SCIENTIFIC DISCOVERY FLIGHT SIMULATOR · CLOSED-LOOP CV DIAGNOSIS            │
│ Why did peak separation grow relative to the frozen healthy control?        │
│ A saved synthetic diagnosis run — not a diagnosis of a real sample.         │
│ Healthy ΔEp {x} → abnormal ΔEp {y} · ◇ SYNTHETIC · Budget 3/4 left          │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────── COMPETING EXPLANATIONS ─────────────────────────────┐
│ Slow electron-transfer kinetics   █████  20%                                │
│ Uncompensated resistance          █████  20%                                │
│ Reference-electrode drift         █████  20%                                │
│ Electrode fouling                 █████  20%                                │
│ Concentration/preparation error   █████  20%                                │
│ Working beliefs inside the stated synthetic model; not calibrated truth.    │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────── NEXT EXPERIMENT ────────┐ ┌──────────── CURRENT FULL CV ────────────┐
│ ƒ DERIVED RECOMMENDATION        │ │ ◇ SYNTHETIC OBSERVATION                 │
│ Measure independent Ru          │ │                                         │
│ Why: best separates resistance  │ │        current                          │
│ from kinetic/fouling causes.    │ │           │ full contract-supplied CVs  │
│ Cost: 1 operation               │ │           └──────────── potential       │
│ [Run recommended experiment]    │ │ Baseline —  Latest —                    │
└─────────────────────────────────┘ └─────────────────────────────────────────┘
                                      ┌──────── RESULT & UPDATE ──────────────┐
                                      │ Before run: No result yet             │
                                      │ or                                    │
                                      │ RESULT · independent Ru = {value} Ω   │
                                      │ Belief moved: resistance 20% → 62%    │
                                      │ Budget: 2/4 operations left           │
                                      │ Next: {server recommendation}         │
                                      └────────────────────────────────────────┘

┌──────────────────────────── RUN TIMELINE ───────────────────────────────────┐
│ 1  Repeat CV  ✓ valid result   → beliefs updated   cost 1                  │
│ 2  Measure independent Ru  ⚠ operation failed     cost charged             │
│ 3  Next recommendation ready                                               │
└──────────────────────────────────────────────────────────────────────────────┘

▶ Supporting Measurements
  Independent Ru record · Conductivity (separate measurement path)

▶ Expert & audit details
```

Values and recommendations in this wireframe are illustrative UI copy. The implementation must
render only contract-authorized values and full-curve arrays from the current run; it must not
hard-code the example belief movement, reconstruct a curve from peak markers, or claim that Ru is
always the first recommendation.

## 5. Exact labels and copy

### Page and provenance

- Eyebrow: `SCIENTIFIC DISCOVERY FLIGHT SIMULATOR · CLOSED-LOOP CV DIAGNOSIS`
- H1: `Why did peak separation grow relative to the frozen healthy control?`
- Lede: `Test competing explanations by choosing the next useful experiment under a fixed budget.`
- Nonclaim: `Saved synthetic diagnosis run · not a diagnosis of a real sample · no hardware control`
- Published badge: `◆ PUBLISHED CONTEXT`
- Synthetic badge: `◇ SYNTHETIC EXPERIMENT · NOT A LAB MEASUREMENT`
- Derived badge: `ƒ DERIVED FROM CURRENT EVIDENCE`

### Question and budget

- Section: `THE SCIENTIFIC QUESTION`
- Question: `What best explains the increase in apparent peak separation from the frozen synthetic healthy/control comparator to the initial abnormal synthetic CV?`
- Comparator summary: `Frozen healthy/control ΔEp · {value} {unit}`
- Trigger summary: `Initial abnormal ΔEp · {value} {unit}`
- Help: `Both curves are synthetic contract fixtures. Their difference starts the question; the browser does not calculate or reinterpret it.`
- Budget: `Budget · {remaining}/{total} operations left`
- Secondary budget, when distinct: `Attempts · {used}/{limit}`
- Budget help: `Failed attempts remain visible and may consume the contract-defined cost.`

### Hypotheses

- Heading: `Competing explanations`
- `Slow electron-transfer kinetics`
- `Uncompensated resistance`
- `Reference-electrode drift`
- `Electrode fouling`
- `Concentration or preparation error`
- Help: `Working beliefs within five predefined synthetic hypotheses—not probabilities that a real sample has each mechanism.`

Do not label the highest bar `the cause`, `diagnosis confirmed`, or `ground truth`.

### Recommendation

- Heading: `Recommended next experiment`
- Provenance: `ƒ DERIVED FROM CURRENT EVIDENCE`
- Dynamic action label: `{server recommendation.operation display label}`
- Reason label: `Why this experiment`
- Reason copy: `max_expected_information` renders the server-issued text exactly:
  `This eligible experiment has the highest expected information gain under the public five-hypothesis model.`
  The browser never writes, scores, or paraphrases a reason.
- Cost: `Cost · {recommendation.measurement_cost} operation · {recommendation.attempt_cost} attempt`
- Primary button: `Run recommended experiment`
- Secondary control in expert mode only: `Choose another eligible experiment`
- Pending: `Choosing the next experiment…`

The active recommendation is a server-owned object with exactly the contract fields
`recommendation_id`, `state_version`, `planner_id`, `planner_version`, `operation`, `controls`,
`reason_code`, `reason_text`, `attempt_cost`, `measurement_cost`,
`expected_information_gain_nats`, and `action_input_hash`. The Run request binds to that identity
and its exact controls. Expert alternatives, if present, are also server-issued Recommendation
objects; the browser cannot edit controls, add a rationale, or declare eligibility.

### Central full synthetic CV

- Heading: `Synthetic CV comparison`
- x-axis: contract-defined potential plus reference scale, never just `Voltage`
- y-axis: contract-defined current/current-density unit
- Legend: `Frozen healthy/control comparator`, `Initial abnormal CV`, `Latest valid CV`
- Empty state: `Verified full synthetic CV arrays are unavailable; no curve is drawn.`
- Failure overlay: `Operation failed · no curve was added`
- Caption: `Full curves come from the verified synthetic response. The browser does not reconstruct them from peak markers. Failed operations are recorded and never plotted as zero.`

The chart shows the complete contract-supplied forward and reverse potential/current arrays. It
must decode the exact 122-point `Curve`, verify its 61-point forward/reverse grids, units,
directions, curve/evidence hashes, campaign/state identity, and reproduce the contract's discrete
argmax/argmin Peak extraction within its fixed tolerances before drawing. A thumbnail, sparkline,
peak-only interpolation, or generic smooth curve is not sufficient. Scalar operations leave the
current curve unchanged and add their result only to the result panel.

### Result and belief update

- Heading: `Result and belief update`
- Before run: `Run the recommended experiment to reveal the next saved observation.`
- Success badge: `VALID SYNTHETIC RESULT`
- Failure badge: `EXPLICIT OPERATION FAILURE`
- Failure body: render the contract-issued `failure_message` exactly; no synthetic replacement
  value is created.
- Belief delta: `{hypothesis}: {before}% → {after}%`
- No material change: `The observation did not meaningfully separate the current explanations.`
- Next-ready: `Next recommendation ready`
- Stop: `Diagnosis loop stopped`
- Stop copy comes only from the exact mapping below:
  - `budget_exhausted` → `Stopped · attempt or measurement budget exhausted.`
  - `confident_diagnosis` → `Stopped · confident diagnosis gate satisfied.`
  - `low_expected_information` → `Stopped · expected information is below the threshold.`
  Terminal precedence is budget exhaustion, confident diagnosis, then low expected information.

Use `working belief`, not `confidence`, in general UI prose. The browser renders all five
server-issued finite belief values only after checking that they sum to one within the contract
tolerance; it never normalizes, repairs, or recomputes an invalid vector.

### Timeline

- Heading: `Run timeline`
- Item title: `Experiment {n} · {action}`
- Item fields visible without expansion: `recommended because`, `result` or `failed`, `cost`, and
  largest belief movement.
- Current marker: `NEXT`
- Empty state: `No experiments run yet.`
- Failed item: `FAILED · attempt and operation cost recorded · working beliefs unchanged`
- Rejected item: `REJECTED · attempt charged · no experiment executed · working beliefs unchanged`
- Details link: `Show evidence and audit record`

### Supporting Measurements

- Drawer heading: `Supporting Measurements`
- Intro: `These measurements may support diagnosis but remain separate from ordinary CV inference.`
- Card: `Independent Ru`
- Card action: `Review resistance provenance`
- Card: `Conductivity`
- Conductivity copy: `Calculated only from an independent resistance and calibrated cell constant for the same sample/cell context. It is not inferred from CV.`
- Conductivity action: `Open the conductivity workbench`
- Target: `/tempo/#conductivity` unless the implementation contract explicitly embeds the existing
  strict form without duplicating its validation logic.

Conductivity must not appear as a sixth diagnosis hypothesis, a property of a molecule alone, or a
number inferred from the displayed CV.

### Expert drawer

- Summary: `Expert & audit details`
- Supporting line: `Action alternatives, exact state, QC, hashes, replay identity, and post-run limits`
- Tabs are unnecessary in restricted v1; use nested headings/details in document order.
- Truth control, when eligible: `Reveal synthetic benchmark truth`
- Truth warning: `Synthetic truth for this committed replay—not experimental truth.`

## 6. Core interaction and state transitions

The browser is a renderer of the frozen scientific contract. It does not calculate beliefs,
recommendations, reasons, eligibility, costs, full curves, or replacement observations.

```text
BOOT
  → LOADING_SCENARIO
  → READY_TO_RUN
  → RUNNING_OPERATION
       ├─ VALID_RESULT → APPLY_UPDATE → READY_TO_RUN or STOPPED
       ├─ EXPLICIT_FAILURE → APPLY_CONTRACT_FAILURE_UPDATE → READY_TO_RUN or STOPPED
       ├─ REQUEST_REJECTED_422 → APPLY_RETURNED_REJECTION_STATE → READY_TO_RUN or STOPPED
       └─ TRANSPORT_AMBIGUOUS → RECONCILING_IDEMPOTENT_REQUEST
              ├─ ORIGINAL_RESPONSE_RECOVERED → APPLY_UPDATE
              └─ CONFIRMED_NOT_RECORDED → RETRY_IDENTICAL_REQUEST
  → STOPPED
```

### BOOT / LOADING_SCENARIO

- Render the page skeleton, scientific question, hypothesis names, and provenance key.
- Disable Run and show `Loading committed diagnosis scenario…`.
- Do not display plausible default beliefs, budgets, recommendations, or curves before verification.

### READY_TO_RUN

- Render the verified comparator, abnormal/latest CV arrays, beliefs, budgets, recommendation,
  reason, and timeline returned by the backend.
- Enable Run only when `recommendation_id`, `state_version`, `planner_id`, operation/controls, and
  `action_input_hash` agree with the current verified campaign state.
- Record the currently rendered state version so late responses can be discarded.

### RUNNING_OPERATION

- Immediately disable Run and alternate-action controls.
- Change button text to `Running saved experiment…`.
- Preserve the prior curve and beliefs until a valid response arrives.
- Show a nonblocking progress message in an aria-live region.

### VALID_RESULT

- Validate response/run/state identity before rendering.
- Add the new curve or supporting measurement only when the observation type authorizes it.
- Animate belief bars only after text values have updated; motion is optional and disabled under
  reduced-motion preferences.
- Append exactly one timeline event and show the next recommendation or stop reason.

### EXPLICIT_FAILURE

- Display failure as the result, never as zero, an empty curve, or a successful observation.
- Do not add a curve: restricted-v1 timeout and QC-failure events always have `observation=null`.
- Append the charged costs and failure reason to the timeline.
- Validate that the returned five-value belief vector equals the previous verified vector and render
  `Working beliefs unchanged`; the browser never creates a neutral update itself.

### REQUEST_REJECTED_422

- Treat a scientific/validator rejection as a recorded campaign event, not a transport error.
- Apply the returned incremented `state_version`, append one `REJECTED` timeline item, consume one
  attempt, preserve measurement budget and the exact unchanged server belief vector, then render
  the returned next recommendation or terminal state.
- Show the returned finite `rejection_message` selected by its exact `RejectionCode`, followed by
  `Request rejected · attempt charged · no experiment executed · working beliefs unchanged.`
- Never resend the rejected action automatically.

### TRANSPORT_AMBIGUOUS / IDEMPOTENT RECOVERY

- A timeout, disconnect, or unreadable response does not justify claiming that no cost or mutation
  occurred. Keep the previous verified state visible and label it `Previous verified state`.
- Show `Connection lost after submission. Checking whether the experiment was recorded…` while the
  browser reconciles against the campaign state/ledger using the same uppercase HTTP method,
  canonical path, campaign ID, request ID, exact raw body bytes, state version, and hashes.
- If the event exists, recover and render its original recorded response. If it does not exist,
  enable `Retry identical request`; reuse the exact request ID and identical serialized bytes.
- Same scoped key `(method, canonical_path, campaign_id, request_id)` plus the same raw bytes must
  recover the original response without another event, noise draw, cost, or update. The same scoped
  key plus different bytes is a non-mutating 409; distinct endpoint paths never collide.
- Do not silently generate a new request ID or choose another experiment.

### INTEGRITY ERROR / NON-MUTATING 404 OR 409

- Keep the prior verified state visible but mark it `Previous verified state`.
- Show `The response could not be verified. Previous verified state retained.`
- Reconcile state/ledger before offering retry. A confirmed non-mutating 404/409 adds no timeline
  event and consumes no budget.

### STALE RESPONSE

- If scenario, mode, alternative action, reset, or state version changes while a request is in
  flight, abort it and invalidate its response.
- Announce `Outdated experiment response discarded.`
- Never append an event, alter budget, update belief, or change a curve from a stale response.
- Fetch the authoritative current state after discard; do not infer that the server did not mutate.

### STOPPED

- Replace Run with a disabled `Diagnosis loop complete` control.
- Show only the contract enum/copy mapping for `budget_exhausted`, `confident_diagnosis`, or
  `low_expected_information`, plus the final server belief distribution. Apply the contract's
  precedence in that order; `insufficient_budget` does not exist in restricted v1.
- Keep replay/reset and post-run truth in Expert & audit only.

### One frontend Envelope decoder

Every endpoint and error uses the contract's one closed `Envelope` shape, with exact fields
`schema_version`, `response_id`, `response_hash`, `request_id`, `idempotency_input_hash`,
`scenario_id`, `campaign_id`, `previous_state_version`, `state_version`, `previous_ledger_hash`,
`ledger_hash`, `status`, and `payload`. Nullability is exactly the endpoint matrix in the contract.
The browser implements one decoder and then switches only on payload `type`: `scenario`, `state`,
`ledger`, `reveal`, or `error`. Unknown/missing fields, payload types, enums, units, or illegal
nullability fail closed.

The `scenario` payload contains the exact Scenario, including 5 hypotheses, 12 concrete action
specifications, comparator and trigger fixtures. The `state` payload contains exact State and
nullable Event; `ledger` contains State and Events; `reveal` contains Reveal; `error` contains exact
ErrorCode/message and nullable State/Event. Observation `cv` requires Peak+Curve and null scalar
fields; observation `scalar` requires its exact feature/unit pair and null Peak/Curve. Failure,
rejection, and stop events have null observation.

Verification order is: closed Envelope/Payload schema → scenario/campaign/request and
previous/current identity → recompute `request_body_hash=SHA-256(exact raw request-body bytes)` and
`idempotency_input_hash=SHA-256(JCS({method,canonical_path,campaign_id,request_id,request_body_hash}))` →
RFC 8785 response hash → event/evidence/curve hashes → ledger linkage → state/event/budget/five-
belief reconciliation → Recommendation binding → observation/curve QC → atomic render. The browser
never repairs or partially renders. Scenario creation, campaign GET, actions, stop, ledger, reveal,
and all errors use this same decoder; endpoint-specific nullable fields follow the contract matrix.

For this identity, method is uppercase `POST`; canonical path is the literal route with canonical
campaign ID substituted and no query, fragment, or trailing slash. Retain those values and the exact
serialized body until reconciliation; never regenerate equivalent JSON for retry.

Reveal is available only after terminal state and an explicit click. It is non-mutating: no event,
cost, version, or ledger-hash change. Repeating the first reveal's exact request ID and serialized
bytes returns its cached Envelope byte-for-byte; a new request ID is a non-mutating
`REVEAL_ALREADY_COMPLETED` 409. The browser verifies the returned `CommitmentPayload` by checking
its scenario identity, equality of the returned and initially verified commitment, and
`SHA-256(JCS(commitment_payload))` equality to that commitment before showing truth. The private
cause, seed bundle, and 43-character base64url nonce never enter ordinary State, Event, Ledger,
error, DOM, cache, or storage before reveal; afterward they intentionally support public replay.
The nonce is generated once from exactly 32 CSPRNG bytes when the frozen scenario artifact is
created, then persisted: one scenario version keeps the same commitment across campaigns and
redeploys, while a new scenario version receives a new private nonce.

## 7. Beginner versus expert behavior

Beginner mode is not a switch that changes scientific behavior. It is the default disclosure level.
It exposes the same current state and result as expert mode with less metadata.

Beginner view shows:

- question;
- five explanations and working beliefs;
- budgets;
- recommendation, reason, and cost;
- central full curve;
- result/failure and belief delta;
- timeline; and
- obvious links to Supporting Measurements and Expert & audit.

Expert drawer adds identifiers, exact vectors, candidate-action table, QC, formulas/method versions,
hashes, seeds, replay artifacts, and allowed post-run truth. It never reveals future events, future
failures, private seeds, hidden mechanism, or evaluator internals during an active run.

## 8. Provenance and visual language

Use the existing visual vocabulary consistently:

| Layer | Mark | Meaning | Placement |
|---|---|---|---|
| Published | `◆` | cited context only | optional collapsed published-context card |
| Synthetic | `◇` | committed virtual experiment/observation | CV plot, results, failures, timeline |
| Derived | `ƒ` | recommendation or belief update calculated from current allowed evidence | recommendation and belief panels |

Rules:

- The central comparator is the frozen **synthetic healthy/control fixture supplied by the diagnosis
  contract**, not a published curve. Published reference curves remain separate collapsed context
  and are never overlaid as diagnosis input.
- Every central curve gets an on-chart provenance label, not only a page-level disclaimer.
- A derived recommendation is not an experiment result.
- A synthetic result is not published or measured data.
- Hidden synthetic truth remains visually and semantically separate from working beliefs.

## 9. Responsive and mobile behavior

### Desktop, ≥ 980 px

- Question/budget strip spans the page.
- Hypotheses use five equal rows, not five tiny cards.
- Diagnosis bench uses `minmax(240px, .65fr) minmax(420px, 1.35fr)` for recommendation and central
  plot; result/update sits below the plot or as a third column only at ≥ 1180 px.
- Timeline is horizontal only when every item remains at least 180 px wide; otherwise it scrolls in
  its own labelled region.

### Tablet, 721–979 px

- Recommendation first, full CV second, result/update third in one column.
- Hypothesis label, bar, before/after value remain on one row.
- Timeline becomes a two-column grid or vertical list.

### Mobile, ≤ 720 px

Order is fixed:

1. question + provenance;
2. budget;
3. recommendation + Run;
4. full CV plot;
5. result/failure;
6. belief bars;
7. timeline;
8. Supporting Measurements;
9. Expert & audit.

- No horizontal document overflow at 390 px or 320 px.
- The SVG uses a stable `viewBox`, `width: 100%`, and a minimum readable plot height around 260 px.
- Axis titles remain visible; reduce tick count before reducing font below 11 px.
- Hypothesis names may wrap; bars never force the document wider.
- Primary Run button is full width and at least 44 px high.
- Timeline uses a vertical left rule; any exact-data table scrolls inside its own labelled wrapper.

## 10. Accessibility

- Provide a skip link to `#diagnosis-workbench`.
- The scientific question is the main H1; section headings follow logical H2/H3 order.
- Recommendation updates and run completion use a polite `role="status"` live region. Integrity
  failures use `role="alert"`.
- The CV SVG has a dynamic `<title>` and `<desc>` stating provenance, axes, number of valid curves,
  and a plain trend summary. Do not depend on shape/color alone.
- Belief bars use native text values plus `aria-label="{hypothesis}, before {x}, after {y}"`.
- Use icon + word for success/failure; never green/red alone.
- Timeline is an ordered list. The current item uses `aria-current="step"`.
- All controls are keyboard reachable; Run retains focus after a result unless an error summary must
  receive focus.
- Expert `<details>` and Supporting Measurements use native `<summary>` with a 44 px target.
- Respect `prefers-reduced-motion`; no autoplay in the diagnosis loop.
- Focus is never moved merely because beliefs animate.

## 11. Loading, empty, error, and stale copy

| State | Exact visible message | Control behavior |
|---|---|---|
| Loading | `Loading committed diagnosis scenario…` | Run disabled |
| Ready | `Recommendation ready.` | Run enabled |
| Running | `Running saved experiment…` | Run/alternatives disabled |
| Valid result | `Experiment complete. Result and working beliefs updated.` | next Run enabled or stopped |
| Explicit failure | `Operation failed. No replacement value was created.` | next recommendation follows contract |
| 422 rejected action | `Request rejected · attempt charged · no experiment executed · working beliefs unchanged.` | apply returned state/version and next recommendation |
| Ambiguous network failure | `Connection lost after submission. Checking whether the experiment was recorded…` | reconcile state/ledger; controls disabled |
| Confirmed unrecorded request | `The request was not recorded.` | Retry identical request ID and bytes |
| Integrity/hash mismatch | `The response could not be verified. Previous verified state retained.` | reconcile; audit records error |
| Non-mutating 404/409 | `Request was not applied. Verified campaign state is unchanged.` | return to current recommendation |
| Stale response | `Outdated experiment response discarded.` | current state unchanged |
| `confident_diagnosis` | `Stopped · confident diagnosis gate satisfied.` | Run disabled |
| `low_expected_information` | `Stopped · expected information is below the threshold.` | Run disabled |
| automatic `budget_exhausted` | `Stopped · attempt or measurement budget exhausted.` | Run disabled |
| Scenario unavailable | `Diagnosis scenario unavailable. No synthetic fallback was generated.` | all run controls disabled |

Never use `N/A`, zero, an empty success card, or a generic smooth curve as a substitute for missing
or failed evidence.

## 12. Implementation file plan

This is the anticipated integration map, not authorization to edit scientific contracts.

### Existing browser files

- `demo/index.html`
  - make the restricted closed-loop diagnosis the primary synthetic flagship;
  - add stable hooks for question, hypotheses, budgets, recommendation, full CV, result, timeline,
    Supporting Measurements, and Expert & audit;
  - move the current three-planner comparison out of the beginner path.
- `demo/app.js`
  - add a single diagnosis-state renderer and explicit state machine;
  - consume only the frozen public scenario/action/observation contract;
  - bind Run to the exact server recommendation identity and serialized action bytes;
  - implement response/ledger identity and hash validation, abort/stale guards, idempotent
    reconciliation/retry, 422 returned-state application, timeline append, and accessible summaries;
  - render full synthetic CV arrays only when supplied and verified by the backend;
  - do not compute or repair beliefs, recommendation, reason, eligibility, costs, curves, or stop
    state in the browser.
- `demo/styles.css`
  - add diagnosis-bench, full-curve, result, belief, and vertical-timeline layouts;
  - preserve the current warm paper/green/indigo visual system and provenance shapes;
  - add 980/720/420 px behavior and 320 px overflow safeguards.

### Expected verification files

- `tests/test_cartoon_ui_contract.py` or a new focused UI-contract test selected by the integrator:
  stable hooks, exact labels, provenance, default disclosure, failure/stale copy, central full CV,
  conductivity placement, keyboard structure, and responsive guards.
- Existing scientific/runner/fairness/leakage tests remain owned by their implementation workers and
  must exercise the frozen contract, not this prose plan.
- `docs/CLOSED_LOOP_DIAGNOSIS_LIVE_TASKS.md`: durable status, ownership, gates, review evidence.
- Independent intake/final review under `docs/reviews/`: separate ownership and verdict.

Do not duplicate the strict TEMPO conductivity implementation in `app.js`. Link to or reuse the
existing `/tempo/#conductivity` workflow so its structured provenance and explicit review gates stay
authoritative.

## 13. Explicit scope cuts — hide or postpone

Hide from the default flagship path:

- the large three-electrode apparatus animation and seven-step replay;
- simultaneous Random / Fixed Grid / Information Gain lanes;
- complete metric tables, run seeds, hashes, JSON downloads, and truth reveal;
- the full TEMPO six-rate input table and structured conductivity form;
- all alternative-action controls until Expert & audit is opened.

Retain these as collapsed context/audit, a separate route, or a later benchmark page. Do not delete
verified artifacts merely to simplify the screen.

Postpone beyond restricted v1:

- real user-uploaded CV diagnosis;
- automatic peak picking or curve segmentation;
- free-form LLM hypotheses, recommendations, or explanations;
- novel/unanticipated mechanism discovery;
- hardware/instrument control or live acquisition;
- real-material causal diagnosis or institutional endorsement;
- molecule selection, formulation optimization, conductivity inference from CV, `k0` inference,
  reference-scale conversion, or a hard reversibility label;
- planner leaderboard or claims that one strategy is universally best;
- multi-sample campaigns, multi-objective optimization, microscopy, and cross-domain worlds;
- accounts, saved cloud sessions, collaboration, comments, and production telemetry.

Also defer nonessential visual polish—decorative lab animation, elaborate transitions, custom chart
tooltips, theme variants, and illustration work—until the plain end-to-end loop passes comprehension,
scientific, accessibility, and failure-state review.

## 14. UX acceptance criteria

- At 1180, 980, 720, 390, and 320 px, the document has no horizontal overflow and the full CV is
  readable.
- Before opening a drawer, the page visibly contains the question, all five hypotheses, remaining
  budget, next experiment, reason, full CV, result/failure area, belief update, and timeline.
- A naive five-person comprehension check can answer the four questions in section 2 within ten
  seconds after the verified scenario loads.
- Published, synthetic, and derived elements each carry their own label; no published curve appears
  as synthetic evidence.
- Run is unavailable during loading/running/stopped states and no autoplay occurs.
- Failure adds no fake zero/curve; stale or unverifiable responses alter no state.
- Recommendation reason is visible in beginner mode and comes unchanged from the backend's finite
  reason code/text mapping; Run is bound to recommendation/state/hash identity.
- A 422 rejection visibly consumes one attempt, advances to the returned version, appends a rejected
  timeline event, and preserves the server-returned measurement budget and beliefs.
- Ambiguous transport failure reconciles before retry; identical retry creates no duplicate event,
  cost, noise draw, curve, or belief update.
- Only the four exact stop identifiers/copy mappings in section 5 are rendered.
- All five server beliefs must be finite and normalized; invalid vectors fail closed and are never
  renormalized by the browser.
- Supporting Measurements contains Conductivity with the explicit independent-measurement
  limitation and a stable path to the strict TEMPO workflow.
- Expert details expose the complete replay/audit record without leaking future or hidden state
  during the active loop.
- Keyboard, screen-reader text, reduced motion, focus behavior, and 44 px targets pass browser QA.

## 15. Contract alignment gate

The UX and scientific contract now share the same restricted-v1 decoder and semantics:

- exhaustive 122-point Curve, extracted Peak, Observation, comparator, trigger, unit, QC, nullability,
  and hash rules;
- the same 12-field Recommendation, planner/version, EIG, eligibility, reason, and binding;
- one closed Envelope and discriminated Payload union for every endpoint and error;
- exact Event/status/error/rejection enums, 422 sanitation and `1/0` accounting;
- method/path/campaign/request/body-scoped byte-identical retry, non-mutating 400/404/409/500, and
  atomic verification;
- disjoint terminal precedence and three exact stop messages; and
- terminal-only, non-mutating Reveal that cryptographically opens the original commitment and has
  byte-identical same-scoped-request replay.

The final protocol correction is complete but implementation remains blocked pending independent QA4
approval. Browser examples remain illustrative; no default may substitute for a missing backend
field.
