# Independent plan review v3 — closed-loop CV diagnosis restricted v1

Review date: 2026-07-21

Reviewed: corrected contract, corrected UX plan, live task board, and prior B1–B8 findings.

## Verdict

**REQUEST CHANGES**

Curve/QC, Recommendation fields, the shared Envelope/Payload decoder, sanitized 422 events, and
terminal precedence now align. Two protocol-level blockers remain.

## Blocking findings

### 1. Reveal does not cryptographically open the original commitment

`Scenario.commitment` has no frozen construction. `Reveal.verification_hash` is defined as the hash
of `{commitment,cause,world_seed,noise_seed,failure_seed}`, while verification only requires the
revealed commitment string to equal `Scenario.commitment`. This proves that the reveal fields were
hashed together after reveal; it does not prove that the original commitment committed to that
cause and those seeds. Any cause/seeds can be paired with the unchanged commitment and a newly
computed valid `verification_hash`.

Freeze the commitment preimage, including scenario identity and all revealed private values, and
require the browser to recompute that commitment from the reveal and compare it with the original
Scenario commitment. The separate verification hash may remain only if its distinct purpose is
defined.

### 2. Idempotency scope is ambiguous across endpoints

The stop and reveal bodies have the same shape and may be byte-identical. The contract keys replay
only by `request_id` plus request bytes, without stating whether the HTTP method/path participates
in the key. Reusing one ID/body first at `/stop` and then at `/reveal` can therefore either replay
the stop Envelope or execute reveal, depending on implementation.

Freeze the key scope, for example
`(campaign_id, HTTP method, canonical path, request_id)`, while retaining byte-identical body replay
within that scope and non-mutating conflict for changed bytes. The UX reconciliation identity must
use the same scope.

## B1–B8 disposition

| Finding | Disposition | Evidence |
|---|---|---|
| B1 | **CLOSED** | Curve, fixture, extraction, tolerances, units, hashes, and likelihood boundary align. |
| B2 | **CLOSED** | Both documents use the same 12-field Recommendation and server-owned reason/binding. |
| B3 | **CLOSED** | Both documents use the same closed Envelope and discriminated Payload decoder. |
| B4 | **OPEN** | Replay behavior is defined, but its cross-endpoint key scope is not. |
| B5 | **CLOSED** | Base parse failures are 400; semantic 422 events have exact sanitation, reasons, and accounting. |
| B6 | **OPEN** | Stop precedence aligns, but reveal does not open the initial commitment. |
| B7 | **CLOSED** | Complete belief vectors remain finite and normalized. |
| B8 | **CLOSED** | Comparator and trigger remain explicit, public, distinct, and excluded from Bayes. |

Approval requires only the two protocol corrections above and one final focused reread.
