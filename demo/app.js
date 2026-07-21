"use strict";

const PLANNERS = ["random", "fixed_grid", "information_gain"];
const ARTIFACTS = {
  realCV: "/real-cv-data.json",
  manifest: "/artifacts/manifest.json",
  summary: "/artifacts/summary.json",
  random: "/artifacts/ledgers/random.json",
  fixed_grid: "/artifacts/ledgers/fixed_grid.json",
  information_gain: "/artifacts/ledgers/information_gain.json",
};

const state = {
  realCV: null,
  realSampleId: null,
  previousRealSampleId: null,
  labStep: 0,
  labTimer: null,
  manifest: null,
  summary: null,
  ledgers: {},
  selectedPlanner: PLANNERS[0],
  complete: false,
  reveal: null,
  strategyStep: 0,
  strategyTimer: null,
};

const SVG_NS = "http://www.w3.org/2000/svg";

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

function svgElement(tag, attributes = {}) {
  const element = document.createElementNS(SVG_NS, tag);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
  return element;
}

function linearScale(domainMin, domainMax, rangeMin, rangeMax) {
  return (value) => rangeMin + ((value - domainMin) / (domainMax - domainMin)) * (rangeMax - rangeMin);
}

function logScale(domainMin, domainMax, rangeMin, rangeMax) {
  const low = Math.log(domainMin);
  const high = Math.log(domainMax);
  return (value) => rangeMin + ((Math.log(value) - low) / (high - low)) * (rangeMax - rangeMin);
}

function drawChartFrame(svg, options) {
  const width = 760;
  const height = Number(svg.getAttribute("viewBox")?.split(" ")[3] || 430);
  const frame = { left: 72, right: width - 24, top: 24, bottom: height - 58 };
  const x = options.xScale(options.xMin, options.xMax, frame.left, frame.right);
  const y = linearScale(options.yMin, options.yMax, frame.bottom, frame.top);
  const grid = svgElement("g", { class: "chart-grid" });
  options.xTicks.forEach((tick) => {
    const position = x(tick);
    grid.appendChild(svgElement("line", { x1: position, x2: position, y1: frame.top, y2: frame.bottom }));
    const label = svgElement("text", { x: position, y: frame.bottom + 24, "text-anchor": "middle" });
    label.textContent = options.xFormat(tick);
    grid.appendChild(label);
  });
  options.yTicks.forEach((tick) => {
    const position = y(tick);
    grid.appendChild(svgElement("line", { x1: frame.left, x2: frame.right, y1: position, y2: position }));
    const label = svgElement("text", { x: frame.left - 12, y: position + 4, "text-anchor": "end" });
    label.textContent = options.yFormat(tick);
    grid.appendChild(label);
  });
  svg.appendChild(grid);
  svg.appendChild(svgElement("line", { class: "chart-axis", x1: frame.left, x2: frame.right, y1: frame.bottom, y2: frame.bottom }));
  svg.appendChild(svgElement("line", { class: "chart-axis", x1: frame.left, x2: frame.left, y1: frame.top, y2: frame.bottom }));
  const xLabel = svgElement("text", { class: "axis-label", x: (frame.left + frame.right) / 2, y: height - 12, "text-anchor": "middle" });
  xLabel.textContent = options.xLabel;
  svg.appendChild(xLabel);
  const yLabel = svgElement("text", { class: "axis-label", x: 18, y: (frame.top + frame.bottom) / 2, transform: `rotate(-90 18 ${(frame.top + frame.bottom) / 2})`, "text-anchor": "middle" });
  yLabel.textContent = options.yLabel;
  svg.appendChild(yLabel);
  return { ...frame, x, y };
}

const LAB_STEPS = [
  ["Choose formulation", "Select the named electrolyte formulation whose published CV will be displayed."],
  ["Remove previous sample", "If a different formulation was in the cell, stop the run and remove it before loading the next sample."],
  ["Rinse and prepare", "Rinse the cell and prepare the electrodes so residue from the prior formulation is not treated as the new sample."],
  ["Load and identify sample", "Load the selected anolyte and bind its composition, pH, source record, and protocol to this run."],
  ["Equilibrate and check", "Assemble the three-electrode cell, allow it to stabilize, and check the potential window and reference."],
  ["Run cyclic voltammetry", "Sweep from 0 V toward −1.2 V and back at 10 mV/s while recording current density."],
  ["Retain the analysis curve", "Complete the recorded cycles and display the authors’ processed second-cycle curve."],
];

function selectedRealSample() {
  return state.realCV?.samples?.find((sample) => sample.id === state.realSampleId) || null;
}

