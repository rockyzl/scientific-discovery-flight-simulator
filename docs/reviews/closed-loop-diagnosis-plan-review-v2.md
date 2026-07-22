# Independent plan review v2 — closed-loop CV diagnosis restricted v1

Review date: 2026-07-21

Reviewed: the corrected scientific contract, UX plan, prior review, live task board, and the current
`demo/`, `src/discovery_flight_simulator/`, and test boundaries.

## Verdict

**REQUEST CHANGES**

The frozen arithmetic checks pass: both CV sweeps contain 61 points, the peak-current ratio is
exactly `1.02`, the two five-belief fixtures sum to `1.0`, and the quadrature weights can be
normalized from `0.9999999999`. The current implementation is also a viable base for an additive
campaign service. Implementation is nevertheless blocked by the exact interface defects below.

## Blocking findings

### 1. B1 is not yet an executable full-curve contract

The contract gives the grid and generator, but `Curve` is not included as an exhaustive closed wire
type and the scenario response does not say whether `comparator` and `initial_trigger` contain a
`Peak`, a `Curve`, both hashes, or some other exact shape. It also requires “scalar/curve peak
consistency QC” without defining its algorithm or tolerance. This matters because noisy future peak
positions need not lie on the `0.005 V` grid, so equality to the discrete curve maximum is generally
impossible. Freeze the exact comparator/trigger/observation curve objects and an implementable QC
rule before the browser is required to fail closed on them.

### 2. B2/B3 still have direct Recommendation and response-schema conflicts

The contract's exact `Recommendation` has `planner_version` and
`expected_information_gain_nats`; the UX's asserted exact field list omits both. More broadly, the
UX requires a flat mutable-response identity bundle (`schema_version`, `request_id`, previous and
current ledger hashes, completion status, remaining budgets), while the contract freezes a nested
`Envelope={response_id,response_hash,state,event}` that does not contain several of those fields.
The scenario and reveal responses are not Envelopes, yet the UX verification order assumes a
response hash. These two documents cannot generate one closed decoder.

The purported closed types also leave wire-critical values open: `event_type`, observation
`kind`/feature/unit combinations, nullable fields, response/error codes, `response_id`, and exact
scenario action/comparator/trigger shapes. Freeze one exhaustive schema per endpoint and make the
UX consume that exact nesting and field set.

### 3. B5 cannot represent the 422 events it requires

Schema, eligibility, and binding failures must all produce a charged `rejected` event, but the exact
`Event` requires `recommendation_id`, `operation`, and `controls` without nullable/sanitized rules.
A missing or wrongly typed one of those fields is itself a schema failure, so a conforming rejected
event cannot always be constructed. The 422 Envelope also has no frozen rejection code/message,
although the UX requires an exact visible rejection reason. Define the rejected-event payload for
each validation class, including nullability/sanitization and the public reason enum; preserve the
already aligned `1/0`, unchanged-belief, incremented-version semantics.

### 4. B6 stop/reveal behavior is not deterministic at the boundaries

Every action costs one measurement. Therefore “no one-measurement action fits” occurs at
`measurement_used=10`, exactly where automatic `budget_exhausted` also applies. No precedence is
defined, so two terminal reasons are valid for the same state and `insufficient_budget` has no
distinct reachable state. Freeze evaluation order or change the rule/costs so the reasons are
disjoint. The contract's exact visible strings also omit the terminal periods present in the UX.

Reveal needs the same precision: declare whether a successful terminal reveal is non-mutating or
appends an event/advances state/charges cost, and define repeated reveal behavior. The current
“every mutating 200/422” sentence does not classify it.

## B1–B8 disposition

| Finding | Disposition | Evidence |
|---|---|---|
| B1 | **OPEN** | Grid/generator exist; closed curve-bearing schemas and exact QC do not. |
| B2 | **OPEN** | Recommendation exists, but its contract and UX exact field lists conflict. |
| B3 | **OPEN** | Envelope nesting and required UX identity bundle do not align; endpoint schemas remain incomplete. |
| B4 | **CLOSED** | Same ID + identical bytes replays the original status/body; changed bytes are non-mutating 409. |
| B5 | **OPEN** | Accounting is aligned, but malformed requests cannot always populate the required rejected Event and no reason enum is frozen. |
| B6 | **OPEN** | Terminal rules overlap; copy and successful/repeated reveal semantics are not exact. |
| B7 | **CLOSED** | Both complete vectors are finite, normalized, and satisfy the stated pass/fail intent. |
| B8 | **CLOSED** | Healthy/control and abnormal fixtures are distinct, numeric, public, display-only, and excluded from Bayes. |

Approval requires closing only the open rows above and rerunning this contract/UX alignment check.
