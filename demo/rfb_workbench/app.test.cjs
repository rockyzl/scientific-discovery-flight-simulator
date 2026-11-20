"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { deriveContinuation } = require("./app.js");

test("approved public state restores a run command at the current revision", () => {
  assert.deepEqual(deriveContinuation({
    campaign_id: "persisted-approved",
    revision: 7,
    phase: "approved",
    approved_decision: { decision_id: "approval-7", decision: "approve" },
  }), {
    campaignId: "persisted-approved",
    decisionId: "approval-7",
    expectedRevision: 7,
    kind: "run_approved_simulation",
  });
});

test("rejected public state restores a continuation without execution", () => {
  assert.deepEqual(deriveContinuation({
    campaign_id: "persisted-rejection",
    revision: 4,
    phase: "awaiting_recommendation",
    decisions: [
      { decision_id: "older", decision: "approve" },
      { decision_id: "rejection-4", decision: "reject" },
    ],
  }), {
    campaignId: "persisted-rejection",
    decisionId: "rejection-4",
    expectedRevision: 4,
    kind: "continue_without_execution",
  });
});

test("unrelated or incomplete public state has no continuation", () => {
  for (const campaign of [
    null,
    { campaign_id: "review", revision: 2, phase: "awaiting_review", decisions: [{ decision_id: "edit", decision: "approve_with_edit" }] },
    { campaign_id: "not-rejected", revision: 3, phase: "awaiting_recommendation", decisions: [{ decision_id: "approve", decision: "approve" }] },
    { campaign_id: "missing-approval", revision: 3, phase: "approved", approved_decision: null },
  ]) assert.equal(deriveContinuation(campaign), null);
});
