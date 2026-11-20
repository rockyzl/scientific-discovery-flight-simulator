"use strict";

const state = { scenario: null, campaign: null, events: [], busy: false };
const $ = (id) => document.getElementById(id);

function deriveContinuation(campaign) {
  if (!campaign || typeof campaign !== "object" || typeof campaign.campaign_id !== "string" || !campaign.campaign_id || !Number.isInteger(campaign.revision)) return null;
  if (campaign.phase === "approved") {
    const approved = campaign.approved_decision;
    if (!approved || typeof approved.decision_id !== "string" || !approved.decision_id) return null;
    return { campaignId: campaign.campaign_id, decisionId: approved.decision_id, expectedRevision: campaign.revision, kind: "run_approved_simulation" };
  }
  if (campaign.phase === "awaiting_recommendation") {
    const decisions = Array.isArray(campaign.decisions) ? campaign.decisions : [];
    const latest = decisions[decisions.length - 1];
    if (!latest || latest.decision !== "reject" || typeof latest.decision_id !== "string" || !latest.decision_id) return null;
    return { campaignId: campaign.campaign_id, decisionId: latest.decision_id, expectedRevision: campaign.revision, kind: "continue_without_execution" };
  }
  return null;
}

function text(value) { return value == null ? "Not available" : String(value); }
function label(value) { return text(value).replace(/_/g, " "); }
function number(value, digits = 3) { return typeof value === "number" ? value.toFixed(digits).replace(/\.0+$/, "") : text(value); }
function setStatus(message, type = "") { const node = $("status"); node.textContent = message; node.className = `status ${type}`; }
function safeError(error) {
  if (error && typeof error === "object" && error.message) return error.message;
  return "The request could not be completed. Check the campaign ID and try again.";
}
async function request(url, options) {
  let response;
  try { response = await fetch(url, { cache: "no-store", ...options, headers: { "Content-Type": "application/json", ...(options && options.headers) } }); }
  catch { throw new Error("The local simulator could not be reached."); }
  let body = null;
  try { body = await response.json(); } catch { throw new Error("The simulator returned an unreadable response."); }
  if (!response.ok) throw new Error(body && body.error && body.error.message ? body.error.message : "The simulator could not complete that request.");
  return body;
}
function campaignId() { return $("campaign-id").value.trim(); }
function decisionId(campaign, decision) { return `rfb-ui:${campaign.campaign_id}:r${campaign.revision}:${decision}`; }
function create(tag, value, className) { const node = document.createElement(tag); if (className) node.className = className; if (value != null) node.textContent = value; return node; }
function setBusy(busy) { state.busy = busy; document.querySelectorAll("button, input, select").forEach((node) => { if (node.id !== "reason-code") node.disabled = busy || node.disabled && false; }); render(); }
function facts(items, target) { target.replaceChildren(); items.forEach(([key, value]) => { const item = document.createElement("div"); item.append(create("dt", key)); item.append(create("dd", value)); target.append(item); }); }
function renderRecommendation() {
  const target = $("recommendation"), recommendation = state.campaign && state.campaign.pending_recommendation;
  target.replaceChildren();
  if (!recommendation) { target.append(create("p", state.campaign ? "There is no recommendation waiting for review." : "Start or load a campaign to inspect its current recommendation.")); return; }
  const action = recommendation.action || {};
  const grid = document.createElement("dl"); grid.className = "facts protocol";
  [["Charge current", `${number(action.charge_current_A)} A`], ["Discharge current", `${number(action.discharge_current_A)} A`], ["Charge voltage limit", `${number(action.charge_voltage_limit_V)} V`], ["Discharge voltage limit", `${number(action.discharge_voltage_limit_V)} V`], ["Protocol duration", `${number(action.protocol_duration_s, 0)} s`], ["Predicted utility", recommendation.predicted_utility_mean == null ? "Not provided" : `${number(recommendation.predicted_utility_mean)} +/- ${number(recommendation.predicted_utility_std)}`], ["Remaining budget", `${recommendation.remaining_attempt_budget} attempts; ${recommendation.remaining_measurement_budget} measurements`]].forEach(([key, value]) => { const item = document.createElement("div"); item.append(create("dt", key)); item.append(create("dd", value)); grid.append(item); });
  target.append(grid); target.append(create("h3", "Rationale")); target.append(create("p", recommendation.rationale || "No rationale was provided."));
}
function renderOutcomes() {
  const target = $("outcomes"), executions = state.campaign ? state.campaign.executions || [] : [];
  target.replaceChildren();
  if (!executions.length) { target.append(create("p", "No completed simulation outcome is available.")); return; }
  executions.slice().reverse().forEach((execution, index) => { const article = document.createElement("article"); article.className = "outcome"; const outcome = execution.outcome || {}, utility = execution.utility_record || {}; article.append(create("h3", `Simulation ${executions.length - index}: ${label(outcome.status)}`)); const grid = document.createElement("dl"); grid.className = "facts"; [["Delivered discharge energy", `${number(outcome.delivered_discharge_energy_J)} J`], ["Round-trip efficiency", number(outcome.round_trip_efficiency)], ["Capacity retention", number(outcome.capacity_retention)], ["Elapsed duration", `${number(outcome.elapsed_duration_s)} s`], ["Utility", number(utility.utility)], ["QC flags", (outcome.qc_flags || []).join(", ") || "None"]].forEach(([key, value]) => { const item = document.createElement("div"); item.append(create("dt", key)); item.append(create("dd", value)); grid.append(item); }); article.append(grid); target.append(article); });
}
function eventSummary(event) { const payload = event.payload || {}; if (payload.recommendation) return "Recommendation saved for review."; if (payload.approval) return "Approval recorded. No simulation was run by recording this decision."; if (payload.intervention) return "Rejection recorded. No simulation was run by recording this decision."; if (payload.execution) return event.event_type === "execution_completed" ? "Simulation completed." : "Approved simulation started."; if (event.event_type === "campaign_created") return "Campaign created."; return "Public campaign event recorded."; }
function renderEvents() { const target = $("events"); target.replaceChildren(); if (!state.events.length) { target.append(create("li", "No campaign events loaded.")); return; } state.events.slice(-12).reverse().forEach((event) => { const item = document.createElement("li"); item.append(create("strong", `${event.sequence + 1}. ${label(event.event_type)}`)); item.append(create("span", eventSummary(event))); target.append(item); }); }
function render() {
  const campaign = state.campaign, reviewing = campaign && campaign.phase === "awaiting_review" && campaign.pending_recommendation;
  $("phase").textContent = campaign ? label(campaign.phase) : "No campaign loaded";
  $("recommendation-state").textContent = reviewing ? "Ready for review" : campaign ? "No review pending" : "Awaiting a campaign";
  facts(campaign ? [["Campaign", campaign.campaign_id], ["Scenario", campaign.public_scenario && campaign.public_scenario.scenario_id], ["Policy", label(campaign.policy_id)], ["Revision", campaign.revision], ["Budget used", `${campaign.cumulative_costs.attempts} attempts; ${campaign.cumulative_costs.measurements} measurements`], ["Budget remaining", `${campaign.public_scenario.total_attempt_budget - campaign.cumulative_costs.attempts - campaign.reserved_costs.attempts} attempts; ${campaign.public_scenario.total_measurement_budget - campaign.cumulative_costs.measurements - campaign.reserved_costs.measurements} measurements`]] : [], $("campaign-facts"));
  $("review-controls").disabled = !reviewing || state.busy; $("record-button").disabled = !reviewing || state.busy; $("refresh-button").disabled = !campaign || state.busy;
  $("start-button").disabled = state.busy || !state.scenario; $("load-button").disabled = state.busy;
  const continuation = $("continuation"), resume = deriveContinuation(campaign);
  continuation.hidden = !resume; if (resume) { const approved = resume.kind === "run_approved_simulation"; $("continuation-text").textContent = approved ? "Approval is recorded only. Run the approved simulation as a separate command." : "Rejection is recorded only. Continue to request the next recommendation without execution."; $("resume-button").textContent = approved ? "Run approved simulation" : "Continue without execution"; $("resume-button").disabled = state.busy; }
  renderRecommendation(); renderOutcomes(); renderEvents();
}
async function loadEvents(id) { const data = await request(`/api/rfb/campaigns/${encodeURIComponent(id)}/events`); state.events = Array.isArray(data.events) ? data.events : []; }
async function applyCampaign(response) { state.campaign = response.campaign; await loadEvents(state.campaign.campaign_id); render(); }
async function startCampaign(event) { event.preventDefault(); const id = campaignId(); if (!id || !state.scenario) { setStatus("Enter a campaign ID after the public scenario has loaded.", "error"); return; } state.busy = true; render(); try { await applyCampaign(await request("/api/rfb/campaigns", { method: "POST", body: JSON.stringify({ campaign_id: id, scenario_id: state.scenario.scenario_id, policy_id: $("policy-id").value }) })); setStatus("Campaign started. Review the current recommendation.", "success"); } catch (error) { setStatus(safeError(error), "error"); } finally { state.busy = false; render(); } }
async function loadCampaign() { const id = campaignId(); if (!id) { setStatus("Enter a campaign ID to load a campaign.", "error"); return; } state.busy = true; render(); try { await applyCampaign(await request(`/api/rfb/campaigns/${encodeURIComponent(id)}`)); setStatus("Campaign loaded.", "success"); } catch (error) { state.campaign = null; state.events = []; setStatus(safeError(error), "error"); } finally { state.busy = false; render(); } }
function updateReason() { const reject = document.querySelector('input[name="decision"]:checked').value === "reject"; $("reason-field").hidden = !reject; $("reason-code").disabled = !reject; $("reason-code").required = reject; }
async function recordDecision(event) { event.preventDefault(); const campaign = state.campaign, decision = document.querySelector('input[name="decision"]:checked').value, reason = $("reason-code").value; if (!campaign || campaign.phase !== "awaiting_review") return; if (decision === "reject" && !reason) { setStatus("Choose a reason code before recording a rejection.", "error"); return; } const id = decisionId(campaign, decision), payload = { decision_id: id, expected_revision: campaign.revision, decision }; if (decision === "reject") payload.reason_code = reason; state.busy = true; render(); try { await applyCampaign(await request(`/api/rfb/campaigns/${encodeURIComponent(campaign.campaign_id)}/approvals`, { method: "POST", body: JSON.stringify(payload) })); setStatus(`${label(decision)} decision recorded.`, "success"); } catch (error) { setStatus(safeError(error), "error"); } finally { state.busy = false; render(); } }
async function resumeCampaign() { const resume = deriveContinuation(state.campaign); if (!resume) return; state.busy = true; render(); try { await applyCampaign(await request(`/api/rfb/campaigns/${encodeURIComponent(resume.campaignId)}/resume`, { method: "POST", body: JSON.stringify({ decision_id: resume.decisionId, expected_revision: resume.expectedRevision }) })); setStatus(resume.kind === "run_approved_simulation" ? "Simulation completed. Review the next recommendation if one is available." : "Continuation completed without execution.", "success"); } catch (error) { setStatus(safeError(error), "error"); } finally { state.busy = false; render(); } }
async function initialize() { try { state.scenario = (await request("/api/rfb/scenario")).scenario; setStatus("Public scenario loaded. Start a campaign or load an existing one.", "success"); } catch (error) { setStatus(safeError(error), "error"); } render(); }
if (typeof module !== "undefined" && module.exports) module.exports = { deriveContinuation };
if (typeof document !== "undefined") { $("campaign-form").addEventListener("submit", startCampaign); $("load-button").addEventListener("click", loadCampaign); $("review-form").addEventListener("submit", recordDecision); $("resume-button").addEventListener("click", resumeCampaign); $("refresh-button").addEventListener("click", loadCampaign); document.querySelectorAll('input[name="decision"]').forEach((node) => node.addEventListener("change", updateReason)); updateReason(); initialize(); }