function renderRealCurve(progress = 1) {
  const svg = byId("real-cv-chart");
  const sample = selectedRealSample();
  svg.replaceChildren();
  if (!sample) return;
  const points = sample.points;
  const currents = points.map((point) => point[1]);
  const yAbs = Math.max(5, ...currents.map(Math.abs));
  const yLimit = Math.ceil(yAbs / 10) * 10;
  const frame = drawChartFrame(svg, {
    xMin: -1.2, xMax: 0, yMin: -yLimit, yMax: yLimit,
    xScale: linearScale,
    xTicks: [-1.2, -0.9, -0.6, -0.3, 0],
    yTicks: [-yLimit, -yLimit / 2, 0, yLimit / 2, yLimit],
    xFormat: (value) => value.toFixed(1), yFormat: (value) => String(value),
    xLabel: "Working-electrode potential vs Ag/AgCl/KCl (sat’d) / V",
    yLabel: "Total current density / mA cm⁻²",
  });
  const count = Math.max(2, Math.ceil(points.length * Math.max(0, Math.min(1, progress))));
  const visible = points.slice(0, count);
  const pathData = visible.map((point, index) => `${index ? "L" : "M"}${frame.x(point[0]).toFixed(2)},${frame.y(point[1]).toFixed(2)}`).join(" ");
  svg.appendChild(svgElement("path", { d: pathData, class: "real-cv-line", stroke: sample.color }));
  const cursor = visible[visible.length - 1];
  svg.appendChild(svgElement("circle", { class: "chart-cursor", cx: frame.x(cursor[0]), cy: frame.y(cursor[1]), r: 5, fill: sample.color }));
}

function labNarration(stepIndex) {
  const sample = selectedRealSample();
  if (!sample) return "No sample selected.";
  if (stepIndex === 1 && state.previousRealSampleId == null) {
    return `Fresh-cell start: there is no previous sample to remove. Next, prepare the cell for ${sample.composition}.`;
  }
  const [title, detail] = LAB_STEPS[stepIndex];
  return `${title}: ${detail}`;
}

function renderLabStep() {
  const steps = byId("lab-workflow").querySelectorAll("li");
  steps.forEach((item, index) => {
    item.dataset.state = index < state.labStep ? "done" : index === state.labStep ? "active" : "pending";
  });
  byId("lab-narration").textContent = labNarration(state.labStep);
  renderRealCurve(state.labStep < LAB_STEPS.length - 1 ? 0.015 : 1);
  byId("lab-next").disabled = state.labStep >= LAB_STEPS.length - 1;
  if (state.labStep >= LAB_STEPS.length - 1) {
    state.previousRealSampleId = state.realSampleId;
    window.clearInterval(state.labTimer);
    state.labTimer = null;
    byId("lab-play").textContent = "Run again";
  }
}

function resetLabWorkflow({ showCurve = true } = {}) {
  window.clearInterval(state.labTimer);
  state.labTimer = null;
  state.labStep = 0;
  byId("lab-play").textContent = "Run experiment step by step";
  renderLabStep();
  if (showCurve) renderRealCurve(1);
}

function advanceLabStep() {
  if (state.labStep < LAB_STEPS.length - 1) state.labStep += 1;
  renderLabStep();
}

function selectRealSample(sampleId) {
  if (state.realSampleId && state.realSampleId !== sampleId) {
    state.previousRealSampleId = state.realSampleId;
  }
  state.realSampleId = sampleId;
  document.querySelectorAll(".sample-tab").forEach((button) => {
    const selected = button.dataset.sample === sampleId;
    button.setAttribute("aria-pressed", selected ? "true" : "false");
  });
  const sample = selectedRealSample();
  byId("real-sample-name").textContent = sample.name;
  byId("real-sample-composition").textContent = `${sample.composition} · pH ${sample.ph}`;
  byId("real-protocol").textContent = `${sample.protocol.scan_rate_mV_s} mV/s · ${sample.protocol.cycles_recorded} recorded cycles · cycle ${sample.protocol.analysis_cycle} shown`;
  const measurement = state.realCV.measurement;
  const record = byId("sample-record");
  record.replaceChildren();
  [
    ["Formulation", sample.composition], ["pH", sample.ph],
    ["Working electrode", measurement.working_electrode],
    ["Reference electrode", measurement.reference_electrode],
    ["Counter electrode", measurement.counter_electrode],
    ["Data", `${sample.point_count} published processed points`],
  ].forEach(([label, value]) => {
    appendText(record, "dt", label);
    appendText(record, "dd", value);
  });
  resetLabWorkflow();
}

