"use strict";

const PLANNERS = ["random", "fixed_grid", "information_gain"];
const ARTIFACTS = {
  manifest: "/artifacts/manifest.json",
  summary: "/artifacts/summary.json",
  random: "/artifacts/ledgers/random.json",
  fixed_grid: "/artifacts/ledgers/fixed_grid.json",
  information_gain: "/artifacts/ledgers/information_gain.json",
};

const state = {
  manifest: null,
  summary: null,
  ledgers: {},
  selectedPlanner: PLANNERS[0],
  complete: false,
  reveal: null,
};

const byId = (id) => document.getElementById(id);

function appendText(parent, tag, value, className) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = value == null ? "—" : String(value);
  parent.appendChild(element);
  return element;
}

function humanize(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function compact(value) {
  if (value == null) return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") {
    // String(number) is JavaScript's shortest round-trip representation. In particular, it leaves
    // exponent digits untouched; trimming trailing zeroes from an exponential string can change
    // 1e-10 into 1e-1.
    return Object.is(value, -0) ? "0" : String(value);
  }
  if (Array.isArray(value)) return value.map(compact).join(", ") || "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function flattenScalars(value, prefix = "", output = {}) {
  if (value == null || ["string", "number", "boolean"].includes(typeof value)) {
    if (prefix) output[prefix] = value;
    return output;
  }
  if (Array.isArray(value)) {
    if (value.every((item) => item == null || typeof item !== "object")) output[prefix] = value;
    return output;
  }
  Object.entries(value).forEach(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    flattenScalars(child, path, output);
  });
  return output;
}

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}`);
  return response.json();
}

function assertSimulated(name, artifact) {
  if (!artifact || artifact.provenance !== "simulated") {
    throw new Error(`${name} is missing provenance: simulated`);
  }
}

function resultFor(planner) {
  return state.summary?.results?.[planner] || {};
}

function eventsFor(planner) {
  const events = state.ledgers[planner]?.events;
  return Array.isArray(events) ? events : [];
}

function finalEvent(planner) {
  const events = eventsFor(planner);
  return events.length ? events[events.length - 1] : null;
}

function ledgerCompletion(planner) {
  const ledger = state.ledgers[planner];
  const last = finalEvent(planner);
  if (!ledger || !last) return { complete: false, reason: "No events" };
  if (last.stop != null) {
    const reason = last.stop.reason || last.stop.rationale || "Planner stopped";
    return { complete: true, reason: `Stopped: ${reason}` };
  }
  const world = ledger.world || {};
  const costs = last.costs || {};
  const attemptsExhausted = Number(costs.cumulative_attempt) >= Number(world.total_attempt_budget);
  const measurementsExhausted =
    Number(costs.cumulative_measurement) >= Number(world.total_measurement_budget);
  if (attemptsExhausted || measurementsExhausted) {
    return { complete: true, reason: "Budget exhausted" };
  }
  return { complete: false, reason: "Campaign artifact is incomplete" };
}

function extractReveal() {
  // This is the only reveal source. Never infer or read hidden truth from a ledger or manifest.
  const reveal = state.summary?.post_run_reveal;
  if (!reveal || reveal.available !== true || reveal.provenance !== "simulated") return null;
  return {
    kind: reveal.kind,
    label: reveal.label,
    value: reveal.value,
    provenance: reveal.provenance,
    replay_key: reveal.replay_key,
    private_seeds: reveal.private_seeds,
    planner_seed: reveal.planner_seed,
  };
}

function renderIdentity() {
  const manifest = state.manifest;
  const seeds = manifest.seeds || {};
  const scenarioIdentity = manifest.scenario_identity || {};
  const identity = byId("identity-grid");
  identity.replaceChildren();
  const fields = [
    ["World", `${manifest.world_id || "—"} · ${manifest.world_version || "—"}`],
    ["Scenario commitment", scenarioIdentity.scenario_sha256 || "not published"],
    ["Package", `${manifest.package?.name || "—"} · ${manifest.package?.version || "—"}`],
    ["Schema", manifest.schema_version || "—"],
    ["Planner seed", seeds.planner_seed ?? seeds.planner ?? "—"],
    ["World-seed commitment", seeds.commitments?.world_seed || "not published"],
    ["Noise-seed commitment", seeds.commitments?.noise_seed || "not published"],
    ["Failure-seed commitment", seeds.commitments?.failure_seed || "not published"],
    ["Runtime", `${manifest.runtime?.python || "—"} · NumPy ${manifest.runtime?.numpy || "—"}`],
    ["Manifest hash", manifest.manifest_payload_sha256 || "—"],
  ];
  fields.forEach(([label, value]) => {
    const wrapper = document.createElement("div");
    appendText(wrapper, "dt", label);
    appendText(wrapper, "dd", compact(value));
    identity.appendChild(wrapper);
  });

  const status = byId("run-state");
  status.textContent = state.complete ? "COMPLETE" : "INCOMPLETE";
  status.dataset.state = state.complete ? "complete" : "warning";
}

function plannerDescription(planner) {
  const descriptions = {
    random: "Samples a valid action using an isolated planner random stream.",
    fixed_grid: "Follows a predetermined log-spaced experimental design.",
    information_gain: "Chooses the action with greatest expected uncertainty reduction.",
  };
  return descriptions[planner] || "Recorded experiment-selection policy.";
}

function renderComparison() {
  const cards = byId("planner-cards");
  cards.replaceChildren();
  PLANNERS.forEach((planner) => {
    const card = document.createElement("article");
    card.className = "planner-card";
    appendText(card, "h3", humanize(planner));
    appendText(card, "p", plannerDescription(planner));
    const completion = ledgerCompletion(planner);
    const status = appendText(card, "span", completion.complete ? "COMPLETE" : "INCOMPLETE", "status-pill");
    status.dataset.state = completion.complete ? "complete" : "warning";
    appendText(card, "p", completion.reason);
    cards.appendChild(card);
  });

  const metricMaps = Object.fromEntries(
    PLANNERS.map((planner) => [planner, flattenScalars(resultFor(planner).metrics || {})]),
  );
  const metricKeys = [...new Set(PLANNERS.flatMap((planner) => Object.keys(metricMaps[planner])))]
    .sort();

  const head = byId("comparison-head");
  const headRow = document.createElement("tr");
  appendText(headRow, "th", "Metric").scope = "col";
  PLANNERS.forEach((planner) => {
    const cell = appendText(headRow, "th", humanize(planner));
    cell.scope = "col";
  });
  head.replaceChildren(headRow);

  const body = byId("comparison-body");
  body.replaceChildren();
  if (!metricKeys.length) {
    const row = document.createElement("tr");
    const cell = appendText(row, "td", "No scalar metrics were published in summary.json.");
    cell.colSpan = PLANNERS.length + 1;
    body.appendChild(row);
    return;
  }
  metricKeys.forEach((key) => {
    const row = document.createElement("tr");
    const label = appendText(row, "th", humanize(key.replace(/\./g, " — ")));
    label.scope = "row";
    PLANNERS.forEach((planner) => appendText(row, "td", compact(metricMaps[planner][key])));
    body.appendChild(row);
  });
}

function eventStatus(event) {
  if (event.stop != null) return { text: "STOPPED", className: "success" };
  const validation = event.validation || {};
  const accepted = validation.accepted ?? validation.valid ?? validation.is_valid;
  if (accepted === false) return { text: "BLOCKED", className: "blocked" };
  const observation = event.observation || {};
  const status = String(observation.status || "").toLowerCase();
  if (["failed", "failure", "error"].includes(status)) {
    return { text: "MEASUREMENT FAILED", className: "failure" };
  }
  if (event.observation != null) return { text: "MEASUREMENT SUCCEEDED", className: "success" };
  if (event.request != null) return { text: accepted === true ? "ACCEPTED" : "PROPOSED", className: "" };
  return { text: "RECORDED", className: "" };
}

function reasonFor(event) {
  return event.stop?.reason || event.stop?.rationale || event.request?.reason ||
    event.request?.rationale || event.validation?.reason || event.validation?.message || "—";
}

function requestFor(event) {
  const request = event.request;
  if (!request) return "—";
  return compact(request.controls || request.requested_controls || request);
}

function observationFor(event) {
  const observation = event.observation;
  if (!observation) return "—";
  if (observation.value != null) {
    const unit = observation.unit || observation.units || "";
    return `${compact(observation.value)}${unit ? ` ${unit}` : ""}`;
  }
  return compact(observation.status || observation.qc_flags || observation);
}

function addEventField(grid, label, value) {
  const field = document.createElement("div");
  field.className = "event-field";
  appendText(field, "b", label);
  appendText(field, "span", compact(value));
  grid.appendChild(field);
}

function renderReplay(planner) {
  state.selectedPlanner = planner;
  document.querySelectorAll(".tab-button").forEach((button) => {
    const selected = button.dataset.planner === planner;
    button.setAttribute("aria-selected", selected ? "true" : "false");
    button.tabIndex = selected ? 0 : -1;
  });
  const panel = byId("replay-panel");
  panel.setAttribute("aria-labelledby", `replay-tab-${planner}`);

  const ledger = state.ledgers[planner];
  const events = eventsFor(planner);
  const completion = ledgerCompletion(planner);
  const last = finalEvent(planner);
  const summary = byId("replay-summary");
  summary.replaceChildren();
  [
    `Planner: ${ledger.planner?.name || planner} ${ledger.planner?.version || ""}`,
    `Events: ${events.length}`,
    `Attempts: ${last?.costs?.cumulative_attempt ?? 0}/${ledger.world?.total_attempt_budget ?? "—"}`,
    `Measurements: ${last?.costs?.cumulative_measurement ?? 0}/${ledger.world?.total_measurement_budget ?? "—"}`,
    `Outcome: ${completion.reason}`,
  ].forEach((value) => appendText(summary, "span", value));

  const list = byId("event-list");
  list.replaceChildren();
  events.forEach((event, index) => {
    const item = document.createElement("li");
    item.className = "event";
    const card = document.createElement("article");
    card.className = "event-card";
    const top = document.createElement("div");
    top.className = "event-top";
    appendText(top, "h3", `Event ${event.sequence ?? index + 1}`);
    const statusData = eventStatus(event);
    appendText(top, "span", statusData.text, `event-status ${statusData.className}`);
    card.appendChild(top);

    const grid = document.createElement("div");
    grid.className = "event-grid";
    addEventField(grid, "Request", requestFor(event));
    addEventField(grid, "Reason", reasonFor(event));
    addEventField(grid, "Observation", observationFor(event));
    addEventField(grid, "Attempt cost", event.costs?.attempt ?? 0);
    addEventField(grid, "Measurement cost", event.costs?.measurement ?? 0);
    addEventField(grid, "Remaining budget", {
      attempts: Number(ledger.world?.total_attempt_budget ?? 0) - Number(event.costs?.cumulative_attempt ?? 0),
      measurements: Number(ledger.world?.total_measurement_budget ?? 0) - Number(event.costs?.cumulative_measurement ?? 0),
    });
    card.appendChild(grid);

    const details = document.createElement("details");
    appendText(details, "summary", "Show beliefs, validation, QC, and hashes");
    appendText(details, "pre", JSON.stringify(event, null, 2));
    card.appendChild(details);
    item.appendChild(card);
    list.appendChild(item);
  });
}

function renderReplayTabs() {
  const tabs = byId("replay-tabs");
  tabs.replaceChildren();
  PLANNERS.forEach((planner, index) => {
    const button = appendText(tabs, "button", humanize(planner), "tab-button");
    button.type = "button";
    button.id = `replay-tab-${planner}`;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-controls", "replay-panel");
    button.dataset.planner = planner;
    button.setAttribute("aria-selected", index === 0 ? "true" : "false");
    button.tabIndex = index === 0 ? 0 : -1;
    button.addEventListener("click", () => renderReplay(planner));
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      let next = PLANNERS.indexOf(planner);
      if (event.key === "ArrowRight") next = (next + 1) % PLANNERS.length;
      if (event.key === "ArrowLeft") next = (next - 1 + PLANNERS.length) % PLANNERS.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = PLANNERS.length - 1;
      const nextPlanner = PLANNERS[next];
      renderReplay(nextPlanner);
      document.querySelector(`[data-planner="${nextPlanner}"]`).focus();
    });
  });
  renderReplay(state.selectedPlanner);
}

function configureReveal() {
  const button = byId("reveal-button");
  const explanation = byId("reveal-explanation");
  if (!state.complete) {
    button.disabled = true;
    explanation.textContent = "Hidden truth cannot be revealed because one or more campaign artifacts are incomplete.";
    return;
  }
  if (state.reveal == null) {
    button.disabled = true;
    explanation.textContent = "All campaigns are complete, but this artifact schema did not publish benchmark truth.";
    return;
  }
  button.disabled = false;
  explanation.textContent = "All completed artifacts loaded. Reveal the synthetic answer used for post-run evaluation.";
  button.addEventListener("click", () => {
    const panel = byId("truth-panel");
    panel.hidden = false;
    byId("truth-value").textContent = JSON.stringify(state.reveal, null, 2);
    byId("replay-identity").textContent = JSON.stringify({
      scenario_commitment: state.manifest.scenario_identity?.scenario_sha256 || null,
      replay_key: state.reveal.replay_key,
      private_seeds: state.reveal.private_seeds,
      planner_seed: state.reveal.planner_seed,
    }, null, 2);
    button.disabled = true;
    button.textContent = "Benchmark truth revealed below";
    panel.focus();
  }, { once: true });
}

async function loadArtifacts() {
  const status = byId("load-status");
  try {
    const [manifest, summary, ...ledgers] = await Promise.all([
      fetchJson(ARTIFACTS.manifest),
      fetchJson(ARTIFACTS.summary),
      ...PLANNERS.map((planner) => fetchJson(ARTIFACTS[planner])),
    ]);
    assertSimulated("manifest.json", manifest);
    assertSimulated("summary.json", summary);
    ledgers.forEach((ledger, index) => assertSimulated(`${PLANNERS[index]} ledger`, ledger));
    state.manifest = manifest;
    state.summary = summary;
    state.ledgers = Object.fromEntries(PLANNERS.map((planner, index) => [planner, ledgers[index]]));
    state.complete = PLANNERS.every((planner) => ledgerCompletion(planner).complete);
    state.reveal = extractReveal();
    renderIdentity();
    renderComparison();
    renderReplayTabs();
    configureReveal();
    status.textContent = state.complete
      ? "Completed simulated artifacts loaded. This page is a deterministic replay."
      : "Artifacts loaded, but at least one campaign is incomplete.";
  } catch (error) {
    status.classList.add("error");
    status.textContent = `Artifacts could not be loaded: ${error.message}`;
    const runState = byId("run-state");
    runState.textContent = "LOAD ERROR";
    runState.dataset.state = "error";
    byId("reveal-button").disabled = true;
  }
}

document.addEventListener("DOMContentLoaded", loadArtifacts);
