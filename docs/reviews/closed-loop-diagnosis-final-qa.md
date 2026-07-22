# Closed-loop CV diagnosis — independent final QA

Date: 2026-07-21
Reviewer role: independent implementation QA
Decision: **APPROVE**

## Release verdict

The restricted-v1 closed-loop CV diagnosis is implemented consistently across the scientific
contract, Python service, HTTP adapter, browser client, tests, and user documentation. No release
blocker remains in the reviewed workspace.

This approval is for the local synthetic research prototype described by the repository. It is not
an approval of a production deployment, physical CV model, real-sample diagnosis, instrument
control system, or calibrated scientific confidence claim.

## Verification performed

The final workspace passed:

```text
.venv/bin/pytest -q        175 passed in 17.53 s
.venv/bin/ruff check .     passed
node --check demo/app.js   passed
node --check demo/tempo.js passed
git diff --check           passed
```

The Python suite includes an executable Node adversarial harness for browser reconciliation. It
rejects contradictory beliefs, budget totals, ledger links, transition success counts,
cross-campaign ledger responses, and cross-campaign reveal responses.

## Live HTTP adversarial review

A fresh campaign was exercised through the running adapter at `127.0.0.1:8004`, not only through
direct unit calls.

| Case | Verified result |
| --- | --- |
| Public scenario and all preterminal responses | no private truth, seed bundle, nonce, or commitment preimage |
| Campaign creation | `201`, State version 0, valid scoped input identity |
| Parseable changed-byte create replay | non-mutating `409`; `idempotency_input_hash` present |
| Same scoped action and identical raw bytes | byte-for-byte replay with the original status |
| Same scoped request ID with changed bytes | non-mutating `409 IDEMPOTENCY_CONFLICT` |
| Same request ID on the stop endpoint | endpoint-scoped independently; charged `422` rather than colliding |
| Charged rejection | event cost `1 attempt / 0 measurements`; observation absent; beliefs unchanged |
| Accepted execution number two | explicit `TIMEOUT`; no observation or replacement curve; beliefs unchanged; contract costs charged |
| Terminal campaign | stopped by `low_expected_information`; ledger and final State reconciled |
| Reveal before terminal | `409 REVEAL_NOT_AVAILABLE`; no private data leaked |
| First terminal reveal | commitment recomputed successfully from the returned preimage |
| Identical reveal retry | original status and bytes replayed exactly |
| Different reveal request after opening | `409 REVEAL_ALREADY_COMPLETED` |

The persisted scenario commitment was also stable across service restart during review.

## Browser and UX review

The visible Windows Chrome session successfully loaded a fresh campaign and ran the recommended
experiment against the real local API. The first screen makes the scientific question, comparator
change (`0.060 V` to `0.100 V`), five competing explanations, budgets, recommended next experiment,
reason, cost, full synthetic CV, and evidence timeline visible. A successful action added the full
verified curve and updated the server-issued beliefs and budgets.

Responsive inspection found no horizontal document overflow at viewport widths `1180`, `1037`,
`980`, `901`, `900`, `720`, `390`, or `320` CSS pixels. The primary action remained at least
`44 px` high. Supporting Measurements and Expert/audit details remained closed by default. The
accessible curve table retains all 122 backend-supplied points while its hidden layout no longer
forces horizontal overflow.

Static accessibility checks cover the live status and alert regions, keyboard-native controls,
text-equivalent curve table, reduced-motion rules, and narrow reflow. This review did not include a
full manual session with a specific commercial screen reader.

## Blockers found and resolved during QA

Final QA initially found four implementation-level blockers. All were corrected and reverified:

1. A narrow-screen status badge and then the off-screen accessible curve table caused horizontal
   overflow at specific widths.
2. The browser validated individual hashes but did not initially reconcile the complete
   Event/State/ledger/budget/belief relationship.
3. The browser applied some response state before ledger verification, so a later integrity failure
   could replace the previous verified screen.
4. Endpoint/campaign/version/ledger identity was not initially bound tightly enough for GET,
   action, creation, and reveal responses; parseable create errors also omitted the scoped input
   hash.

The final code now performs endpoint-aware closed validation and atomically commits UI state only
after the response and fetched ledger agree.

## Scientific and product limitations (non-blocking)

- The deliberately narrow Gaussian toy likelihood can drive the displayed posterior extremely
  close to zero or one after one successful observation. The UI and documentation correctly call
  these values working beliefs inside five predefined synthetic hypotheses, not calibrated
  confidence for a real sample. A future UI refinement could render a rounded `100.0%` as
  `>99.9%` to reinforce that boundary.
- The full curves are deterministic synthetic evidence generated by a frozen benchmark contract;
  they are not a validated physical electrochemical simulator.
- The local review server is not production infrastructure. Deployment durability, authentication,
  rate limiting, monitoring, privacy operations, and multi-user isolation require a separate
  production review.
- The published all-iron CV material and the older planner replay remain supporting contexts and
  are correctly separated from the new synthetic diagnosis likelihood loop.

## Handoff

The implementation may proceed to the repository's normal commit/release process. Before release,
update the live task board from `final QA pending` to approved and replace its earlier test count
with the final result above. This review itself authorizes no commit, push, or deployment.