function renderRealLab() {
  const tabs = byId("sample-tabs");
  tabs.replaceChildren();
  state.realCV.samples.forEach((sample, index) => {
    const button = appendText(tabs, "button", sample.name, "sample-tab");
    button.type = "button";
    button.dataset.sample = sample.id;
    button.setAttribute("aria-pressed", index === 0 ? "true" : "false");
    button.addEventListener("click", () => selectRealSample(sample.id));
  });
  const workflow = byId("lab-workflow");
  workflow.replaceChildren();
  LAB_STEPS.forEach(([title, detail], index) => {
    const item = document.createElement("li");
    item.dataset.state = index ? "pending" : "active";
    appendText(item, "b", title);
    appendText(item, "span", detail);
    workflow.appendChild(item);
  });
  byId("lab-next").addEventListener("click", advanceLabStep);
  byId("lab-reset").addEventListener("click", () => resetLabWorkflow());
  byId("lab-play").addEventListener("click", () => {
    if (state.labTimer) {
      window.clearInterval(state.labTimer);
      state.labTimer = null;
      byId("lab-play").textContent = "Continue";
      return;
    }
    if (state.labStep >= LAB_STEPS.length - 1) resetLabWorkflow({ showCurve: false });
    byId("lab-play").textContent = "Pause";
    renderLabStep();
    state.labTimer = window.setInterval(advanceLabStep, 1050);
  });
  selectRealSample(state.realCV.samples[0].id);
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
    const metrics = resultFor(planner).metrics || {};
    const resultLine = appendText(
      card,
      "p",
      `${metrics.attempts ?? "—"} attempts → ${humanize(metrics.predicted_mechanism || "unknown")}`,
      "planner-result",
    );
    resultLine.dataset.correct = metrics.mechanism_correct === true ? "true" : "false";
    appendText(
      card,
      "p",
      metrics.mechanism_correct === true
        ? "Correct synthetic mechanism"
        : "Did not identify the hidden mechanism",
      "planner-verdict",
    );
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

function responseFor(mechanism, scanRate) {
  const x = scanRate / 100;
  if (mechanism === "diffusion") return 1.05 * Math.sqrt(x);
  if (mechanism === "surface") return 0.55 * x;
  return 0.58 * Math.sqrt(x) + 0.24 * x;
}

function strategyEventCopy(event, index) {
  if (index === 0) {
    return "No measurement has been revealed. All three mechanisms begin with equal probability.";
  }
  if (event.stop) {
    return `The policy stops and reports ${humanize(event.stop.final_hypothesis)} at ${Math.round((event.stop.confidence || 0) * 100)}% confidence.`;
  }
  if (event.request?.operation === "calibrate") {
    return `The policy first checks the reference response. Result: ${compact(event.observation?.value)}.`;
  }
  const rate = event.request?.controls?.scan_rate_mv_s;
  if (event.observation?.status === "failed") {
    return `It requested ${compact(rate)} mV/s, but the virtual instrument returned ${humanize(event.observation.qc_flags?.[0] || "failure")}. No current value was learned.`;
  }
  return `It requested ${compact(rate)} mV/s and observed normalized current ${compact(event.observation?.value)}. The three mechanism probabilities update below.`;
}

function renderBeliefs(beliefs) {
  const container = byId("belief-bars");
  container.replaceChildren();
  ["diffusion", "surface", "mixed"].forEach((mechanism) => {
    const value = Number(beliefs?.[mechanism] ?? 1 / 3);
    const row = document.createElement("div");
    row.className = "belief-row";
    appendText(row, "span", humanize(mechanism));
    const track = document.createElement("span");
    track.className = "belief-track";
    const fill = document.createElement("i");
    fill.className = `belief-fill ${mechanism}`;
    fill.style.width = `${Math.max(1, value * 100)}%`;
    track.appendChild(fill);
    row.appendChild(track);
    appendText(row, "b", `${(value * 100).toFixed(1)}%`);
    container.appendChild(row);
  });
}

function renderStrategyChart(events, step) {
  const svg = byId("strategy-chart");
  svg.replaceChildren();
  const frame = drawChartFrame(svg, {
    xMin: 5, xMax: 500, yMin: 0, yMax: 2.35,
    xScale: logScale,
    xTicks: [5, 10, 25, 50, 100, 250, 500],
    yTicks: [0, 0.5, 1, 1.5, 2],
    xFormat: (value) => String(value), yFormat: (value) => value.toFixed(1),
    xLabel: "Requested scan rate / mV s⁻¹ (log scale)",
    yLabel: "Normalized current response",
  });
  ["diffusion", "surface", "mixed"].forEach((mechanism) => {
    const points = Array.from({ length: 101 }, (_, index) => 5 * (100 ** (index / 100)));
    const path = points.map((rate, index) => `${index ? "L" : "M"}${frame.x(rate).toFixed(2)},${frame.y(Math.min(2.35, responseFor(mechanism, rate))).toFixed(2)}`).join(" ");
    svg.appendChild(svgElement("path", { d: path, class: `model-line ${mechanism}` }));
  });
  events.slice(0, step).forEach((event) => {
    if (event.request?.operation !== "measure") return;
    const rate = Number(event.request.controls?.scan_rate_mv_s);
    if (!Number.isFinite(rate)) return;
    if (event.observation?.status === "ok" && Number.isFinite(Number(event.observation.value))) {
      svg.appendChild(svgElement("circle", {
        class: "observed-point", cx: frame.x(rate), cy: frame.y(Number(event.observation.value)), r: 6,
      }));
    } else {
      const x = frame.x(rate);
      const y = frame.y(0.12);
      svg.appendChild(svgElement("line", { class: "failed-point", x1: x - 7, x2: x + 7, y1: y - 7, y2: y + 7 }));
      svg.appendChild(svgElement("line", { class: "failed-point", x1: x - 7, x2: x + 7, y1: y + 7, y2: y - 7 }));
    }
  });
  const legend = svgElement("g", { class: "chart-legend" });
  [["diffusion", 84], ["surface", 200], ["mixed", 304]].forEach(([name, x]) => {
    legend.appendChild(svgElement("line", { class: `model-line ${name}`, x1: x, x2: Number(x) + 26, y1: 16, y2: 16 }));
    const label = svgElement("text", { x: Number(x) + 32, y: 20 });
    label.textContent = humanize(name);
    legend.appendChild(label);
  });
  svg.appendChild(legend);
}

function renderStrategyStep() {
  const events = eventsFor(state.selectedPlanner);
  const step = Math.max(0, Math.min(state.strategyStep, events.length));
  const event = step ? events[step - 1] : null;
  byId("strategy-step-title").textContent = event
    ? `Step ${step} of ${events.length}: ${eventStatus(event).text}`
    : `Before step 1 of ${events.length}`;
  byId("strategy-step-copy").textContent = strategyEventCopy(event, step);
  renderBeliefs(event?.beliefs_after || { diffusion: 1 / 3, surface: 1 / 3, mixed: 1 / 3 });
  renderStrategyChart(events, step);
  byId("strategy-prev").disabled = step === 0;
  byId("strategy-next").disabled = step >= events.length;
  if (step >= events.length) {
    window.clearInterval(state.strategyTimer);
    state.strategyTimer = null;
    byId("strategy-play").textContent = "Replay";
  }
}

function configureStrategyPlayer() {
  byId("strategy-prev").addEventListener("click", () => {
    state.strategyStep = Math.max(0, state.strategyStep - 1);
    renderStrategyStep();
  });
  byId("strategy-next").addEventListener("click", () => {
    state.strategyStep += 1;
    renderStrategyStep();
  });
  byId("strategy-play").addEventListener("click", () => {
    if (state.strategyTimer) {
      window.clearInterval(state.strategyTimer);
      state.strategyTimer = null;
      byId("strategy-play").textContent = "Continue";
      return;
    }
    const eventCount = eventsFor(state.selectedPlanner).length;
    if (state.strategyStep >= eventCount) state.strategyStep = 0;
    byId("strategy-play").textContent = "Pause";
    renderStrategyStep();
    state.strategyTimer = window.setInterval(() => {
      state.strategyStep += 1;
      renderStrategyStep();
    }, 1250);
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
  window.clearInterval(state.strategyTimer);
  state.strategyTimer = null;
  state.strategyStep = 0;
  if (byId("strategy-play")) byId("strategy-play").textContent = "Play";
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
  renderStrategyStep();
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
    const [realCV, manifest, summary, ...ledgers] = await Promise.all([
      fetchJson(ARTIFACTS.realCV),
      fetchJson(ARTIFACTS.manifest),
      fetchJson(ARTIFACTS.summary),
      ...PLANNERS.map((planner) => fetchJson(ARTIFACTS[planner])),
    ]);
    if (realCV?.provenance !== "published_processed_experimental_data") {
      throw new Error("real CV reference is missing experimental-data provenance");
    }
    assertSimulated("manifest.json", manifest);
    assertSimulated("summary.json", summary);
    ledgers.forEach((ledger, index) => assertSimulated(`${PLANNERS[index]} ledger`, ledger));
    state.realCV = realCV;
    state.manifest = manifest;
    state.summary = summary;
    state.ledgers = Object.fromEntries(PLANNERS.map((planner, index) => [planner, ledgers[index]]));
    state.complete = PLANNERS.every((planner) => ledgerCompletion(planner).complete);
    state.reveal = extractReveal();
    renderRealLab();
    renderIdentity();
    renderComparison();
    configureStrategyPlayer();
    renderReplayTabs();
    configureReveal();
    status.textContent = state.complete
      ? "Published CV reference and completed simulated artifacts loaded. The two data layers are labeled separately."
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
