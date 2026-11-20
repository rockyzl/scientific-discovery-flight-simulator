# RFB workflow contract

**Status:** frozen contract for the implemented RFB HTTP integration, awaiting
independent API/workflow QA.

## Scope

RFB V1 is a process-local, deterministic, simulated 0D virtual-cell campaign.
It uses `rfbzero==1.0.1` for numerical outcomes and LangGraph with SQLite
checkpoints for recommend -> mandatory human approval -> resume orchestration.
It has no LLM planner, network/hardware action, laboratory control, digital-twin
claim, or calibrated physical-performance claim.

## Authority and boundaries

SQLite is the source of truth for a campaign's public state, canonical event
journal, decisions, costs, executions, and private execution leases. Every
mutation verifies the persisted event chain and uses the campaign `revision` for
optimistic concurrency. LangGraph state and checkpointer entries are disposable
orchestration state: after restart, they must be reconstructed from verified
SQLite state and may never invent, replace, or supersede a campaign decision.

Public campaign state may include the frozen public scenario, policy/version,
recommendation, decision, completed outcome, utility record, cost accounting,
mode/eligibility, and event chain. It must exclude private oracle model values,
execution identity, lease tokens/generation/expiry, worker details, reviewer
identity or notes, and checkpointer internals. Public fields carry
`provenance: simulated` where applicable.

## Public policy metadata schema

Public `policy_metadata` is the closed RFB V1 schema, not an arbitrary JSON
extension point. It permits an empty mapping or any valid subset of these
explicitly named optional fields:

| Field | Allowed value |
| --- | --- |
| `selection_order` | One of `declared_candidate_order`, `deterministic_public_history`, or `deterministic_scalar_utility_ucb`. |
| `hidden_layer_count` | A non-negative integer. |
| `token_count` | A non-negative integer. |
| `tokenizer` | One of `byte-pair`, `wordpiece`, or `sentencepiece`. |
| `private_config_hmac_sha256` | A lowercase, 64-character HMAC/SHA-256 commitment. |

Unknown keys, nested arbitrary values, aliases or casing variations, raw
private data, secrets or raw tokens, and lease, reviewer, or oracle data are
rejected. This closed schema prevents public-artifact leakage. The
`private_config_hmac_sha256` value is a commitment, not a signature.

These metadata fields do not change the campaign boundary: RFB V1 remains a
simulated 0D virtual cell with no hardware, LLM, or network action.

## Lifecycle and approval

| Phase | Permitted transition | Meaning |
| --- | --- | --- |
| `awaiting_recommendation` | save a canonical recommendation | Enters `awaiting_review`. |
| `awaiting_review` | `approve` | Records an unchanged decision and enters `approved`; no oracle call or cost. |
| `awaiting_review` | `approve_with_edit` | Records intervention, replaces the pending canonical recommendation, remains in review, and becomes unrankable. |
| `awaiting_review` | `reject` | Records intervention, removes the pending recommendation, returns to `awaiting_recommendation`, and becomes unrankable. |
| `approved` | `resume`/execution claim | Creates one private lease, reserves one attempt and measurement, and enters `executing`. |
| `executing` | execution commit | Commits one canonical outcome/utility/cost and returns to `awaiting_recommendation`. |
| `awaiting_review` | `abort` | Enters `aborted` as an unrankable workflow case study. |

Every new campaign begins in `strict_benchmark`. Any edit or rejection sets
`human_intervened: true`, `mode: workflow_case_study`, and
`comparison_eligible: false`; therefore it is unrankable. No policy-specific or
partial ranking may be reported after an intervention.

An approval is evidence only. It must not itself execute a run, acquire a
lease, reserve budget, call RFBzero, derive an outcome, or commit a measurement
cost. Only a subsequent `resume` may do so.

## Public HTTP API

All successful campaign responses use this envelope:

```json
{
  "campaign": { "...": "CampaignState public fields" },
  "event_head_sha256": "64-character lowercase SHA-256"
}
```

`CampaignState` is the public serialized state: it includes `workflow_version`,
`campaign_id`, `revision`, `phase`, policy metadata, public scenario, pending
recommendation, decisions, executions, rejected action IDs, cumulative/reserved
costs, mode, eligibility, intervention flag, and current approved decision.

