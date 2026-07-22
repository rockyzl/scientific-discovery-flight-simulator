# Independent plan review v4 — closed-loop CV diagnosis restricted v1

Review date: 2026-07-21

Reviewed: corrected scientific contract, corrected UX plan, live task board, and QA1–QA3 blockers.

## Verdict

**APPROVE**

No plan-level blocker remains. The contract and UX now define one implementable restricted-v1
decoder and state machine. Approval authorizes implementation against these frozen documents; it
does not waive their automated, leakage, accessibility, or final-QA gates.

## Focused verification

- **Commitment opening:** `Scenario.commitment` is the SHA-256/JCS digest of one persisted
  `CommitmentPayload` containing scenario identity, hidden cause, all three seeds, and a 32-byte
  CSPRNG nonce. Reveal returns that exact preimage; the browser checks identity, commitment
  equality, and recomputed digest before displaying truth.
- **Preterminal boundary:** the preimage, nonce, truth, seeds, and future failure are excluded from
  every ordinary payload, error, ledger, manifest, DOM/storage/cache, and source map. Only the
  digest is public until terminal state plus explicit reveal.
- **Scoped idempotency:** every parseable POST binds uppercase method, canonical path, campaign ID,
  request ID, and exact raw-body hash into `idempotency_input_hash`. Identical replay is
  byte-for-byte within that scope; changed bytes are non-mutating 409; stop and reveal cannot
  collide across paths. The UX preserves the same raw bytes and scope during reconciliation.
- **Decoder alignment:** contract and UX share the same Envelope fields, Payload discriminator,
  endpoint nullability, Recommendation fields, Event sanitation, hash order, terminal precedence,
  and non-mutating reveal behavior.

## B1–B8 disposition

| Finding | Disposition |
|---|---|
| B1 | **CLOSED** — exhaustive Curve/Peak/Fixture/Observation shape and discrete QC agree. |
| B2 | **CLOSED** — exact 12-field server Recommendation, eligibility, reason, and binding agree. |
| B3 | **CLOSED** — one closed Envelope/Payload decoder and verification order agree. |
| B4 | **CLOSED** — method/path/campaign/request/body-scoped replay and conflict behavior agree. |
| B5 | **CLOSED** — parse failures and sanitized charged semantic rejections are unambiguous. |
| B6 | **CLOSED** — terminal precedence and commitment-opening Reveal are exact and aligned. |
| B7 | **CLOSED** — complete belief fixtures are finite and normalized. |
| B8 | **CLOSED** — comparator and trigger are explicit, distinct, and excluded from Bayes. |
