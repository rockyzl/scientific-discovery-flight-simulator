import assert from "node:assert/strict";
import { createHash, webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const hooks = {};
const context = vm.createContext({
  console,
  TextEncoder,
  window: { crypto: webcrypto },
  document: { addEventListener() {} },
  __DIAGNOSIS_TEST_HOOKS__: hooks,
});
vm.runInContext(readFileSync(new URL("../../demo/app.js", import.meta.url), "utf8"), context);

const prior = [0.2, 0.2, 0.2, 0.2, 0.2];
const posterior = [0.05, 0.8, 0.05, 0.05, 0.05];
const campaignId = "campaign-browser-reconciliation";
const genesis = createHash("sha256")
  .update(JSON.stringify({ campaign_id: campaignId, scenario_id: "cv_diagnosis_v1", scenario_version: "1.0.0" }))
  .digest("hex");

const event = {
  event_id: "event-1",
  event_index: 0,
  event_type: "action",
  request_id: "request-1",
  idempotency_input_hash: "1".repeat(64),
  state_version_before: 0,
  state_version_after: 1,
  recommendation_id: "2".repeat(64),
  operation: "measure_ru",
  controls: {},
  status: "success",
  failure_code: null,
  failure_message: null,
  rejection_code: null,
  rejection_message: null,
  attempt_cost: 1,
  measurement_cost: 1,
  observation: { kind: "scalar" },
  beliefs_before: prior,
  beliefs_after: posterior,
  previous_event_hash: genesis,
  event_hash: "3".repeat(64),
};

const state0 = {
  campaign_id: campaignId,
  scenario_id: "cv_diagnosis_v1",
  scenario_version: "1.0.0",
  state_version: 0,
  beliefs: prior,
  budget: { attempt_used: 0, measurement_used: 0 },
  success_count: 0,
  successful_operations: [],
  last_valid_curve_hash: null,
  ledger_head_hash: genesis,
};
const state1 = {
  ...state0,
  state_version: 1,
  beliefs: posterior,
  budget: { attempt_used: 1, measurement_used: 1 },
  success_count: 1,
  successful_operations: ["measure_ru"],
  ledger_head_hash: event.event_hash,
};

await hooks.reconcileLedger(state1, [event], prior);
hooks.reconcileTransition(state0, state1, event);

await assert.rejects(
  hooks.reconcileLedger({ ...state1, beliefs: prior }, [event], prior),
  /final beliefs do not reconcile/,
);
await assert.rejects(
  hooks.reconcileLedger({ ...state1, budget: { attempt_used: 1, measurement_used: 0 } }, [event], prior),
  /costs do not reconcile/,
);
await assert.rejects(
  hooks.reconcileLedger(state1, [{ ...event, previous_event_hash: "4".repeat(64) }], prior),
  /previous hash is discontinuous/,
);
assert.throws(
  () => hooks.reconcileTransition(state0, { ...state1, success_count: 0 }, event),
  /success count do not reconcile/,
);

const ledgerEnvelope = {
  request_id: null,
  idempotency_input_hash: null,
  scenario_id: "cv_diagnosis_v1",
  campaign_id: campaignId,
  previous_state_version: 1,
  state_version: 1,
  previous_ledger_hash: event.event_hash,
  ledger_hash: event.event_hash,
  payload: { type: "ledger", state: { campaign_id: campaignId, state_version: 1, ledger_head_hash: event.event_hash } },
};
hooks.validateGetIdentity(ledgerEnvelope, `/api/v1/closed-loop/campaigns/${campaignId}/ledger`);
assert.throws(
  () => hooks.validateGetIdentity({ ...ledgerEnvelope, campaign_id: "campaign-attacker" }, `/api/v1/closed-loop/campaigns/${campaignId}/ledger`),
  /bound to another campaign/,
);

const revealPrepared = {
  campaignId,
  body: { request_id: "reveal-request", expected_state_version: 1 },
  inputHash: "5".repeat(64),
  baseStateVersion: 1,
  baseLedgerHash: event.event_hash,
};
const revealEnvelope = {
  request_id: revealPrepared.body.request_id,
  idempotency_input_hash: revealPrepared.inputHash,
  scenario_id: "cv_diagnosis_v1",
  campaign_id: campaignId,
  previous_state_version: 1,
  state_version: 1,
  previous_ledger_hash: event.event_hash,
  ledger_hash: event.event_hash,
  payload: { type: "reveal", reveal: {} },
};
hooks.validatePreparedIdentity(revealEnvelope, revealPrepared, 200);
assert.throws(
  () => hooks.validatePreparedIdentity({ ...revealEnvelope, campaign_id: "campaign-attacker" }, revealPrepared, 200),
  /bound to another campaign/,
);

console.log("diagnosis reconciliation adversarial vectors passed");