| Route | Request and response intent |
| --- | --- |
| `GET /api/rfb/scenario` | Returns `200 {"scenario": <public RFBScenarioV1>}`. It never returns the private oracle configuration or execution identity. |
| `POST /api/rfb/campaigns` | Accepts exactly `{"campaign_id": "...", "scenario_id": "rfbzero_cell_v0", "policy_id": "random|fixed_grid|constrained_bo"}`. The service resolves the pinned scenario and policy version, creates a strict campaign, and returns `201` with the campaign envelope. Reusing a campaign ID returns `409`; creation is deliberately not a duplicate-success operation. |
| `GET /api/rfb/campaigns/{campaign_id}` | Returns `200` with the verified current campaign envelope. |
| `GET /api/rfb/campaigns/{campaign_id}/events` | Returns `200 {"campaign_id": "...", "event_head_sha256": "...", "events": [<public canonical event>, ...]}`. Each event retains `audit_timestamp`, but its SHA-256 is calculated from logical content without that timestamp. |
| `POST /api/rfb/campaigns/{campaign_id}/approvals` | Accepts `decision_id`, `expected_revision`, and `decision`. `approve` has no extra fields; `reject` requires non-empty `reason_code`; `approve_with_edit` requires `edited_recommendation`, a full canonical `RFBRecommendationV1`. Returns `200` with the campaign envelope and records only the decision. |
| `POST /api/rfb/campaigns/{campaign_id}/resume` | Accepts exactly `{"decision_id": "...", "expected_revision": <integer>}`. It may execute exactly one matching unchanged approved decision. It returns `202` with the current campaign envelope for a newly advanced transition, or `200` for an exact idempotent repeat. Idempotency is decision-scoped and it must never create a second execution/cost. |

No route accepts client-provided private oracle configuration, lease material,
execution identity, audit timestamp, reviewer identity, or output/utility value.
The service supplies audit time and derives the utility from the committed
canonical outcome.

Every error uses this shape:

```json
{
  "error": {
    "code": "machine_readable_code",
    "message": "safe concise explanation",
    "details": {}
  }
}
```

Use `400` for malformed JSON or a wrong request shape, `404` with
`campaign_not_found` for an unknown campaign, `409` for `duplicate_campaign`, `revision_conflict`,
`invalid_phase`, `duplicate_decision`, or `execution_in_progress`, and `422` for
a semantically invalid policy, recommendation, protocol, or decision payload.
An event-chain or persisted-state integrity failure is fail-closed with `500`
and code `integrity_failure`; the response must not expose private material.

## Resumability and logical idempotency

An execution claim is bound to campaign, approved `decision_id`,
recommendation, request, action, public scenario identity, execution identity,
and utility identity. The first matching resume creates a private renewable
lease and one public reservation. A live lease prevents concurrent execution.
An expired lease may be renewed only for that same logical execution.

Completion atomically replaces the reservation with the single committed cost
and stores one canonical execution. Repeating `resume` after a commit returns
that committed execution rather than rerunning it. A stale lease, mismatched
action/outcome, obsolete revision, or different execution semantics fails
closed. A crash before commit may recompute the deterministic simulation, but
must not create a second logical execution or second cost.

## Reproducibility record

The public campaign export and its RFB artifact/replay record must bind:

- `rfb_workflow_v1` and the applicable RFB artifact version;
- simulated provenance; scenario/version/public projection, candidate-set,
  validator, cost-model, and utility hashes;
- policy/version, recommendation basis revision/event head, action/request/
  decision identities, and all canonical events;
- canonical outcome, derived utility record, QC state, and costs;
- RFBzero adapter/reducer identity and pinned dependency identity, including
  `rfbzero==1.0.1`; and
- event-chain head and payload hashes.

Replay is logical rather than wall-clock or byte-for-byte. It verifies the
identity/event chain and consumes captured decision records; it never prompts a
reviewer again. `audit_timestamp` is format-validated audit metadata, not event
content, and is excluded from event hashes.

## Acceptance criteria

The RFB workflow is not complete until integration demonstrates all of the
following:

- Each listed route conforms to its request, success, and error contract.
- SQLite remains authoritative across a process restart; LangGraph resumes only
  from verified SQLite state.
- Approval has no execution side effect; only `resume` can start the approved
  simulated action.
- Concurrent/retried resume requests result in exactly one committed execution
  and one attempt/measurement debit.
- Edit/reject makes the whole strict comparison human-intervened and unrankable.
- Public state/events contain no private oracle, lease, reviewer, or checkpoint
  data, and RFB code has no LLM, hardware, or network-control path.
- Public `policy_metadata` accepts only the strict RFB V1 schema and rejects
  unknown, nested, aliased, mis-cased, or private values.
- Artifact/replay verification rejects changed identities or logical event
  content while accepting changed audit timestamps.
