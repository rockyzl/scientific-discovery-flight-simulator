"use strict";

const PLANNERS = ["random", "fixed_grid", "information_gain"];
const PLANNER_META = {
  random: { label: "Random", pattern: "scattered", icon: "✦" },
  fixed_grid: { label: "Fixed Grid", pattern: "regular", icon: "▦" },
  information_gain: { label: "Information Gain", pattern: "targeted", icon: "◎" },
};
const ARTIFACTS = {
  realCV: "/real-cv-data.json",
  manifest: "/artifacts/manifest.json",
  summary: "/artifacts/summary.json",
  random: "/artifacts/ledgers/random.json",
  fixed_grid: "/artifacts/ledgers/fixed_grid.json",
  information_gain: "/artifacts/ledgers/information_gain.json",
};
const SVG_NS = "http://www.w3.org/2000/svg";
const DIAGNOSIS_API = "/api/v1/closed-loop";
const DIAGNOSIS_ENVELOPE_FIELDS = [
  "schema_version", "response_id", "response_hash", "request_id", "idempotency_input_hash",
  "scenario_id", "campaign_id", "previous_state_version", "state_version",
  "previous_ledger_hash", "ledger_hash", "status", "payload",
];
const DIAGNOSIS_RECOMMENDATION_FIELDS = [
  "recommendation_id", "state_version", "planner_id", "planner_version", "operation", "controls",
  "reason_code", "reason_text", "attempt_cost", "measurement_cost",
  "expected_information_gain_nats", "action_input_hash",
];
const DIAGNOSIS_HYPOTHESIS_ORDER = [
  "slow_kinetics", "uncompensated_resistance", "reference_drift", "electrode_fouling",
  "concentration_preparation_error",
];
const DIAGNOSIS_STOP_COPY = {
  budget_exhausted: "Stopped · attempt or measurement budget exhausted.",
  confident_diagnosis: "Stopped · confident diagnosis gate satisfied.",
  low_expected_information: "Stopped · expected information is below the threshold.",
};
const DIAGNOSIS_REJECTION_MESSAGES = {
  INVALID_RECOMMENDATION: "Recommendation identity does not match the current campaign state.",
  INVALID_OPERATION: "Operation is not allowed by this scenario.",
  INVALID_CONTROLS: "Controls do not match the operation contract.",
  INELIGIBLE_ACTION: "The requested experiment is not currently eligible.",
  STOP_RULE_NOT_SATISFIED: "No stop rule is satisfied.",
};
const DIAGNOSIS_ERROR_CODES = new Set([
  "MALFORMED_JSON", "INVALID_REQUEST_ENVELOPE", ...Object.keys(DIAGNOSIS_REJECTION_MESSAGES),
  "NOT_FOUND", "STALE_STATE", "TERMINAL_STATE", "IDEMPOTENCY_CONFLICT",
  "REVEAL_NOT_AVAILABLE", "REVEAL_ALREADY_COMPLETED", "INTERNAL_ERROR",
]);
const DIAGNOSIS_SECRET_KEYS = new Set([
  "cause", "world_seed", "noise_seed", "failure_seed", "reveal_nonce", "hidden_truth",
  "seed_bundle", "commitment_payload",
]);
const DIAGNOSIS_ACTIONS = [
  ...[5, 10, 25, 50, 100, 200].map((scan_rate_mv_s) => ({ operation: "repeat_cv", controls: { scan_rate_mv_s } })),
  { operation: "measure_ru", controls: {} },
  { operation: "check_reference", controls: {} },
  { operation: "run_blank", controls: {} },
  { operation: "dilute_and_repeat", controls: { dilution_factor: 0.5, scan_rate_mv_s: 25 } },
  { operation: "clean_and_repeat", controls: { scan_rate_mv_s: 25 } },
  { operation: "run_control_sample", controls: { scan_rate_mv_s: 25 } },
];

const LAB_STEPS = [
  {
    label: "1 · Select formulation",
    detail: "Choose a published formulation. Selection does not run an experiment yet.",
  },
  {
    label: "2 · Check sample change",
    detail: "Compare the selected formulation with the sample currently in the cell.",
  },
  {
    label: "3 · Remove and prepare",
    detail: "Remove previous sample only when switching formulations. Rinse and prepare according to the protocol-defined procedure.",
  },
  {
    label: "4 · Load and identify",
    detail: "Attach the selected formulation, pH, and source record to the physical cell.",
  },
  {
    label: "5 · Assemble and check cell",
    detail: "Check WE, RE, CE, connections, and the protocol-defined ready state.",
  },
  {
    label: "6 · Sweep potential and record current",
    detail: "Sweep WE potential relative to RE while recording current through the WE–CE circuit.",
  },
  {
    label: "7 · Retain the published curve",
    detail: "Show the authors’ processed second-cycle curve and its source metadata.",
  },
];

const BRANCH_COPY = {
  fresh: {
    badge: "EMPTY / FRESH START",
    decision: "No previous sample to remove",
    route: "Fresh cell → load the selected formulation",
  },
  same: {
    badge: "SAME LOADED FORMULATION — CONDITION REPLAY",
    decision: "Same formulation → keep sample loaded",
    route: "Same loaded formulation and cell; physical history may still matter",
  },
  different: {
    badge: "NEW FORMULATION — SAMPLE REPLACEMENT REQUIRED",
    decision: "Different formulation → remove, prepare, and load before measurement",
    route: "Previous sample removed; then load the selected formulation",
  },
};

const state = {
  realCV: null,
  realReady: false,
  selectedSampleId: null,
  loadedSampleId: null,
  workflowStartLoadedId: null,
  displayedSampleId: null,
  labBranch: "fresh",
  labStep: 0,
  labReplayPercent: 0,
  labTimer: null,
  labTick: 0,
  manifest: null,
  summary: null,
  ledgers: {},
  syntheticReady: false,
  selectedPlanner: PLANNERS[0],
  complete: false,
  reveal: null,
  strategyStep: 0,
  strategyTimer: null,
  reducedMotion: false,
  electrodeTrigger: null,
};

const diagnosis = {
  scenario: null,
  campaign: null,
  events: [],
  pending: null,
  epoch: 0,
  busy: false,
  revealed: false,
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
  if (typeof value === "number") return Object.is(value, -0) ? "0" : String(value);
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
    flattenScalars(child, prefix ? `${prefix}.${key}` : key, output);
  });
  return output;
}

function announce(message) {
  const region = byId("cartoon-status-live");
  if (!region) return;
  region.textContent = "";
  window.setTimeout(() => { region.textContent = message; }, 20);
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
  const frame = { left: 72, right: width - 24, top: 28, bottom: height - 58 };
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
  const midpoint = (frame.top + frame.bottom) / 2;
  const yLabel = svgElement("text", { class: "axis-label", x: 18, y: midpoint, transform: `rotate(-90 18 ${midpoint})`, "text-anchor": "middle" });
  yLabel.textContent = options.yLabel;
  svg.appendChild(yLabel);
  return { ...frame, x, y };
}

function clearLabTimer() {
  window.clearInterval(state.labTimer);
  state.labTimer = null;
  state.labTick = 0;
}

function clearStrategyTimer() {
  window.clearInterval(state.strategyTimer);
  state.strategyTimer = null;
}

function pauseAllPlayback(reason = "") {
  const hadLabTimer = state.labTimer != null;
  const hadStrategyTimer = state.strategyTimer != null;
  clearLabTimer();
  clearStrategyTimer();
  if (byId("lab-play")) byId("lab-play").textContent = hadLabTimer ? "Resume" : "Replay published CV workflow";
  if (byId("strategy-play")) byId("strategy-play").textContent = hadStrategyTimer ? "Resume" : "Play all";
  if (reason && (hadLabTimer || hadStrategyTimer)) announce(reason);
}

function configureMotion() {
  const media = window.matchMedia("(prefers-reduced-motion: reduce)");
  state.reducedMotion = media.matches;
  const handleChange = (event) => {
    state.reducedMotion = event.matches;
    if (event.matches) pauseAllPlayback("Reduced-motion preference enabled. Automatic replay stopped; use Previous and Next.");
    document.documentElement.dataset.motion = event.matches ? "reduced" : "full";
  };
  media.addEventListener("change", handleChange);
  document.documentElement.dataset.motion = media.matches ? "reduced" : "full";
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) pauseAllPlayback("Replay paused because this page is no longer visible.");
  });
}

function sampleById(sampleId) {
  return state.realCV?.samples?.find((sample) => sample.id === sampleId) || null;
}

function selectedRealSample() {
  return sampleById(state.selectedSampleId);
}

function displayedRealSample() {
  return sampleById(state.displayedSampleId);
}

function sceneLoadedSampleId() {
  if (state.labBranch === "same") return state.workflowStartLoadedId;
  if (state.labBranch === "fresh") return state.labStep >= 4 ? state.selectedSampleId : null;
  if (state.labBranch === "different") {
    if (state.labStep <= 2) return state.workflowStartLoadedId;
    if (state.labStep === 3) return null;
    return state.selectedSampleId;
  }
  return state.loadedSampleId;
}

function determineBranch(selectedId, loadedId) {
  if (!loadedId) return "fresh";
  return selectedId === loadedId ? "same" : "different";
}

function stepCompletionStatus(index) {
  if (index === 0) return "DONE — FORMULATION SELECTED";
  if (index === 1) {
    if (state.labBranch === "fresh") return "DONE — FRESH START";
    if (state.labBranch === "same") return "DONE — SAME FORMULATION";
    return "DONE — REPLACEMENT REQUIRED";
  }
  if (index === 2) {
    if (state.labBranch === "fresh") return "SKIPPED — NO PREVIOUS SAMPLE";
    if (state.labBranch === "same") return "SKIPPED — SAME FORMULATION";
    return "DONE — PREVIOUS SAMPLE REMOVED AND CELL PREPARED";
  }
  if (index === 3) {
    if (state.labBranch === "same") return "SKIPPED — ALREADY LOADED";
    return "DONE — SAMPLE LOADED AND IDENTIFIED";
  }
  if (index === 4) return "DONE — CELL READY";
  if (index === 5) return "DONE — TWO CYCLES RECORDED";
  return "DONE — AUTHOR-SELECTED SECOND CYCLE SHOWN";
}

function stepVisualStatus(index) {
  const skipped = (index === 2 && state.labBranch !== "different") ||
    (index === 3 && state.labBranch === "same");
  if (skipped) return { state: "skipped", text: stepCompletionStatus(index) };
  if (index < state.labStep) return { state: "done", text: stepCompletionStatus(index) };
  if (index === 6 && state.labStep === 6) return { state: "done", text: stepCompletionStatus(index) };
  if (index === state.labStep) return { state: "active", text: "ACTIVE" };
  return { state: "pending", text: "PENDING" };
}

function labNarration() {
  const selected = selectedRealSample();
  if (!selected) return "No source formulation selected.";
  if (state.labStep === 0) return `${LAB_STEPS[0].label}: ${selected.composition}, pH ${selected.ph}. Selection does not run an experiment yet.`;
  if (state.labStep === 1) return `${BRANCH_COPY[state.labBranch].badge}. ${BRANCH_COPY[state.labBranch].decision}.`;
  if (state.labStep === 2) {
    if (state.labBranch === "fresh") return "SKIPPED — NO PREVIOUS SAMPLE. No removal or rinse is shown.";
    if (state.labBranch === "same") return "SKIPPED — SAME FORMULATION. The loaded sample tag and liquid remain fixed.";
    return "Previous sample removed. Cell/electrodes prepared — exact cleaning follows the laboratory protocol.";
  }
  if (state.labStep === 3) {
    if (state.labBranch === "same") return "SKIPPED — ALREADY LOADED. The same formulation remains in the same cell; physical history may still matter.";
    return `Load and identify ${selected.composition}, pH ${selected.ph}.`;
  }
  if (state.labStep === 4) return "Cell assembled. Connections checked. Protocol-defined equilibration / reference check; no unsupported duration or threshold is asserted.";
  if (state.labStep === 5) return "Potential goes forward and back. The potentiostat controls WE potential relative to RE and records current through the WE–CE circuit.";
  return "Published, author-processed second-cycle curve. Not raw data. This source-specific analysis choice is not a universal CV rule.";
}

function realReplayPoint() {
  const sample = displayedRealSample();
  if (!sample?.points?.length || state.labReplayPercent < 50) return null;
  const fraction = Math.min(1, Math.max(0, (state.labReplayPercent - 50) / 50));
  const index = Math.round(fraction * (sample.points.length - 1));
  return { point: sample.points[index], index, fraction };
}

function waveformPosition(percent) {
  const cyclePosition = percent >= 100 ? 1 : (percent % 50) / 50;
  const x = 683 + 151 * cyclePosition;
  const y = cyclePosition <= 0.5
    ? 337 - 64 * (cyclePosition / 0.5)
    : 273 + 64 * ((cyclePosition - 0.5) / 0.5);
  return { x, y };
}

function trianglePotential(percent) {
  const cyclePosition = percent >= 100 ? 1 : (percent % 50) / 50;
  return cyclePosition <= 0.5
    ? -1.2 * (cyclePosition / 0.5)
    : -1.2 + 1.2 * ((cyclePosition - 0.5) / 0.5);
}

function miniCurvePath(sample, count = null) {
  if (!sample?.points?.length) return "";
  const currents = sample.points.map((point) => Number(point[1]));
  const yAbs = Math.max(1, ...currents.map(Math.abs));
  const x = linearScale(-1.2, 0, 950, 1098);
  const y = linearScale(-yAbs, yAbs, 295, 170);
  const visible = count == null ? sample.points : sample.points.slice(0, Math.max(2, count));
  return visible.map((point, index) => `${index ? "L" : "M"}${x(point[0]).toFixed(1)},${y(point[1]).toFixed(1)}`).join(" ");
}

function renderMiniCurve() {
  const sample = displayedRealSample();
  const fullPath = byId("real-cv-path");
  const progressPath = byId("real-cv-progress-path");
  const cursor = byId("real-cv-cursor");
  if (!sample) {
    fullPath.setAttribute("d", "");
    progressPath.setAttribute("d", "");
    cursor.hidden = true;
    byId("real-cv-awaiting").hidden = false;
    byId("real-provenance-badge").hidden = true;
    return;
  }
  byId("real-cv-awaiting").hidden = true;
  byId("real-provenance-badge").hidden = false;
  fullPath.setAttribute("d", miniCurvePath(sample));
  fullPath.style.stroke = sample.color;
  const replay = realReplayPoint();
  if (state.labStep === 5 && replay) {
    progressPath.setAttribute("d", miniCurvePath(sample, replay.index + 1));
    progressPath.style.stroke = sample.color;
    const currents = sample.points.map((point) => Number(point[1]));
    const yAbs = Math.max(1, ...currents.map(Math.abs));
    const x = linearScale(-1.2, 0, 950, 1098);
    const y = linearScale(-yAbs, yAbs, 295, 170);
    cursor.setAttribute("cx", x(replay.point[0]));
    cursor.setAttribute("cy", y(replay.point[1]));
    cursor.style.fill = sample.color;
    cursor.hidden = false;
  } else {
    progressPath.setAttribute("d", "");
    cursor.hidden = true;
  }
}

function renderDetailedRealCurve() {
  const svg = byId("real-cv-chart");
  const sample = displayedRealSample();
  svg.replaceChildren();
  const title = svgElement("title", { id: "real-chart-title" });
  title.textContent = sample
    ? `Published cyclic voltammogram for ${sample.composition}`
    : state.realReady ? "Published CV awaiting sample load" : "Published cyclic voltammogram unavailable";
  const desc = svgElement("desc", { id: "real-chart-desc" });
  desc.textContent = sample
    ? `Published, author-processed total current density versus working-electrode potential for ${sample.composition}, pH ${sample.ph}.`
    : state.realReady
      ? "A different formulation is selected. No published curve is assigned until Load and identify completes."
      : "The published reference did not load; no substitute curve is drawn.";
  svg.append(title, desc);
  if (!sample) {
    const waiting = svgElement("text", { class: "chart-empty-message", x: 380, y: 210, "text-anchor": "middle" });
    waiting.textContent = "Awaiting sample load — no curve assigned";
    svg.appendChild(waiting);
    return;
  }
  const currents = sample.points.map((point) => Number(point[1]));
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
  const pathFor = (points) => points.map((point, index) => `${index ? "L" : "M"}${frame.x(point[0]).toFixed(2)},${frame.y(point[1]).toFixed(2)}`).join(" ");
  svg.appendChild(svgElement("path", { d: pathFor(sample.points), class: "real-cv-line reference", stroke: sample.color }));
  const replay = realReplayPoint();
  if (state.labStep === 5 && replay) {
    svg.appendChild(svgElement("path", { d: pathFor(sample.points.slice(0, replay.index + 1)), class: "real-cv-line progress", stroke: sample.color }));
    svg.appendChild(svgElement("circle", { class: "chart-cursor", cx: frame.x(replay.point[0]), cy: frame.y(replay.point[1]), r: 6, fill: sample.color }));
  }
}

function updateSampleRecord() {
  const selected = selectedRealSample();
  const displayed = displayedRealSample();
  if (!selected) return;
  byId("real-sample-name").textContent = displayed ? displayed.name : "Awaiting sample load — no curve assigned";
  byId("real-sample-composition").textContent = displayed ? `${displayed.composition} · pH ${displayed.ph}` : `Selected: ${selected.composition} · pH ${selected.ph}`;
  byId("real-protocol").textContent = displayed
    ? `${displayed.protocol.scan_rate_mV_s} mV/s · ${displayed.protocol.cycles_recorded} cycles · cycle ${displayed.protocol.analysis_cycle} shown`
    : "No published curve assigned until Load and identify completes";
  const measurement = state.realCV.measurement;
  const record = byId("sample-record");
  record.replaceChildren();
  [
    ["Selected formulation", selected.composition],
    ["Curve currently shown", displayed ? displayed.composition : "Awaiting sample load — no curve assigned"],
    ["pH", selected.ph],
    ["Working electrode", measurement.working_electrode],
    ["Reference electrode", measurement.reference_electrode],
    ["Counter electrode", measurement.counter_electrode],
    ["Source points", displayed ? `${displayed.point_count} published processed points` : "No curve assigned"],
  ].forEach(([label, value]) => {
    appendText(record, "dt", label);
    appendText(record, "dd", value);
  });
}

function renderLabScene() {
  const selected = selectedRealSample();
  if (!selected) return;
  const sceneIdMap = {
    fecl2_nh4cl: "real-sample-base",
    fecl2_nh4cl_glycine: "real-sample-glycine",
    fecl2_nh4cl_glycine_lactic: "real-sample-lactic",
  };
  Object.entries(sceneIdMap).forEach(([sampleId, elementId]) => {
    byId(elementId).classList.toggle("selected", sampleId === state.selectedSampleId);
  });
  byId("real-scene-selected").textContent = `${selected.composition} · pH ${selected.ph}`;
  byId("mobile-sample-label").textContent = `${selected.composition} · pH ${selected.ph}`;

  const loaded = sampleById(sceneLoadedSampleId());
  const liquid = byId("real-cell-liquid");
  const tag = byId("real-cell-sample-tag");
  liquid.style.fill = loaded?.color || selected.color;
  liquid.dataset.state = loaded ? "loaded" : "empty";
  if (state.labStep === 3 && state.labBranch !== "same") {
    tag.textContent = `LOADING: ${selected.composition}`;
    liquid.dataset.state = "loading";
  } else if (state.labBranch === "different" && state.labStep === 2) {
    tag.textContent = `REMOVING: ${state.workflowStartLoadedId ? sampleById(state.workflowStartLoadedId)?.composition : "previous sample"}`;
    liquid.dataset.state = "removing";
  } else {
    tag.textContent = loaded ? `LOADED: ${loaded.composition}` : "EMPTY / FRESH START";
  }
  byId("mobile-cell-label").textContent = tag.textContent;

  const showDifferentTools = state.labBranch === "different" && (state.labStep === 2 || state.labStep === 3);
  byId("real-waste-tray").hidden = !showDifferentTools;
  byId("real-rinse-tool").hidden = !showDifferentTools;
  ["real-electrode-we", "real-electrode-re", "real-electrode-ce", "real-lead-we", "real-lead-re", "real-lead-ce"].forEach((id) => {
    byId(id).classList.toggle("active", state.labStep >= 4);
  });
  byId("real-potentiostat").classList.toggle("active", state.labStep >= 5);

  const replay = realReplayPoint();
  const cycle = state.labReplayPercent < 50 ? 1 : 2;
  const potential = replay?.point?.[0] ?? trianglePotential(state.labReplayPercent);
  const currentText = replay
    ? `${Number(replay.point[1]).toFixed(3)} mA cm⁻²`
    : state.labStep >= 5 ? "recorded · cycle 1 not retained here" : "current: source replay";
  byId("real-potential-value").textContent = `${Number(potential).toFixed(3)} V`;
  byId("real-current-value").textContent = currentText;
  byId("real-cycle-counter").textContent = `cycle ${cycle} / 2`;
  const position = waveformPosition(state.labReplayPercent);
  byId("real-sweep-cursor").setAttribute("cx", position.x);
  byId("real-sweep-cursor").setAttribute("cy", position.y);

  const scrubber = byId("lab-scrubber");
  scrubber.value = String(state.labReplayPercent);
  const direction = ((state.labReplayPercent >= 100 ? 1 : (state.labReplayPercent % 50) / 50) <= 0.5)
    ? "toward −1.2 V" : "returning toward 0 V";
  const valueText = `${Math.round(state.labReplayPercent)}% · cycle ${cycle} / 2 · ${direction}`;
  byId("lab-scrubber-value").textContent = valueText;
  scrubber.setAttribute("aria-valuetext", valueText);

  byId("real-lab-title").textContent = `Published CV replay for ${selected.composition}`;
  byId("real-lab-desc").textContent = `${BRANCH_COPY[state.labBranch].badge}. Step ${state.labStep + 1} of 7. Potentiostat controls working-electrode potential relative to the reference electrode and records current through the working-counter circuit.`;
  const curveState = displayedRealSample()?.composition || "Awaiting sample load — no curve assigned";
  byId("real-scene-summary").textContent = `${BRANCH_COPY[state.labBranch].route}. Current state: ${LAB_STEPS[state.labStep].label}. Published curve shown: ${curveState}.`;
  renderMiniCurve();
  renderDetailedRealCurve();
  updateSampleRecord();
}

function renderLabWorkflow() {
  const workflow = byId("lab-workflow");
  if (!workflow.children.length) {
    LAB_STEPS.forEach((step, index) => {
      const item = document.createElement("li");
      item.id = `lab-step-${index + 1}`;
      appendText(item, "b", step.label);
      appendText(item, "span", "PENDING", "step-status");
      appendText(item, "small", step.detail);
      workflow.appendChild(item);
    });
  }
  [...workflow.children].forEach((item, index) => {
    const visual = stepVisualStatus(index);
    item.dataset.state = visual.state;
    item.querySelector(".step-status").textContent = visual.text;
    item.setAttribute("aria-current", index === state.labStep ? "step" : "false");
  });
  byId("lab-narration").textContent = labNarration();
}

function renderLabControls() {
  byId("lab-prev").disabled = state.labStep === 0;
  byId("lab-next").disabled = state.labStep >= LAB_STEPS.length - 1;
  byId("lab-scrubber").disabled = state.labStep < 5;
  if (!state.labTimer) byId("lab-play").textContent = state.labStep >= 6 ? "Replay published CV workflow" : "Replay published CV workflow";
}

function renderRealLabState() {
  renderLabWorkflow();
  renderLabScene();
  renderLabControls();
}

function commitSceneLoadedState() {
  state.loadedSampleId = sceneLoadedSampleId();
  if (state.labStep >= 4 && state.selectedSampleId) {
    state.loadedSampleId = state.selectedSampleId;
    state.displayedSampleId = state.selectedSampleId;
  }
}

function selectRealSample(sampleId, { announceSelection = true } = {}) {
  clearLabTimer();
  const currentLoaded = sceneLoadedSampleId();
  state.loadedSampleId = currentLoaded;
  state.workflowStartLoadedId = currentLoaded;
  state.selectedSampleId = sampleId;
  state.labBranch = determineBranch(sampleId, currentLoaded);
  state.labStep = 0;
  state.labReplayPercent = 0;
  if (state.labBranch === "different") {
    state.displayedSampleId = null;
  } else if (state.labBranch === "same") {
    state.displayedSampleId = currentLoaded;
  } else if (!state.displayedSampleId) {
    state.displayedSampleId = sampleId;
  }
  document.querySelectorAll(".sample-tab").forEach((button) => {
    const selected = button.dataset.sample === sampleId;
    button.setAttribute("aria-checked", selected ? "true" : "false");
    button.tabIndex = selected ? 0 : -1;
  });
  renderRealLabState();
  if (announceSelection) announce(`${selectedRealSample().composition} selected. ${BRANCH_COPY[state.labBranch].badge}. ${BRANCH_COPY[state.labBranch].decision}.`);
}

function advanceLabStep({ announceStep = true } = {}) {
  clearLabTimer();
  if (state.labStep >= LAB_STEPS.length - 1) return;
  if (state.labStep === 5) state.labReplayPercent = 100;
  state.labStep += 1;
  commitSceneLoadedState();
  renderRealLabState();
  if (announceStep) announce(`${LAB_STEPS[state.labStep].label}. ${labNarration()}`);
}

function previousLabStep() {
  clearLabTimer();
  if (state.labStep === 0) return;
  state.labStep -= 1;
  if (state.labStep < 5) state.labReplayPercent = 0;
  renderRealLabState();
  announce(`${LAB_STEPS[state.labStep].label}. ${labNarration()}`);
}

function resetLab() {
  clearLabTimer();
  state.loadedSampleId = null;
  state.workflowStartLoadedId = null;
  state.labBranch = "fresh";
  state.labStep = 0;
  state.labReplayPercent = 0;
  if (!state.selectedSampleId) state.selectedSampleId = state.realCV?.samples?.[0]?.id || null;
  if (!state.displayedSampleId) state.displayedSampleId = state.selectedSampleId;
  renderRealLabState();
  announce("Lab reset. EMPTY / FRESH START. No previous sample to remove.");
}

function startLabPlayback() {
  if (!state.realReady) return;
  if (state.labTimer) {
    clearLabTimer();
    byId("lab-play").textContent = "Resume";
    announce("Published workflow replay paused.");
    return;
  }
  if (state.reducedMotion) {
    announce("Reduced motion is active. Use Previous step and Next step to inspect every static state.");
    return;
  }
  if (state.labStep >= 6) resetLab();
  byId("lab-play").textContent = "Pause";
  state.labTimer = window.setInterval(() => {
    if (state.labStep === 5) {
      state.labReplayPercent = Math.min(100, state.labReplayPercent + 3);
      renderRealLabState();
      if (state.labReplayPercent >= 100) {
        state.labStep = 6;
        commitSceneLoadedState();
        clearLabTimer();
        renderRealLabState();
        announce("Published workflow replay complete. Author-selected second-cycle curve shown.");
      }
      return;
    }
    state.labTick += 1;
    if (state.labTick < 7) return;
    state.labTick = 0;
    if (state.labStep < 5) {
      state.labStep += 1;
      commitSceneLoadedState();
      renderRealLabState();
      announce(`${LAB_STEPS[state.labStep].label}.`);
    }
  }, 120);
}

function renderRealSampleControls() {
  const tabs = byId("sample-tabs");
  tabs.replaceChildren();
  state.realCV.samples.forEach((sample, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sample-tab";
    button.dataset.sample = sample.id;
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", index === 0 ? "true" : "false");
    button.setAttribute("aria-label", `${sample.composition}, pH ${sample.ph}`);
    button.tabIndex = index === 0 ? 0 : -1;
    appendText(button, "b", sample.name);
    appendText(button, "span", `${sample.composition} · pH ${sample.ph}`);
    button.addEventListener("click", () => selectRealSample(sample.id));
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      let next = state.realCV.samples.findIndex((entry) => entry.id === sample.id);
      if (event.key === "ArrowRight") next = (next + 1) % state.realCV.samples.length;
      if (event.key === "ArrowLeft") next = (next - 1 + state.realCV.samples.length) % state.realCV.samples.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = state.realCV.samples.length - 1;
      selectRealSample(state.realCV.samples[next].id);
      tabs.querySelector(`[data-sample="${state.realCV.samples[next].id}"]`).focus();
    });
    tabs.appendChild(button);
  });
}

function configureRealControls() {
  byId("lab-prev").addEventListener("click", previousLabStep);
  byId("lab-next").addEventListener("click", () => advanceLabStep());
  byId("lab-reset").addEventListener("click", resetLab);
  byId("lab-play").addEventListener("click", startLabPlayback);
  byId("lab-scrubber").addEventListener("input", (event) => {
    clearLabTimer();
    if (state.labStep < 5) state.labStep = 5;
    state.labReplayPercent = Number(event.target.value);
    if (state.labReplayPercent >= 100) state.labStep = 6;
    renderRealLabState();
  });

  const electrodeCopy = {
    we: ["WE — working electrode", "The potentiostat controls WE potential relative to RE. Current is measured through the WE–CE circuit."],
    re: ["RE — reference electrode", "RE provides the potential reference. It is not drawn as the main current-carrying electrode."],
    ce: ["CE — counter electrode", "CE completes the main current path with WE. It is not the voltage reference."],
  };
  document.querySelectorAll("[data-electrode]").forEach((button) => {
    button.addEventListener("click", () => {
      const [title, copy] = electrodeCopy[button.dataset.electrode];
      state.electrodeTrigger = button;
      byId("electrode-help-title").textContent = title;
      byId("electrode-help-copy").textContent = copy;
      byId("electrode-help").hidden = false;
      byId("electrode-help").focus();
    });
  });
  const closeElectrodeHelp = () => {
    byId("electrode-help").hidden = true;
    state.electrodeTrigger?.focus();
  };
  byId("electrode-help-close").addEventListener("click", closeElectrodeHelp);
  byId("electrode-help").addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeElectrodeHelp();
  });
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

function maxEventCount() {
  return Math.max(0, ...PLANNERS.map((planner) => eventsFor(planner).length));
}

function ledgerCompletion(planner) {
  const ledger = state.ledgers[planner];
  const last = finalEvent(planner);
  if (!ledger || !last) return { complete: false, reason: "No events" };
  if (last.stop != null) return { complete: true, reason: `Stopped: ${last.stop.reason || last.stop.rationale || "planner stopped"}` };
  const world = ledger.world || {};
  const costs = last.costs || {};
  const attemptsExhausted = Number(costs.cumulative_attempt) >= Number(world.total_attempt_budget);
  const measurementsExhausted = Number(costs.cumulative_measurement) >= Number(world.total_measurement_budget);
  if (attemptsExhausted || measurementsExhausted) return { complete: true, reason: "Budget exhausted" };
  return { complete: false, reason: "Campaign artifact is incomplete" };
}

function extractReveal() {
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
  [
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
  ].forEach(([label, value]) => {
    const wrapper = document.createElement("div");
    appendText(wrapper, "dt", label);
    appendText(wrapper, "dd", compact(value));
    identity.appendChild(wrapper);
  });
  const runState = byId("run-state");
  runState.textContent = state.complete ? "COMPLETE" : "INCOMPLETE";
  runState.dataset.state = state.complete ? "complete" : "warning";
}

function plannerDescription(planner) {
  return {
    random: "Legal random choices across the allowed range.",
    fixed_grid: "Predetermined log-spaced choices.",
    information_gain: "Belief-dependent choices targeting uncertainty reduction.",
  }[planner];
}

function finalCosts(planner) {
  const last = finalEvent(planner);
  return {
    attempts: last?.costs?.cumulative_attempt ?? 0,
    operations: last?.costs?.cumulative_measurement ?? 0,
  };
}

function renderComparison() {
  const cards = byId("planner-cards");
  cards.replaceChildren();
  PLANNERS.forEach((planner) => {
    const metrics = resultFor(planner).metrics || {};
    const costs = finalCosts(planner);
    const card = document.createElement("article");
    card.className = `planner-card planner-${planner}`;
    appendText(card, "h3", `${PLANNER_META[planner].icon} ${PLANNER_META[planner].label}`);
    appendText(card, "p", plannerDescription(planner));
    const list = document.createElement("dl");
    [
      ["Choice pattern", PLANNER_META[planner].pattern],
      ["Attempts", costs.attempts],
      ["Executed-operation cost", costs.operations],
      ["Conclusion", `${humanize(metrics.predicted_mechanism || "unknown")} · ${metrics.mechanism_correct === true ? "correct in this run" : "not correct in this run"}`],
    ].forEach(([label, value]) => {
      appendText(list, "dt", label);
      appendText(list, "dd", value);
    });
    card.appendChild(list);
    cards.appendChild(card);
  });

  const metricMaps = Object.fromEntries(PLANNERS.map((planner) => [planner, flattenScalars(resultFor(planner).metrics || {})]));
  const metricKeys = [...new Set(PLANNERS.flatMap((planner) => Object.keys(metricMaps[planner])))].sort();
  const headRow = document.createElement("tr");
  appendText(headRow, "th", "Metric").scope = "col";
  PLANNERS.forEach((planner) => { appendText(headRow, "th", PLANNER_META[planner].label).scope = "col"; });
  byId("comparison-head").replaceChildren(headRow);
  const body = byId("comparison-body");
  body.replaceChildren();
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

function eventStatus(event) {
  if (!event) return { text: "WAITING", className: "" };
  if (event.stop != null) return { text: "STOPPED", className: "stopped" };
  const validation = event.validation || {};
  const accepted = validation.accepted ?? validation.valid ?? validation.is_valid;
  if (accepted === false) return { text: "BLOCKED", className: "blocked" };
  const status = String(event.observation?.status || "").toLowerCase();
  if (["failed", "failure", "error"].includes(status)) return { text: "FAILED", className: "failure" };
  if (event.observation != null) return { text: "MEASURED", className: "success" };
  if (event.request != null) return { text: accepted === true ? "ACCEPTED" : "PROPOSED", className: "" };
  return { text: "RECORDED", className: "" };
}

function rateFor(event) {
  return Number(event?.request?.controls?.scan_rate_mv_s ?? event?.request?.requested_controls?.scan_rate_mv_s);
}

function strategyEventCopy(event, step) {
  if (!step || !event) return "No saved operation has been revealed. All three supplied synthetic models begin with equal planner belief.";
  if (event.stop) return `The planner stops: ${event.stop.reason || event.stop.rationale || "recorded stopping rule"}. It reports ${humanize(event.stop.final_hypothesis || "unknown")} at ${Math.round(Number(event.stop.confidence || 0) * 100)}% belief.`;
  const validation = event.validation || {};
  const accepted = validation.accepted ?? validation.valid ?? validation.is_valid;
  const rate = rateFor(event);
  if (accepted === false) return `The ${compact(rate)} mV/s request was blocked by the public validator. Attempt cost is charged; no observation exists.`;
  if (event.request?.operation === "calibrate") return `CALIBRATION OPERATION. The saved virtual reference check returned ${compact(event.observation?.value)}; this is not a scan-rate experiment.`;
  if (["failed", "failure", "error"].includes(String(event.observation?.status || "").toLowerCase())) {
    return `Injected synthetic failure at ${compact(rate)} mV/s: ${humanize(event.observation?.qc_flags?.[0] || event.observation?.status)}. Attempt and executed-operation cost are charged; no fake zero response is added.`;
  }
  return `Requested ${compact(rate)} mV/s; saved unitless normalized response ${compact(event.observation?.value)}. Planner beliefs update within the three predefined synthetic models.`;
}

function renderBeliefs(after, before) {
  const container = byId("belief-bars");
  container.replaceChildren();
  ["diffusion", "surface", "mixed"].forEach((mechanism) => {
    const afterValue = Number(after?.[mechanism] ?? 1 / 3);
    const beforeValue = Number(before?.[mechanism] ?? 1 / 3);
    const row = document.createElement("div");
    row.className = "belief-row";
    appendText(row, "span", mechanism === "mixed" ? "mixed toy model" : `${mechanism}-like`);
    const track = document.createElement("span");
    track.className = "belief-track";
    const beforeMarker = document.createElement("i");
    beforeMarker.className = "belief-before";
    beforeMarker.style.left = `${Math.max(0, Math.min(100, beforeValue * 100))}%`;
    const fill = document.createElement("i");
    fill.className = `belief-fill ${mechanism}`;
    fill.style.width = `${Math.max(1, afterValue * 100)}%`;
    track.append(fill, beforeMarker);
    row.appendChild(track);
    appendText(row, "b", `${(afterValue * 100).toFixed(1)}%`);
    container.appendChild(row);
  });
}

function renderStrategyChart(events, step) {
  const svg = byId("strategy-chart");
  svg.replaceChildren();
  const title = svgElement("title", { id: "strategy-chart-title" });
  title.textContent = `${PLANNER_META[state.selectedPlanner].label} synthetic response replay`;
  const desc = svgElement("desc", { id: "strategy-chart-desc" });
  desc.textContent = `Three predefined synthetic models and ${Math.min(step, events.length)} saved events. Unitless response; not a CV and not experimental current density.`;
  svg.append(title, desc);
  const frame = drawChartFrame(svg, {
    xMin: 5, xMax: 500, yMin: 0, yMax: 2.35,
    xScale: logScale,
    xTicks: [5, 10, 25, 50, 100, 250, 500],
    yTicks: [0, 0.5, 1, 1.5, 2],
    xFormat: String, yFormat: (value) => value.toFixed(1),
    xLabel: "Requested scan rate / mV s⁻¹ (log scale)",
    yLabel: "Unitless normalized response",
  });
  ["diffusion", "surface", "mixed"].forEach((mechanism) => {
    const points = Array.from({ length: 101 }, (_, index) => 5 * (100 ** (index / 100)));
    const d = points.map((rate, index) => `${index ? "L" : "M"}${frame.x(rate).toFixed(2)},${frame.y(Math.min(2.35, responseFor(mechanism, rate))).toFixed(2)}`).join(" ");
    svg.appendChild(svgElement("path", { d, class: `model-line ${mechanism}` }));
  });
  events.slice(0, Math.min(step, events.length)).forEach((event) => {
    if (event.request?.operation !== "measure") return;
    const rate = rateFor(event);
    if (!Number.isFinite(rate)) return;
    if (eventStatus(event).text === "MEASURED" && Number.isFinite(Number(event.observation?.value))) {
      svg.appendChild(svgElement("circle", { class: "observed-point", cx: frame.x(rate), cy: frame.y(Number(event.observation.value)), r: 6 }));
    } else if (eventStatus(event).text === "FAILED") {
      const x = frame.x(rate);
      const y = frame.y(0.12);
      svg.appendChild(svgElement("line", { class: "failed-point", x1: x - 7, x2: x + 7, y1: y - 7, y2: y + 7 }));
      svg.appendChild(svgElement("line", { class: "failed-point", x1: x - 7, x2: x + 7, y1: y + 7, y2: y - 7 }));
    }
  });
  const currentEvent = step ? events[Math.min(step, events.length) - 1] : null;
  const currentRate = rateFor(currentEvent);
  if (Number.isFinite(currentRate) && currentRate >= 5 && currentRate <= 500) {
    const x = frame.x(currentRate);
    svg.appendChild(svgElement("line", { class: "chosen-rate", x1: x, x2: x, y1: frame.top, y2: frame.bottom }));
    const label = svgElement("text", { class: "chosen-rate-label", x: x + 5, y: frame.top + 14 });
    label.textContent = `${compact(currentRate)} mV/s chosen`;
    svg.appendChild(label);
  }
  const legend = svgElement("g", { class: "chart-legend" });
  [["diffusion", 90, "diffusion-like"], ["surface", 245, "surface-like"], ["mixed", 385, "mixed toy model"]].forEach(([name, x, labelText]) => {
    legend.appendChild(svgElement("line", { class: `model-line ${name}`, x1: x, x2: Number(x) + 26, y1: 16, y2: 16 }));
    const label = svgElement("text", { x: Number(x) + 32, y: 20 });
    label.textContent = labelText;
    legend.appendChild(label);
  });
  svg.appendChild(legend);
}

function renderSyntheticLoop(event, step) {
  const elements = [
    byId("synthetic-state-select"), byId("synthetic-state-validate"),
    byId("synthetic-state-execute"), byId("synthetic-state-beliefs"), byId("synthetic-state-stop"),
  ];
  elements.forEach((element, index) => {
    element.dataset.state = step ? "done" : index === 0 ? "active" : "pending";
  });
  if (!step || !event) return;
  if (event.stop) {
    elements.slice(0, 4).forEach((element) => { element.dataset.state = "skipped"; });
    elements[4].dataset.state = "stopped";
    return;
  }
  const status = eventStatus(event).text;
  if (status === "BLOCKED") {
    elements[1].dataset.state = "blocked";
    elements.slice(2).forEach((element) => { element.dataset.state = "skipped"; });
  } else if (status === "FAILED") {
    elements[2].dataset.state = "failure";
    elements[3].dataset.state = "skipped";
    elements[4].dataset.state = "done";
  } else {
    elements[4].dataset.state = "done";
  }
}

function laneEvent(planner) {
  const events = eventsFor(planner);
  if (!state.strategyStep || !events.length) return null;
  return events[Math.min(state.strategyStep, events.length) - 1];
}

function renderPlannerLanes() {
  PLANNERS.forEach((planner) => {
    const button = byId(`synthetic-planner-${planner.replace(/_/g, "-")}`);
    const event = laneEvent(planner);
    const costs = event?.costs || {};
    const selected = planner === state.selectedPlanner;
    const atEnd = state.strategyStep >= eventsFor(planner).length && eventsFor(planner).length > 0;
    const status = atEnd && ledgerCompletion(planner).complete ? "STOPPED" : eventStatus(event).text;
    button.replaceChildren();
    appendText(button, "span", `${PLANNER_META[planner].icon} ${PLANNER_META[planner].label}`, "lane-name");
    appendText(button, "span", `${PLANNER_META[planner].pattern} choices`, "lane-pattern");
    appendText(button, "span", `${status} · attempts ${costs.cumulative_attempt ?? 0} · operations ${costs.cumulative_measurement ?? 0}`, "lane-state");
    button.setAttribute("aria-selected", selected ? "true" : "false");
    button.tabIndex = selected ? 0 : -1;
  });
}

function renderBudget(event) {
  const ledger = state.ledgers[state.selectedPlanner];
  const attempts = event?.costs?.cumulative_attempt ?? 0;
  const operations = event?.costs?.cumulative_measurement ?? 0;
  byId("synthetic-budget-status").textContent = `Attempts ${attempts}/${ledger?.world?.total_attempt_budget ?? "—"} · Executed-operation cost ${operations}/${ledger?.world?.total_measurement_budget ?? "—"}`;
}

function renderStrategyStep() {
  if (!state.syntheticReady) return;
  const events = eventsFor(state.selectedPlanner);
  const step = Math.max(0, Math.min(state.strategyStep, maxEventCount()));
  const localStep = Math.min(step, events.length);
  const event = localStep ? events[localStep - 1] : null;
  const status = eventStatus(event);
  byId("strategy-step-title").textContent = event
    ? `Event ${localStep} of ${events.length} · ${status.text}`
    : `Before event 1 of ${events.length}`;
  byId("strategy-step-copy").textContent = strategyEventCopy(event, localStep);
  byId("virtual-operation-status").textContent = event?.request?.operation === "calibrate"
    ? "CALIBRATION OPERATION"
    : status.text === "FAILED" ? "Injected synthetic failure"
      : status.text === "BLOCKED" ? "not executed"
        : status.text === "MEASURED" ? "unitless response returned"
          : status.text.toLowerCase();
  renderBeliefs(event?.beliefs_after, event?.beliefs_before);
  renderBudget(event);
  renderSyntheticLoop(event, localStep);
  renderStrategyChart(events, localStep);
  renderPlannerLanes();
  renderEventList(state.selectedPlanner);
  byId("strategy-text-summary").textContent = `${PLANNER_META[state.selectedPlanner].label}: ${strategyEventCopy(event, localStep)} ${event ? `Status ${status.text}.` : ""}`;

  const max = maxEventCount();
  const scrubber = byId("strategy-scrubber");
  scrubber.max = String(max);
  scrubber.value = String(step);
  scrubber.setAttribute("aria-label", `Campaign event, 0 to ${max}`);
  scrubber.setAttribute("aria-valuetext", `Event ${step} of ${max}`);
  byId("strategy-scrubber-value").textContent = `${step} / ${max}`;
  byId("strategy-prev").disabled = step === 0;
  byId("strategy-next").disabled = step >= max;
}

function reasonFor(event) {
  return event.stop?.reason || event.stop?.rationale || event.request?.reason ||
    event.request?.rationale || event.validation?.reason || event.validation?.message || "—";
}

function requestFor(event) {
  if (!event.request) return "—";
  return compact(event.request.controls || event.request.requested_controls || event.request);
}

function observationFor(event) {
  const observation = event.observation;
  if (!observation) return "—";
  if (observation.value != null) return `${compact(observation.value)} unitless normalized response`;
  return compact(observation.status || observation.qc_flags || observation);
}

function addEventField(grid, label, value) {
  const field = document.createElement("div");
  field.className = "event-field";
  appendText(field, "b", label);
  appendText(field, "span", compact(value));
  grid.appendChild(field);
}

function renderEventList(planner) {
  const list = byId("event-list");
  list.replaceChildren();
  const ledger = state.ledgers[planner];
  eventsFor(planner).forEach((event, index) => {
    const item = document.createElement("li");
    item.className = "event";
    item.dataset.revealed = index < state.strategyStep ? "true" : "false";
    const card = document.createElement("article");
    card.className = "event-card";
    const top = document.createElement("div");
    top.className = "event-top";
    appendText(top, "h3", `Event ${event.sequence ?? index + 1}`);
    const status = eventStatus(event);
    appendText(top, "span", status.text, `event-status ${status.className}`);
    card.appendChild(top);
    const grid = document.createElement("div");
    grid.className = "event-grid";
    addEventField(grid, "Request", requestFor(event));
    addEventField(grid, "Reason", reasonFor(event));
    addEventField(grid, "Observation", observationFor(event));
    addEventField(grid, "Attempt cost", event.costs?.attempt ?? 0);
    addEventField(grid, "Executed-operation cost", event.costs?.measurement ?? 0);
    addEventField(grid, "Remaining budget", {
      attempts: Number(ledger.world?.total_attempt_budget ?? 0) - Number(event.costs?.cumulative_attempt ?? 0),
      operations: Number(ledger.world?.total_measurement_budget ?? 0) - Number(event.costs?.cumulative_measurement ?? 0),
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

function selectPlanner(planner, { focus = false } = {}) {
  clearStrategyTimer();
  state.selectedPlanner = planner;
  byId("replay-panel").setAttribute("aria-labelledby", `synthetic-planner-${planner.replace(/_/g, "-")}`);
  renderStrategyStep();
  if (focus) byId(`synthetic-planner-${planner.replace(/_/g, "-")}`).focus();
}

function configurePlannerTabs() {
  PLANNERS.forEach((planner) => {
    const button = byId(`synthetic-planner-${planner.replace(/_/g, "-")}`);
    button.addEventListener("click", () => selectPlanner(planner));
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      let next = PLANNERS.indexOf(planner);
      if (event.key === "ArrowRight") next = (next + 1) % PLANNERS.length;
      if (event.key === "ArrowLeft") next = (next - 1 + PLANNERS.length) % PLANNERS.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = PLANNERS.length - 1;
      selectPlanner(PLANNERS[next], { focus: true });
    });
  });
}

function setStrategyStep(step, { announceStep = true } = {}) {
  clearStrategyTimer();
  state.strategyStep = Math.max(0, Math.min(Number(step), maxEventCount()));
  renderStrategyStep();
  if (announceStep) {
    const event = laneEvent(state.selectedPlanner);
    announce(`Synthetic campaign event ${state.strategyStep} of ${maxEventCount()}. ${PLANNER_META[state.selectedPlanner].label}: ${eventStatus(event).text}.`);
  }
}

function resetStrategy() {
  clearStrategyTimer();
  state.strategyStep = 0;
  renderStrategyStep();
  announce("Synthetic replay reset. All three isolated planner lanes returned to event zero.");
}

function startStrategyPlayback() {
  if (!state.syntheticReady) return;
  if (state.strategyTimer) {
    clearStrategyTimer();
    byId("strategy-play").textContent = "Resume";
    announce("Synthetic planner replay paused.");
    return;
  }
  if (state.reducedMotion) {
    announce("Reduced motion is active. Use Previous event and Next event to inspect every saved event.");
    return;
  }
  if (state.strategyStep >= maxEventCount()) state.strategyStep = 0;
  byId("strategy-play").textContent = "Pause";
  state.strategyTimer = window.setInterval(() => {
    state.strategyStep += 1;
    renderStrategyStep();
    if (state.strategyStep >= maxEventCount()) {
      clearStrategyTimer();
      byId("strategy-play").textContent = "Play all";
      announce("Synthetic replay complete. All planner lanes show their final recorded state.");
    }
  }, 1050);
}

function configureStrategyControls() {
  byId("strategy-prev").addEventListener("click", () => setStrategyStep(state.strategyStep - 1));
  byId("strategy-next").addEventListener("click", () => setStrategyStep(state.strategyStep + 1));
  byId("strategy-reset").addEventListener("click", resetStrategy);
  byId("strategy-play").addEventListener("click", startStrategyPlayback);
  byId("strategy-scrubber").addEventListener("input", (event) => setStrategyStep(event.target.value, { announceStep: false }));
}

function configureReveal() {
  const button = byId("reveal-button");
  const explanation = byId("reveal-explanation");
  if (!state.complete) {
    button.disabled = true;
    explanation.textContent = "Synthetic truth cannot be revealed because one or more verified campaign artifacts are incomplete.";
    return;
  }
  if (!state.reveal) {
    button.disabled = true;
    explanation.textContent = "All campaigns are complete, but this verified artifact schema did not publish post-run truth.";
    return;
  }
  button.disabled = false;
  explanation.textContent = "All verified campaign artifacts are complete. The post-run answer remains synthetic truth, not experimental truth.";
}

function revealTruth() {
  if (!state.complete || !state.reveal) return;
  const panel = byId("truth-panel");
  panel.hidden = false;
  byId("truth-value").textContent = JSON.stringify(state.reveal, null, 2);
  byId("replay-identity").textContent = JSON.stringify({
    scenario_commitment: state.manifest.scenario_identity?.scenario_sha256 || null,
    replay_key: state.reveal.replay_key,
    private_seeds: state.reveal.private_seeds,
    planner_seed: state.reveal.planner_seed,
  }, null, 2);
  byId("reveal-button").disabled = true;
  byId("reveal-button").textContent = "Synthetic benchmark truth revealed below";
  panel.focus();
  announce("Synthetic truth revealed. It is not experimental truth.");
}

function diagnosisAssert(condition, message) {
  if (!condition) throw new Error(message);
}

function diagnosisExactObject(value, fields, label) {
  diagnosisAssert(value && typeof value === "object" && !Array.isArray(value), `${label} must be an object`);
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  diagnosisAssert(actual.length === expected.length && actual.every((key, index) => key === expected[index]), `${label} has an unknown or missing field`);
}

function diagnosisCanonicalJson(value) {
  if (value === null || typeof value === "boolean" || typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number") {
    diagnosisAssert(Number.isFinite(value), "Canonical JSON rejects non-finite numbers");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(diagnosisCanonicalJson).join(",")}]`;
  diagnosisAssert(value && typeof value === "object", "Canonical JSON rejects unsupported values");
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${diagnosisCanonicalJson(value[key])}`).join(",")}}`;
}

async function diagnosisSha256Bytes(bytes) {
  diagnosisAssert(window.crypto?.subtle, "Web Crypto is required to verify diagnosis evidence");
  const digest = await window.crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function diagnosisSha256Text(value) {
  return diagnosisSha256Bytes(new TextEncoder().encode(value));
}

function diagnosisWithout(object, field) {
  return Object.fromEntries(Object.entries(object).filter(([key]) => key !== field));
}

function diagnosisHasSecretKey(value) {
  if (!value || typeof value !== "object") return false;
  if (Array.isArray(value)) return value.some(diagnosisHasSecretKey);
  return Object.entries(value).some(([key, child]) => DIAGNOSIS_SECRET_KEYS.has(key) || diagnosisHasSecretKey(child));
}

function diagnosisValidateBeliefs(beliefs, label) {
  diagnosisAssert(Array.isArray(beliefs) && beliefs.length === 5, `${label} must contain five values`);
  beliefs.forEach((value) => diagnosisAssert(Number.isFinite(value) && value >= 0 && value <= 1, `${label} contains an invalid value`));
  diagnosisAssert(Math.abs(beliefs.reduce((sum, value) => sum + value, 0) - 1) <= 1e-12, `${label} does not sum to one`);
}

function diagnosisValidatePeak(peak, label) {
  diagnosisExactObject(peak, ["Epa_v", "Epc_v", "ipa_a", "ipc_a", "midpoint_v", "delta_Ep_v", "ipa_abs_over_ipc_abs"], label);
  Object.values(peak).forEach((value) => diagnosisAssert(Number.isFinite(value), `${label} contains a non-finite value`));
}

async function diagnosisValidateCurve(curve, label) {
  diagnosisExactObject(curve, ["point_count", "potential_reference", "potential_unit", "current_unit", "potential_v", "current_a", "sweep_direction", "curve_hash"], label);
  diagnosisAssert(curve.point_count === 122 && curve.potential_reference === "synthetic_SHE" && curve.potential_unit === "V" && curve.current_unit === "A", `${label} metadata is invalid`);
  diagnosisAssert(curve.potential_v.length === 122 && curve.current_a.length === 122 && curve.sweep_direction.length === 122, `${label} arrays must contain 122 points`);
  curve.current_a.forEach((value) => diagnosisAssert(Number.isFinite(value), `${label} current is invalid`));
  curve.potential_v.forEach((value, index) => {
    const expected = index <= 60 ? 0.650 + 0.005 * index : 0.950 - 0.005 * (index - 61);
    const direction = index <= 60 ? "forward" : "reverse";
    diagnosisAssert(Number.isFinite(value) && Math.abs(value - expected) <= 1e-12, `${label} potential grid is invalid`);
    diagnosisAssert(curve.sweep_direction[index] === direction, `${label} sweep direction is invalid`);
  });
  const expectedHash = await diagnosisSha256Text(diagnosisCanonicalJson(diagnosisWithout(curve, "curve_hash")));
  diagnosisAssert(expectedHash === curve.curve_hash, `${label} hash does not verify`);
}

function diagnosisExtractPeak(curve) {
  let pa = 0;
  let pc = 61;
  for (let index = 1; index <= 60; index += 1) if (curve.current_a[index] > curve.current_a[pa]) pa = index;
  for (let index = 62; index < 122; index += 1) if (curve.current_a[index] < curve.current_a[pc]) pc = index;
  const Epa = curve.potential_v[pa];
  const Epc = curve.potential_v[pc];
  const ipa = curve.current_a[pa];
  const ipc = curve.current_a[pc];
  return { Epa_v: Epa, Epc_v: Epc, ipa_a: ipa, ipc_a: ipc, midpoint_v: (Epa + Epc) / 2, delta_Ep_v: Epa - Epc, ipa_abs_over_ipc_abs: Math.abs(ipa) / Math.abs(ipc) };
}

function diagnosisValidatePeakAgainstCurve(peak, curve, label) {
  const extracted = diagnosisExtractPeak(curve);
  ["Epa_v", "Epc_v", "midpoint_v", "delta_Ep_v", "ipa_abs_over_ipc_abs"].forEach((field) => diagnosisAssert(Math.abs(peak[field] - extracted[field]) <= 1e-12, `${label} ${field} fails curve QC`));
  ["ipa_a", "ipc_a"].forEach((field) => diagnosisAssert(Math.abs(peak[field] - extracted[field]) <= 1e-18, `${label} ${field} fails curve QC`));
}

async function diagnosisValidateObservation(observation, label) {
  diagnosisExactObject(observation, ["kind", "feature_name", "value", "unit", "peak", "curve", "qc_status", "evidence_hash"], label);
  diagnosisAssert(observation.qc_status === "passed", `${label} QC status is invalid`);
  if (observation.kind === "cv") {
    diagnosisAssert(observation.feature_name === null && observation.value === null && observation.unit === null && observation.peak && observation.curve, `${label} CV nullability is invalid`);
    diagnosisValidatePeak(observation.peak, `${label}.peak`);
    await diagnosisValidateCurve(observation.curve, `${label}.curve`);
    diagnosisValidatePeakAgainstCurve(observation.peak, observation.curve, label);
  } else {
    const pairs = { ru_ohm: "ohm", reference_offset_v: "V", blank_current_a: "A", recovery_ratio: "ratio", control_delta_Ep_v: "V" };
    diagnosisAssert(observation.kind === "scalar" && pairs[observation.feature_name] === observation.unit && Number.isFinite(observation.value), `${label} scalar shape is invalid`);
    diagnosisAssert(observation.peak === null && observation.curve === null, `${label} scalar must not carry a curve`);
  }
  const expectedHash = await diagnosisSha256Text(diagnosisCanonicalJson(diagnosisWithout(observation, "evidence_hash")));
  diagnosisAssert(expectedHash === observation.evidence_hash, `${label} evidence hash does not verify`);
}

function diagnosisValidateRecommendation(recommendation) {
  if (recommendation === null) return;
  diagnosisExactObject(recommendation, DIAGNOSIS_RECOMMENDATION_FIELDS, "Recommendation");
  diagnosisAssert(recommendation.planner_id === "expected_information_gain_v1" && recommendation.planner_version === "1.0.0", "Recommendation planner identity is invalid");
  diagnosisAssert(recommendation.reason_code === "max_expected_information" && recommendation.reason_text === "This eligible experiment has the highest expected information gain under the public five-hypothesis model.", "Recommendation reason is invalid");
  diagnosisAssert(Number.isInteger(recommendation.state_version) && recommendation.state_version >= 0, "Recommendation state version is invalid");
  diagnosisAssert(recommendation.attempt_cost === 1 && recommendation.measurement_cost === 1 && Number.isFinite(recommendation.expected_information_gain_nats) && recommendation.expected_information_gain_nats >= 0, "Recommendation costs or score are invalid");
  diagnosisAssert(DIAGNOSIS_ACTIONS.some((action) => action.operation === recommendation.operation && diagnosisCanonicalJson(action.controls) === diagnosisCanonicalJson(recommendation.controls)), "Recommendation action is outside the frozen action table");
}

async function diagnosisValidateRecommendationHash(recommendation) {
  if (recommendation === null) return;
  const input = { operation: recommendation.operation, controls: recommendation.controls, state_version: recommendation.state_version, planner_id: recommendation.planner_id, planner_version: recommendation.planner_version };
  const expected = await diagnosisSha256Text(diagnosisCanonicalJson(input));
  diagnosisAssert(recommendation.action_input_hash === expected && recommendation.recommendation_id === expected, "Recommendation binding hash is invalid");
}

function diagnosisValidateState(campaignState) {
  diagnosisExactObject(campaignState, ["campaign_id", "scenario_id", "scenario_version", "state_version", "status", "beliefs", "budget", "success_count", "successful_operations", "recommendation", "last_valid_curve_hash", "ledger_head_hash", "stop"], "State");
  diagnosisAssert(campaignState.scenario_id === "cv_diagnosis_v1" && campaignState.scenario_version === "1.0.0" && Number.isInteger(campaignState.state_version), "State identity is invalid");
  diagnosisValidateBeliefs(campaignState.beliefs, "State beliefs");
  diagnosisExactObject(campaignState.budget, ["attempt_limit", "attempt_used", "measurement_limit", "measurement_used"], "Budget");
  diagnosisAssert(campaignState.budget.attempt_limit === 12 && campaignState.budget.measurement_limit === 10, "Budget limits are invalid");
  diagnosisAssert(Number.isInteger(campaignState.budget.attempt_used) && campaignState.budget.attempt_used >= 0 && campaignState.budget.attempt_used <= 12, "Attempt budget is invalid");
  diagnosisAssert(Number.isInteger(campaignState.budget.measurement_used) && campaignState.budget.measurement_used >= 0 && campaignState.budget.measurement_used <= 10, "Measurement budget is invalid");
  diagnosisAssert(Number.isInteger(campaignState.success_count) && campaignState.success_count >= 0, "Success count is invalid");
  diagnosisAssert(Array.isArray(campaignState.successful_operations), "Successful operations must be an array");
  diagnosisExactObject(campaignState.stop, ["terminal", "reason"], "Stop");
  diagnosisValidateRecommendation(campaignState.recommendation);
  if (campaignState.recommendation !== null) diagnosisAssert(campaignState.recommendation.state_version === campaignState.state_version, "Recommendation is bound to the wrong state version");
  diagnosisValidateStateSurface(campaignState);
}

async function diagnosisValidateEvent(event, label) {
  diagnosisExactObject(event, ["event_id", "event_index", "event_type", "request_id", "idempotency_input_hash", "state_version_before", "state_version_after", "recommendation_id", "operation", "controls", "status", "failure_code", "failure_message", "rejection_code", "rejection_message", "attempt_cost", "measurement_cost", "observation", "beliefs_before", "beliefs_after", "previous_event_hash", "event_hash"], label);
  diagnosisAssert(Number.isInteger(event.event_index) && event.event_index >= 0 && event.event_id === `event-${event.event_index + 1}`, `${label} index or identity is invalid`);
  diagnosisAssert(["action", "stop"].includes(event.event_type) && ["success", "timeout", "qc_failed", "rejected"].includes(event.status), `${label} type or status is invalid`);
  diagnosisAssert(typeof event.request_id === "string" && event.request_id.length > 0 && /^[0-9a-f]{64}$/.test(event.idempotency_input_hash), `${label} request identity is invalid`);
  diagnosisAssert(Number.isInteger(event.state_version_before) && event.state_version_after === event.state_version_before + 1, `${label} state-version transition is invalid`);
  diagnosisAssert(/^[0-9a-f]{64}$/.test(event.previous_event_hash) && /^[0-9a-f]{64}$/.test(event.event_hash), `${label} ledger hashes are invalid`);
  diagnosisValidateBeliefs(event.beliefs_before, `${label}.beliefs_before`);
  diagnosisValidateBeliefs(event.beliefs_after, `${label}.beliefs_after`);
  if (event.observation !== null) await diagnosisValidateObservation(event.observation, `${label}.observation`);
  diagnosisAssert(event.attempt_cost === 1, `${label} must charge one attempt`);
  if (event.event_type === "action" && event.status !== "rejected") {
    diagnosisAssert(typeof event.recommendation_id === "string" && DIAGNOSIS_ACTIONS.some((action) => action.operation === event.operation && diagnosisSame(action.controls, event.controls)), `${label} executed action is outside the frozen action table`);
  }
  const isExecuted = ["success", "timeout", "qc_failed"].includes(event.status);
  diagnosisAssert(event.measurement_cost === (isExecuted ? 1 : 0), `${label} measurement cost does not match status`);
  if (event.status === "success") {
    diagnosisAssert(event.event_type === "action" && event.observation !== null, `${label} success must be an observed action`);
    diagnosisAssert(event.failure_code === null && event.failure_message === null && event.rejection_code === null && event.rejection_message === null, `${label} success carries failure metadata`);
  } else {
    diagnosisAssert(event.observation === null && diagnosisSame(event.beliefs_before, event.beliefs_after), `${label} failure/rejection must preserve beliefs and carry no observation`);
  }
  if (["timeout", "qc_failed"].includes(event.status)) {
    const expected = event.status === "timeout"
      ? ["TIMEOUT", "Operation timed out; no observation was created."]
      : ["CURVE_QC_FAILED", "Generated CV evidence failed contract QC; no observation was created."];
    diagnosisAssert(event.event_type === "action" && event.failure_code === expected[0] && event.failure_message === expected[1], `${label} failure metadata is invalid`);
    diagnosisAssert(event.rejection_code === null && event.rejection_message === null, `${label} failure carries rejection metadata`);
  }
  if (event.status === "rejected") {
    diagnosisAssert(event.failure_code === null && event.failure_message === null && DIAGNOSIS_REJECTION_MESSAGES[event.rejection_code] === event.rejection_message, `${label} rejection metadata is invalid`);
    diagnosisAssert(event.recommendation_id === null || typeof event.recommendation_id === "string", `${label} rejected recommendation identity is not sanitized`);
    diagnosisAssert(event.operation === null || DIAGNOSIS_ACTIONS.some((action) => action.operation === event.operation), `${label} rejected operation is not sanitized`);
    diagnosisAssert(event.controls === null || (event.operation !== null && DIAGNOSIS_ACTIONS.some((action) => action.operation === event.operation && diagnosisSame(action.controls, event.controls))), `${label} rejected controls are not sanitized`);
  }
  if (event.event_type === "stop") diagnosisAssert(event.status === "rejected" && event.operation === null && event.controls === null && event.recommendation_id === null, `${label} stop event shape is invalid`);
  const expectedHash = await diagnosisSha256Text(diagnosisCanonicalJson(diagnosisWithout(event, "event_hash")));
  diagnosisAssert(expectedHash === event.event_hash, `${label} event hash does not verify`);
}

function diagnosisSame(left, right) {
  return diagnosisCanonicalJson(left) === diagnosisCanonicalJson(right);
}

function diagnosisSuccessfulOperations(previous, event) {
  const operations = [...previous];
  if (event.status === "success" && !operations.includes(event.operation)) operations.push(event.operation);
  return operations;
}

function diagnosisLastCurveHash(previous, event) {
  return event.status === "success" && event.observation?.kind === "cv"
    ? event.observation.curve.curve_hash
    : previous;
}

function diagnosisValidateStateSurface(campaignState) {
  diagnosisAssert(["active", "stopped", "budget_exhausted"].includes(campaignState.status), "State status is invalid");
  diagnosisAssert(/^[0-9a-f]{64}$/.test(campaignState.ledger_head_hash), "State ledger head is invalid");
  diagnosisAssert(campaignState.last_valid_curve_hash === null || /^[0-9a-f]{64}$/.test(campaignState.last_valid_curve_hash), "State last curve hash is invalid");
  diagnosisAssert(campaignState.success_count <= campaignState.budget.measurement_used, "State success count exceeds executed measurements");
  diagnosisAssert(campaignState.successful_operations.every((operation) => DIAGNOSIS_ACTIONS.some((action) => action.operation === operation)), "State contains an unknown successful operation");
  diagnosisAssert(new Set(campaignState.successful_operations).size === campaignState.successful_operations.length, "State successful operations contain duplicates");
  if (campaignState.status === "active") {
    diagnosisAssert(!campaignState.stop.terminal && campaignState.stop.reason === null && campaignState.recommendation !== null, "Active State terminal/recommendation fields are inconsistent");
  } else {
    diagnosisAssert(campaignState.stop.terminal && campaignState.recommendation === null, "Terminal State fields are inconsistent");
    diagnosisAssert(campaignState.status === "budget_exhausted" ? campaignState.stop.reason === "budget_exhausted" : ["confident_diagnosis", "low_expected_information"].includes(campaignState.stop.reason), "Terminal State reason is inconsistent");
  }
}

function diagnosisReconcileTransition(previousState, nextState, event) {
  diagnosisAssert(event !== null, "Charged action response omitted its event");
  diagnosisAssert(previousState.campaign_id === nextState.campaign_id && previousState.scenario_id === nextState.scenario_id && previousState.scenario_version === nextState.scenario_version, "Action State identity changed across the transition");
  diagnosisAssert(event.state_version_before === previousState.state_version && event.state_version_after === nextState.state_version, "Action event and State versions do not reconcile");
  diagnosisAssert(event.previous_event_hash === previousState.ledger_head_hash && event.event_hash === nextState.ledger_head_hash, "Action event and State ledger heads do not reconcile");
  diagnosisAssert(diagnosisSame(event.beliefs_before, previousState.beliefs) && diagnosisSame(event.beliefs_after, nextState.beliefs), "Action event and State beliefs do not reconcile");
  diagnosisAssert(nextState.budget.attempt_used === previousState.budget.attempt_used + event.attempt_cost && nextState.budget.measurement_used === previousState.budget.measurement_used + event.measurement_cost, "Action event and State budget deltas do not reconcile");
  diagnosisAssert(nextState.success_count === previousState.success_count + (event.status === "success" ? 1 : 0), "Action event and State success count do not reconcile");
  diagnosisAssert(diagnosisSame(nextState.successful_operations, diagnosisSuccessfulOperations(previousState.successful_operations, event)), "Action event and State successful operations do not reconcile");
  diagnosisAssert(nextState.last_valid_curve_hash === diagnosisLastCurveHash(previousState.last_valid_curve_hash, event), "Action event and State last curve do not reconcile");
}

async function diagnosisReconcileLedger(campaignState, events, prior) {
  diagnosisValidateBeliefs(prior, "Ledger prior");
  const genesis = await diagnosisSha256Text(diagnosisCanonicalJson({ campaign_id: campaignState.campaign_id, scenario_id: campaignState.scenario_id, scenario_version: campaignState.scenario_version }));
  let version = 0;
  let head = genesis;
  let beliefs = [...prior];
  let attemptUsed = 0;
  let measurementUsed = 0;
  let successCount = 0;
  let successfulOperations = [];
  let lastCurveHash = null;
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index];
    diagnosisAssert(event.event_index === index && event.event_id === `event-${index + 1}`, `Ledger event ${index} is out of order`);
    diagnosisAssert(event.state_version_before === version && event.state_version_after === version + 1, `Ledger event ${index} version is discontinuous`);
    diagnosisAssert(event.previous_event_hash === head, `Ledger event ${index} previous hash is discontinuous`);
    diagnosisAssert(diagnosisSame(event.beliefs_before, beliefs), `Ledger event ${index} beliefs_before is discontinuous`);
    version = event.state_version_after;
    head = event.event_hash;
    beliefs = [...event.beliefs_after];
    attemptUsed += event.attempt_cost;
    measurementUsed += event.measurement_cost;
    if (event.status === "success") successCount += 1;
    successfulOperations = diagnosisSuccessfulOperations(successfulOperations, event);
    lastCurveHash = diagnosisLastCurveHash(lastCurveHash, event);
  }
  diagnosisAssert(campaignState.state_version === version && campaignState.ledger_head_hash === head, "Ledger head/version do not reconcile with State");
  diagnosisAssert(diagnosisSame(campaignState.beliefs, beliefs), "Ledger final beliefs do not reconcile with State");
  diagnosisAssert(campaignState.budget.attempt_used === attemptUsed && campaignState.budget.measurement_used === measurementUsed, "Ledger costs do not reconcile with State budget");
  diagnosisAssert(campaignState.success_count === successCount && diagnosisSame(campaignState.successful_operations, successfulOperations), "Ledger successes do not reconcile with State");
  diagnosisAssert(campaignState.last_valid_curve_hash === lastCurveHash, "Ledger last valid curve does not reconcile with State");
  return true;
}

async function diagnosisValidateFixture(fixture, label) {
  diagnosisExactObject(fixture, ["provenance", "likelihood_role", "peak", "curve"], label);
  diagnosisAssert(fixture.provenance === "simulated" && fixture.likelihood_role === "excluded", `${label} provenance is invalid`);
  diagnosisValidatePeak(fixture.peak, `${label}.peak`);
  await diagnosisValidateCurve(fixture.curve, `${label}.curve`);
  diagnosisValidatePeakAgainstCurve(fixture.peak, fixture.curve, label);
}

async function diagnosisValidateScenario(scenario) {
  diagnosisExactObject(scenario, ["scenario_id", "scenario_version", "planner_id", "planner_version", "belief_method", "prior", "attempt_limit", "measurement_limit", "hypotheses", "actions", "comparator", "initial_trigger", "commitment"], "Scenario");
  diagnosisAssert(scenario.scenario_id === "cv_diagnosis_v1" && scenario.scenario_version === "1.0.0" && scenario.planner_id === "expected_information_gain_v1" && scenario.planner_version === "1.0.0", "Scenario identity is invalid");
  diagnosisValidateBeliefs(scenario.prior, "Scenario prior");
  diagnosisAssert(scenario.attempt_limit === 12 && scenario.measurement_limit === 10 && scenario.hypotheses.length === 5 && scenario.actions.length === 12, "Scenario dimensions are invalid");
  scenario.hypotheses.forEach((hypothesis, index) => {
    diagnosisExactObject(hypothesis, ["id", "label", "order"], `Hypothesis ${index}`);
    diagnosisAssert(hypothesis.id === DIAGNOSIS_HYPOTHESIS_ORDER[index] && hypothesis.order === index, "Hypothesis order is invalid");
  });
  scenario.actions.forEach((action, index) => {
    diagnosisExactObject(action, ["operation", "controls", "display_label", "attempt_cost", "measurement_cost"], `ActionSpec ${index}`);
    const expected = DIAGNOSIS_ACTIONS[index];
    diagnosisAssert(action.operation === expected.operation && diagnosisCanonicalJson(action.controls) === diagnosisCanonicalJson(expected.controls), `ActionSpec ${index} is outside the frozen action table`);
    diagnosisAssert(typeof action.display_label === "string" && action.display_label.trim().length > 0 && action.attempt_cost === 1 && action.measurement_cost === 1, `ActionSpec ${index} metadata is invalid`);
  });
  await diagnosisValidateFixture(scenario.comparator, "Scenario comparator");
  await diagnosisValidateFixture(scenario.initial_trigger, "Scenario trigger");
  diagnosisAssert(/^[0-9a-f]{64}$/.test(scenario.commitment), "Scenario commitment is invalid");
}

async function diagnosisValidatePayload(payload, allowReveal) {
  diagnosisAssert(payload && typeof payload.type === "string", "Payload discriminator is missing");
  if (payload.type === "scenario") {
    diagnosisExactObject(payload, ["type", "scenario"], "Scenario payload");
    await diagnosisValidateScenario(payload.scenario);
  } else if (payload.type === "state") {
    diagnosisExactObject(payload, ["type", "state", "event"], "State payload");
    diagnosisValidateState(payload.state);
    await diagnosisValidateRecommendationHash(payload.state.recommendation);
    if (payload.event !== null) await diagnosisValidateEvent(payload.event, "State event");
  } else if (payload.type === "ledger") {
    diagnosisExactObject(payload, ["type", "state", "events"], "Ledger payload");
    diagnosisValidateState(payload.state);
    await diagnosisValidateRecommendationHash(payload.state.recommendation);
    diagnosisAssert(Array.isArray(payload.events), "Ledger events must be an array");
    for (let index = 0; index < payload.events.length; index += 1) await diagnosisValidateEvent(payload.events[index], `Ledger event ${index}`);
  } else if (payload.type === "reveal") {
    diagnosisAssert(allowReveal, "Reveal payload arrived without an explicit reveal request");
    diagnosisExactObject(payload, ["type", "reveal"], "Reveal payload");
    diagnosisExactObject(payload.reveal, ["commitment", "commitment_payload"], "Reveal");
  } else if (payload.type === "error") {
    diagnosisExactObject(payload, ["type", "error", "state", "event"], "Error payload");
    diagnosisExactObject(payload.error, ["code", "message"], "Error");
    diagnosisAssert(DIAGNOSIS_ERROR_CODES.has(payload.error.code) && typeof payload.error.message === "string" && payload.error.message.length > 0, "Error code or message is outside the frozen contract");
    if (payload.error.code in DIAGNOSIS_REJECTION_MESSAGES) diagnosisAssert(payload.error.message === DIAGNOSIS_REJECTION_MESSAGES[payload.error.code], "Rejected Error message is not the frozen message");
    if (payload.state !== null) {
      diagnosisValidateState(payload.state);
      await diagnosisValidateRecommendationHash(payload.state.recommendation);
    }
    if (payload.event !== null) await diagnosisValidateEvent(payload.event, "Rejected event");
  } else throw new Error("Unknown diagnosis payload type");
}

function diagnosisValidateEnvelopeStatus(envelope, httpStatus) {
  const payload = envelope.payload;
  if (payload.type === "error") {
    const isRejection = payload.error.code in DIAGNOSIS_REJECTION_MESSAGES;
    diagnosisAssert(envelope.status === (isRejection ? "rejected" : "error"), "Envelope status does not match Error payload");
    if (httpStatus !== null) {
      const expected = isRejection ? 422 : {
        MALFORMED_JSON: 400,
        INVALID_REQUEST_ENVELOPE: 400,
        NOT_FOUND: 404,
        STALE_STATE: 409,
        TERMINAL_STATE: 409,
        IDEMPOTENCY_CONFLICT: 409,
        REVEAL_NOT_AVAILABLE: 409,
        REVEAL_ALREADY_COMPLETED: 409,
        INTERNAL_ERROR: 500,
      }[payload.error.code];
      diagnosisAssert(httpStatus === expected, "HTTP status does not match Error code");
    }
    return;
  }
  const isCreation = payload.type === "state" && payload.event === null && envelope.request_id !== null && envelope.previous_state_version === null && envelope.state_version === 0;
  diagnosisAssert(envelope.status === (isCreation ? "created" : "ok"), "Envelope status does not match success payload");
  if (httpStatus !== null) diagnosisAssert(httpStatus === (isCreation ? 201 : 200), "HTTP status does not match success payload");
}

async function diagnosisVerifyEnvelope(envelope, { allowReveal = false, expectedInputHash = null, httpStatus = null } = {}) {
  diagnosisExactObject(envelope, DIAGNOSIS_ENVELOPE_FIELDS, "Envelope");
  diagnosisAssert(envelope.schema_version === "1.0.0", "Envelope schema version is invalid");
  if (!allowReveal) diagnosisAssert(!diagnosisHasSecretKey(envelope), "Pre-reveal response leaked private fixture data");
  await diagnosisValidatePayload(envelope.payload, allowReveal);
  diagnosisValidateEnvelopeStatus(envelope, httpStatus);
  const expectedHash = await diagnosisSha256Text(diagnosisCanonicalJson(diagnosisWithout(envelope, "response_hash")));
  diagnosisAssert(expectedHash === envelope.response_hash, "Envelope response hash does not verify");
  if (expectedInputHash !== null) diagnosisAssert(envelope.idempotency_input_hash === expectedInputHash, "Envelope idempotency identity does not match the submitted bytes");
  if (envelope.payload.type === "state" || (envelope.payload.type === "error" && envelope.payload.state)) {
    const responseState = envelope.payload.state;
    diagnosisAssert(responseState.state_version === envelope.state_version && responseState.ledger_head_hash === envelope.ledger_hash && responseState.campaign_id === envelope.campaign_id, "Envelope and State identity do not reconcile");
    if (envelope.payload.event) diagnosisAssert(envelope.payload.event.previous_event_hash === envelope.previous_ledger_hash && envelope.payload.event.event_hash === envelope.ledger_hash, "Envelope event chain does not reconcile");
  }
  return envelope;
}

function diagnosisValidateGetIdentity(envelope, path) {
  diagnosisAssert(envelope.request_id === null && envelope.idempotency_input_hash === null, "GET response unexpectedly carries POST idempotency identity");
  if (envelope.payload.type === "error") return;
  if (path === `${DIAGNOSIS_API}/scenario`) {
    diagnosisAssert(envelope.payload.type === "scenario" && envelope.scenario_id === "cv_diagnosis_v1", "Scenario endpoint returned the wrong identity");
    diagnosisAssert(envelope.campaign_id === null && envelope.previous_state_version === null && envelope.state_version === null && envelope.previous_ledger_hash === null && envelope.ledger_hash === null, "Scenario GET campaign/version fields must be null");
    return;
  }
  const escaped = DIAGNOSIS_API.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = path.match(new RegExp(`^${escaped}/campaigns/([^/]+)(/ledger)?$`));
  diagnosisAssert(match, "GET path is outside the frozen diagnosis endpoint matrix");
  const expectedCampaignId = decodeURIComponent(match[1]);
  const expectedType = match[2] ? "ledger" : "state";
  diagnosisAssert(envelope.payload.type === expectedType, "Campaign GET endpoint returned the wrong payload type");
  const responseState = envelope.payload.state;
  diagnosisAssert(envelope.scenario_id === "cv_diagnosis_v1" && envelope.campaign_id === expectedCampaignId && responseState.campaign_id === expectedCampaignId, "Campaign GET response is bound to another campaign");
  diagnosisAssert(envelope.previous_state_version === envelope.state_version && envelope.state_version === responseState.state_version, "Campaign GET version fields are not non-mutating");
  diagnosisAssert(envelope.previous_ledger_hash === envelope.ledger_hash && envelope.ledger_hash === responseState.ledger_head_hash, "Campaign GET ledger fields are not non-mutating");
}

function diagnosisValidatePreparedIdentity(envelope, prepared, httpStatus) {
  diagnosisAssert(envelope.request_id === prepared.body.request_id && envelope.idempotency_input_hash === prepared.inputHash, "POST response is not bound to the submitted request identity");
  const isCreate = prepared.campaignId === null;
  if (isCreate && httpStatus === 201) {
    const responseState = envelope.payload.state;
    diagnosisAssert(envelope.payload.type === "state" && envelope.campaign_id === responseState.campaign_id && envelope.scenario_id === responseState.scenario_id, "Create response campaign identity is invalid");
    diagnosisAssert(envelope.previous_state_version === null && envelope.previous_ledger_hash === null && envelope.state_version === 0 && responseState.state_version === 0 && envelope.ledger_hash === responseState.ledger_head_hash, "Create response version/ledger nullability is invalid");
    return;
  }
  if (isCreate) {
    diagnosisAssert(envelope.campaign_id === null && envelope.previous_state_version === null && envelope.state_version === null && envelope.previous_ledger_hash === null && envelope.ledger_hash === null, "Rejected create response unexpectedly carries campaign state");
    return;
  }
  diagnosisAssert(envelope.campaign_id === prepared.campaignId && envelope.scenario_id === "cv_diagnosis_v1", "POST response is bound to another campaign");
  const event = envelope.payload.event ?? null;
  if (event !== null) {
    diagnosisAssert([200, 422].includes(httpStatus), "Only charged 200/422 responses may append an event");
    diagnosisAssert(envelope.previous_state_version === prepared.baseStateVersion && envelope.previous_ledger_hash === prepared.baseLedgerHash, "Charged POST response does not start from the submitted State");
    diagnosisAssert(envelope.state_version === prepared.baseStateVersion + 1 && event.state_version_before === prepared.baseStateVersion && event.state_version_after === envelope.state_version, "Charged POST version bracket is invalid");
    diagnosisAssert(event.previous_event_hash === prepared.baseLedgerHash && event.event_hash === envelope.ledger_hash, "Charged POST ledger bracket is invalid");
    return;
  }
  diagnosisAssert(envelope.previous_state_version === envelope.state_version && envelope.previous_ledger_hash === envelope.ledger_hash, "Non-mutating POST response changed version or ledger identity");
  if (httpStatus === 200) diagnosisAssert(envelope.state_version === prepared.baseStateVersion && envelope.ledger_hash === prepared.baseLedgerHash, "Successful non-mutating POST response is not bound to the submitted State");
}

function diagnosisRequestId() {
  return window.crypto.randomUUID();
}

async function diagnosisFetchGet(path, { allowReveal = false } = {}) {
  const response = await fetch(path, { cache: "no-store", headers: { Accept: "application/json" } });
  const envelope = await diagnosisVerifyEnvelope(await response.json(), { allowReveal, httpStatus: response.status });
  diagnosisValidateGetIdentity(envelope, path);
  if (!response.ok) throw new Error(envelope.payload.error?.message || `HTTP ${response.status}`);
  return envelope;
}

async function diagnosisPreparePost(path, body, campaignId) {
  const rawBody = JSON.stringify(body);
  const requestBodyHash = await diagnosisSha256Text(rawBody);
  const input = { method: "POST", canonical_path: path, campaign_id: campaignId, request_id: body.request_id, request_body_hash: requestBodyHash };
  return {
    path,
    rawBody,
    body,
    campaignId,
    baseStateVersion: body.expected_state_version ?? null,
    baseLedgerHash: campaignId ? diagnosis.campaign?.ledger_head_hash ?? null : null,
    inputHash: await diagnosisSha256Text(diagnosisCanonicalJson(input)),
  };
}

async function diagnosisSendPrepared(prepared, { allowReveal = false } = {}) {
  const response = await fetch(prepared.path, { method: "POST", cache: "no-store", headers: { Accept: "application/json", "Content-Type": "application/json" }, body: prepared.rawBody });
  const envelope = await diagnosisVerifyEnvelope(await response.json(), { allowReveal, expectedInputHash: prepared.inputHash, httpStatus: response.status });
  diagnosisValidatePreparedIdentity(envelope, prepared, response.status);
  return { response, envelope };
}

function diagnosisActionLabel(recommendation) {
  if (!recommendation || !diagnosis.scenario) return "—";
  const controls = diagnosisCanonicalJson(recommendation.controls);
  return diagnosis.scenario.actions.find((action) => action.operation === recommendation.operation && diagnosisCanonicalJson(action.controls) === controls)?.display_label || recommendation.operation;
}

function diagnosisPercent(value) {
  return `${(value * 100).toFixed(1)}%`;
}

function diagnosisPotential(value) {
  return `${Number(value).toFixed(3)} V`;
}

function diagnosisCurrent(value) {
  return `${Number(value).toExponential(3)} A`;
}

function renderDiagnosisBeliefs(campaignState) {
  const container = byId("diagnosis-beliefs");
  container.replaceChildren();
  diagnosis.scenario.hypotheses.forEach((hypothesis, index) => {
    const row = document.createElement("div");
    row.className = "diagnosis-belief-row";
    const label = appendText(row, "span", hypothesis.label);
    const track = appendText(row, "span", "", "diagnosis-belief-track");
    const fill = appendText(track, "span", "", "diagnosis-belief-fill");
    fill.style.width = diagnosisPercent(campaignState.beliefs[index]);
    const value = appendText(row, "span", diagnosisPercent(campaignState.beliefs[index]), "diagnosis-belief-value");
    label.id = `diagnosis-belief-label-${index}`;
    value.setAttribute("aria-labelledby", label.id);
    container.appendChild(row);
  });
}

function diagnosisCurvePath(curve, frame) {
  return curve.potential_v.map((potential, index) => `${index ? "L" : "M"}${frame.x(potential).toFixed(2)},${frame.y(curve.current_a[index]).toFixed(2)}`).join(" ");
}

function renderDiagnosisCurveTable(curves) {
  const container = byId("diagnosis-curve-table");
  container.replaceChildren();
  const table = document.createElement("table");
  const caption = appendText(table, "caption", "Complete verified synthetic CV points");
  caption.className = "sr-only";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  ["Curve", "Point", "Sweep", "Potential / V", "Current / A"].forEach((value) => appendText(headRow, "th", value));
  head.appendChild(headRow);
  const body = document.createElement("tbody");
  curves.forEach(({ label, curve }) => curve.potential_v.forEach((potential, index) => {
    const row = document.createElement("tr");
    [label, index + 1, curve.sweep_direction[index], potential, curve.current_a[index]].forEach((value) => appendText(row, "td", value));
    body.appendChild(row);
  }));
  table.append(head, body);
  container.appendChild(table);
}

function renderDiagnosisChart() {
  const svg = byId("diagnosis-chart");
  svg.replaceChildren();
  const curves = diagnosis.scenario ? [
    { label: "Frozen healthy/control comparator", curve: diagnosis.scenario.comparator.curve, className: "diagnosis-curve comparator" },
    { label: "Initial abnormal CV", curve: diagnosis.scenario.initial_trigger.curve, className: "diagnosis-curve trigger" },
    ...(diagnosis.latestCurve ? [{ label: "Latest valid CV", curve: diagnosis.latestCurve, className: "diagnosis-curve latest" }] : []),
  ] : [];
  const title = svgElement("title", { id: "diagnosis-chart-title" });
  title.textContent = "Synthetic cyclic voltammogram comparison";
  const desc = svgElement("desc", { id: "diagnosis-chart-desc" });
  if (!curves.length) {
    desc.textContent = "Verified full synthetic CV arrays are unavailable; no curve is drawn.";
    svg.append(title, desc);
    const empty = svgElement("text", { class: "chart-empty-message", x: 380, y: 205, "text-anchor": "middle" });
    empty.textContent = "Verified full synthetic CV arrays are unavailable";
    svg.appendChild(empty);
    return;
  }
  desc.textContent = `${curves.length} verified synthetic full curves, each with 122 points, plotted as current in amperes against potential versus synthetic SHE.`;
  svg.append(title, desc);
  const maximum = Math.max(...curves.flatMap(({ curve }) => curve.current_a.map(Math.abs)), 1e-9);
  const frame = drawChartFrame(svg, { xMin: .65, xMax: .95, yMin: -maximum * 1.12, yMax: maximum * 1.12, xScale: linearScale, xTicks: [.65, .70, .75, .80, .85, .90, .95], yTicks: [-maximum, 0, maximum], xFormat: (value) => value.toFixed(2), yFormat: (value) => value.toExponential(1), xLabel: "Potential vs synthetic SHE / V", yLabel: "Current / A" });
  curves.forEach(({ label, curve, className }, index) => {
    svg.appendChild(svgElement("path", { d: diagnosisCurvePath(curve, frame), class: className }));
    const legend = svgElement("text", { class: `diagnosis-legend legend-${index}`, x: frame.left + 8, y: frame.top + 18 + index * 20 });
    legend.textContent = label;
    svg.appendChild(legend);
  });
  renderDiagnosisCurveTable(curves);
}

function renderDiagnosisResult(event) {
  const copy = byId("diagnosis-result-copy");
  const delta = byId("diagnosis-belief-delta");
  delta.replaceChildren();
  if (!event) {
    copy.textContent = "Run the recommended experiment to reveal the next saved observation.";
    return;
  }
  if (event.status === "success" && event.observation?.kind === "cv") {
    const peak = event.observation.peak;
    copy.textContent = `VALID SYNTHETIC RESULT · ΔEp ${diagnosisPotential(peak.delta_Ep_v)} · midpoint ${diagnosisPotential(peak.midpoint_v)} · |ipa| ${diagnosisCurrent(Math.abs(peak.ipa_a))}`;
  } else if (event.status === "success" && event.observation?.kind === "scalar") {
    copy.textContent = `VALID SYNTHETIC RESULT · ${event.observation.feature_name} = ${event.observation.value} ${event.observation.unit}`;
  } else if (event.status === "rejected") {
    copy.textContent = `${event.rejection_message} Request rejected · attempt charged · no experiment executed · working beliefs unchanged.`;
  } else {
    copy.textContent = event.failure_message || "Operation failed. No replacement value was created.";
  }
  diagnosis.scenario.hypotheses.forEach((hypothesis, index) => appendText(delta, "p", `${hypothesis.label}: ${diagnosisPercent(event.beliefs_before[index])} → ${diagnosisPercent(event.beliefs_after[index])}`));
}

function renderDiagnosisTimeline() {
  const list = byId("diagnosis-timeline");
  list.replaceChildren();
  if (!diagnosis.events.length) {
    appendText(list, "li", "No experiments run yet.");
    return;
  }
  diagnosis.events.forEach((event, index) => {
    const item = document.createElement("li");
    const heading = event.event_type === "action" ? `${index + 1} · ${humanize(event.operation || "rejected request")}` : `${index + 1} · Stop check`;
    appendText(item, "b", heading);
    const reason = diagnosis.eventReasons?.[event.event_id];
    if (reason) appendText(item, "span", `Recommended because: ${reason}`);
    const result = event.status === "success" ? "valid result · working beliefs updated" : event.status === "rejected" ? `${event.rejection_message} · beliefs unchanged` : `${event.failure_message} · beliefs unchanged`;
    appendText(item, "span", `${result} · cost ${event.attempt_cost} attempt / ${event.measurement_cost} measurement`);
    list.appendChild(item);
  });
}

function renderDiagnosisAudit() {
  byId("diagnosis-audit").textContent = diagnosis.campaign ? JSON.stringify({ scenario_id: diagnosis.scenario.scenario_id, scenario_version: diagnosis.scenario.scenario_version, commitment: diagnosis.scenario.commitment, state: diagnosis.campaign, events: diagnosis.events }, null, 2) : "No verified campaign state yet.";
}

function renderDiagnosis() {
  if (!diagnosis.scenario || !diagnosis.campaign) return;
  const campaignState = diagnosis.campaign;
  const comparator = diagnosis.scenario.comparator.peak;
  const trigger = diagnosis.scenario.initial_trigger.peak;
  byId("diagnosis-comparator-summary").textContent = `Frozen healthy/control ΔEp · ${diagnosisPotential(comparator.delta_Ep_v)} → initial abnormal ΔEp · ${diagnosisPotential(trigger.delta_Ep_v)}`;
  byId("diagnosis-measurement-budget").textContent = `Budget · ${campaignState.budget.measurement_limit - campaignState.budget.measurement_used}/${campaignState.budget.measurement_limit} operations left`;
  byId("diagnosis-attempt-budget").textContent = `Attempts · ${campaignState.budget.attempt_used}/${campaignState.budget.attempt_limit}`;
  renderDiagnosisBeliefs(campaignState);
  const recommendation = campaignState.recommendation;
  byId("diagnosis-recommendation").textContent = recommendation ? diagnosisActionLabel(recommendation) : "No further experiment";
  byId("diagnosis-reason").textContent = recommendation ? recommendation.reason_text : DIAGNOSIS_STOP_COPY[campaignState.stop.reason] || "Diagnosis loop stopped.";
  byId("diagnosis-cost").textContent = recommendation ? `${recommendation.measurement_cost} operation · ${recommendation.attempt_cost} attempt` : "—";
  const run = byId("diagnosis-run");
  run.disabled = diagnosis.busy || !recommendation || campaignState.stop.terminal;
  run.textContent = campaignState.stop.terminal ? "Diagnosis loop complete" : diagnosis.busy ? "Running saved experiment…" : "Run recommended experiment";
  byId("diagnosis-reveal").disabled = !campaignState.stop.terminal || diagnosis.busy || diagnosis.revealed;
  byId("diagnosis-reveal-help").textContent = campaignState.stop.terminal ? "Synthetic truth for this committed replay—not experimental truth." : "Truth remains unavailable until the diagnosis loop reaches a terminal state.";
  byId("diagnosis-status").textContent = campaignState.stop.terminal ? DIAGNOSIS_STOP_COPY[campaignState.stop.reason] : recommendation ? "Recommendation ready." : "No verified recommendation is available.";
  renderDiagnosisChart();
  renderDiagnosisTimeline();
  renderDiagnosisAudit();
}

function diagnosisShowError(message) {
  const error = byId("diagnosis-error");
  error.textContent = message;
  error.hidden = false;
  error.focus();
}

function diagnosisClearError() {
  byId("diagnosis-error").hidden = true;
  byId("diagnosis-error").textContent = "";
}

async function diagnosisFetchLedger(campaignId) {
  const envelope = await diagnosisFetchGet(`${DIAGNOSIS_API}/campaigns/${campaignId}/ledger`);
  diagnosisAssert(envelope.payload.type === "ledger", "Ledger endpoint returned the wrong payload");
  await diagnosisReconcileLedger(envelope.payload.state, envelope.payload.events, diagnosis.scenario.prior);
  return { state: envelope.payload.state, events: envelope.payload.events };
}

function diagnosisLatestCurveFromEvents(events) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const observation = events[index].observation;
    if (events[index].status === "success" && observation?.kind === "cv") return observation.curve;
  }
  return null;
}

async function diagnosisApplyResponse(envelope, prepared) {
  diagnosisAssert(["state", "error"].includes(envelope.payload.type), "Action returned the wrong payload type");
  const responseState = envelope.payload.state;
  diagnosisAssert(responseState, "Action response omitted campaign state");
  diagnosisAssert(envelope.previous_state_version === prepared.baseStateVersion && envelope.previous_ledger_hash === prepared.baseLedgerHash, "Action response is stale against the submitted verified state");
  const event = envelope.payload.event;
  diagnosisReconcileTransition(diagnosis.campaign, responseState, event);
  diagnosisAssert(event.request_id === prepared.body.request_id && event.idempotency_input_hash === prepared.inputHash, "Event request identity does not match the submitted bytes");
  const verified = await diagnosisFetchLedger(responseState.campaign_id);
  diagnosisAssert(diagnosisSame(verified.state, responseState), "Action response State does not match the verified ledger snapshot");
  const nextReasons = { ...(diagnosis.eventReasons || {}) };
  nextReasons[event.event_id] = diagnosis.pending?.recommendation?.reason_text || null;
  const nextLatestCurve = diagnosisLatestCurveFromEvents(verified.events);
  diagnosis.campaign = verified.state;
  diagnosis.events = verified.events;
  diagnosis.eventReasons = nextReasons;
  diagnosis.latestCurve = nextLatestCurve;
  renderDiagnosisResult(event);
}

async function diagnosisReconcilePending() {
  if (!diagnosis.pending || !diagnosis.campaign) return;
  try {
    const current = await diagnosisFetchGet(`${DIAGNOSIS_API}/campaigns/${diagnosis.campaign.campaign_id}`);
    diagnosisAssert(current.payload.type === "state", "Campaign reconciliation returned the wrong payload");
    const verified = await diagnosisFetchLedger(current.payload.state.campaign_id);
    diagnosisAssert(diagnosisSame(verified.state, current.payload.state), "Campaign State does not match the verified ledger snapshot");
    const recorded = verified.events.some((event) => event.request_id === diagnosis.pending.body.request_id && event.idempotency_input_hash === diagnosis.pending.inputHash);
    if (recorded) {
      const recovered = await diagnosisSendPrepared(diagnosis.pending);
      await diagnosisApplyResponse(recovered.envelope, diagnosis.pending);
      diagnosis.pending = null;
      byId("diagnosis-retry").hidden = true;
      diagnosisClearError();
    } else {
      diagnosis.campaign = verified.state;
      diagnosis.events = verified.events;
      diagnosis.latestCurve = diagnosisLatestCurveFromEvents(verified.events);
      byId("diagnosis-retry").hidden = false;
      diagnosisShowError("The request was not recorded. Retry uses the identical request ID and bytes.");
    }
  } catch (error) {
    byId("diagnosis-retry").hidden = false;
    diagnosisShowError(`Connection lost after submission. Campaign reconciliation did not complete: ${error.message}`);
  }
}

async function diagnosisRunPrepared(prepared) {
  const epoch = diagnosis.epoch;
  diagnosis.busy = true;
  diagnosis.pending = prepared;
  diagnosisClearError();
  renderDiagnosis();
  try {
    const { response, envelope } = await diagnosisSendPrepared(prepared);
    if (epoch !== diagnosis.epoch) return;
    if (![200, 422].includes(response.status)) throw new Error(envelope.payload.error?.message || `HTTP ${response.status}`);
    await diagnosisApplyResponse(envelope, prepared);
    diagnosis.pending = null;
    byId("diagnosis-retry").hidden = true;
    announce(response.status === 422 ? "Request rejected. Attempt charged; beliefs unchanged." : "Synthetic experiment complete. Verified result rendered.");
  } catch (error) {
    if (epoch === diagnosis.epoch) await diagnosisReconcilePending();
  } finally {
    if (epoch === diagnosis.epoch) {
      diagnosis.busy = false;
      renderDiagnosis();
    }
  }
}

async function runDiagnosisRecommendation() {
  if (diagnosis.busy || !diagnosis.campaign?.recommendation) return;
  const recommendation = diagnosis.campaign.recommendation;
  const body = { request_id: diagnosisRequestId(), expected_state_version: diagnosis.campaign.state_version, recommendation_id: recommendation.recommendation_id, action_input_hash: recommendation.action_input_hash, operation: recommendation.operation, controls: recommendation.controls };
  const path = `${DIAGNOSIS_API}/campaigns/${diagnosis.campaign.campaign_id}/actions`;
  const prepared = await diagnosisPreparePost(path, body, diagnosis.campaign.campaign_id);
  prepared.recommendation = recommendation;
  diagnosis.pending = prepared;
  await diagnosisRunPrepared(prepared);
}

async function retryDiagnosisRequest() {
  if (!diagnosis.pending || diagnosis.busy) return;
  await diagnosisRunPrepared(diagnosis.pending);
}

async function revealDiagnosisTruth() {
  if (diagnosis.busy || diagnosis.revealed || !diagnosis.campaign?.stop.terminal) return;
  const body = { request_id: diagnosisRequestId(), expected_state_version: diagnosis.campaign.state_version };
  const path = `${DIAGNOSIS_API}/campaigns/${diagnosis.campaign.campaign_id}/reveal`;
  const prepared = await diagnosisPreparePost(path, body, diagnosis.campaign.campaign_id);
  diagnosis.busy = true;
  renderDiagnosis();
  try {
    const { response, envelope } = await diagnosisSendPrepared(prepared, { allowReveal: true });
    diagnosisAssert(response.ok && envelope.payload.type === "reveal", "Reveal endpoint did not return verified truth");
    const reveal = envelope.payload.reveal;
    const payload = reveal.commitment_payload;
    diagnosisExactObject(payload, ["scenario_id", "scenario_version", "hidden_truth", "seed_bundle", "reveal_nonce"], "CommitmentPayload");
    diagnosisAssert(payload.scenario_id === diagnosis.scenario.scenario_id && payload.scenario_version === diagnosis.scenario.scenario_version && /^[A-Za-z0-9_-]{43}$/.test(payload.reveal_nonce), "Reveal payload identity or nonce is invalid");
    diagnosisAssert(reveal.commitment === diagnosis.scenario.commitment && await diagnosisSha256Text(diagnosisCanonicalJson(payload)) === diagnosis.scenario.commitment, "Reveal does not open the original Scenario commitment");
    diagnosis.revealed = true;
    const truth = byId("diagnosis-truth");
    truth.textContent = JSON.stringify(reveal, null, 2);
    truth.hidden = false;
    truth.focus();
    announce("Synthetic benchmark truth revealed. It is not experimental truth.");
  } catch (error) {
    diagnosisShowError(`Synthetic truth was not shown: ${error.message}`);
  } finally {
    diagnosis.busy = false;
    renderDiagnosis();
  }
}

async function loadDiagnosis() {
  try {
    diagnosis.epoch += 1;
    diagnosisClearError();
    const scenarioEnvelope = await diagnosisFetchGet(`${DIAGNOSIS_API}/scenario`);
    diagnosisAssert(scenarioEnvelope.payload.type === "scenario", "Scenario endpoint returned the wrong payload");
    diagnosis.scenario = scenarioEnvelope.payload.scenario;
    const body = { request_id: diagnosisRequestId(), scenario_id: diagnosis.scenario.scenario_id, scenario_version: diagnosis.scenario.scenario_version };
    const prepared = await diagnosisPreparePost(`${DIAGNOSIS_API}/campaigns`, body, null);
    const { response, envelope } = await diagnosisSendPrepared(prepared);
    diagnosisAssert(response.status === 201 && envelope.payload.type === "state" && envelope.payload.event === null, "Campaign creation returned the wrong response");
    await diagnosisReconcileLedger(envelope.payload.state, [], diagnosis.scenario.prior);
    diagnosis.campaign = envelope.payload.state;
    diagnosis.latestCurve = null;
    diagnosis.events = [];
    renderDiagnosisResult(null);
    renderDiagnosis();
  } catch (error) {
    byId("diagnosis-status").textContent = "Diagnosis scenario unavailable. No synthetic fallback was generated.";
    diagnosisShowError(`The diagnosis experience could not be verified: ${error.message}`);
  }
}

function configureDiagnosis() {
  byId("diagnosis-run").addEventListener("click", runDiagnosisRecommendation);
  byId("diagnosis-retry").addEventListener("click", retryDiagnosisRequest);
  byId("diagnosis-reveal").addEventListener("click", revealDiagnosisTruth);
}

function renderRealLoadError(error) {
  state.realReady = false;
  byId("real-workbench").classList.add("load-failed");
  byId("real-scene-summary").textContent = `Published reference unavailable: ${error.message}. No substitute curve is drawn.`;
  ["lab-prev", "lab-play", "lab-next", "lab-reset", "lab-scrubber"].forEach((id) => { byId(id).disabled = true; });
  renderDetailedRealCurve();
}

function renderSyntheticLoadError(error) {
  state.syntheticReady = false;
  byId("synthetic-benchmark").classList.add("load-failed");
  byId("strategy-text-summary").textContent = `Verified synthetic artifact bundle unavailable: ${error.message}. No plausible replacement events are shown.`;
  ["strategy-prev", "strategy-play", "strategy-next", "strategy-reset", "strategy-scrubber"].forEach((id) => { byId(id).disabled = true; });
  const runState = byId("run-state");
  runState.textContent = "LOAD ERROR";
  runState.dataset.state = "error";
}

async function loadArtifacts() {
  const status = byId("load-status");
  const [realResult, syntheticResult] = await Promise.allSettled([
    fetchJson(ARTIFACTS.realCV),
    Promise.all([
      fetchJson(ARTIFACTS.manifest),
      fetchJson(ARTIFACTS.summary),
      ...PLANNERS.map((planner) => fetchJson(ARTIFACTS[planner])),
    ]),
  ]);
  const messages = [];

  if (realResult.status === "fulfilled") {
    try {
      if (realResult.value?.provenance !== "published_processed_experimental_data") {
        throw new Error("real CV reference is missing experimental-data provenance");
      }
      state.realCV = realResult.value;
      state.realReady = true;
      renderRealSampleControls();
      state.selectedSampleId = state.realCV.samples[0].id;
      state.displayedSampleId = state.selectedSampleId;
      resetLab();
      messages.push("Published CV reference loaded and provenance verified.");
    } catch (error) {
      renderRealLoadError(error);
      messages.push(`Published CV unavailable: ${error.message}`);
    }
  } else {
    renderRealLoadError(realResult.reason);
    messages.push(`Published CV unavailable: ${realResult.reason.message}`);
  }

  if (syntheticResult.status === "fulfilled") {
    try {
      const [manifest, summary, ...ledgers] = syntheticResult.value;
      assertSimulated("manifest.json", manifest);
      assertSimulated("summary.json", summary);
      ledgers.forEach((ledger, index) => assertSimulated(`${PLANNERS[index]} ledger`, ledger));
      state.manifest = manifest;
      state.summary = summary;
      state.ledgers = Object.fromEntries(PLANNERS.map((planner, index) => [planner, ledgers[index]]));
      state.complete = PLANNERS.every((planner) => ledgerCompletion(planner).complete);
      state.reveal = extractReveal();
      state.syntheticReady = true;
      renderIdentity();
      renderComparison();
      renderStrategyStep();
      configureReveal();
      messages.push(state.complete ? "Verified synthetic replays loaded and complete." : "Synthetic artifacts loaded but at least one campaign is incomplete.");
    } catch (error) {
      renderSyntheticLoadError(error);
      messages.push(`Synthetic replay unavailable: ${error.message}`);
    }
  } else {
    renderSyntheticLoadError(syntheticResult.reason);
    messages.push(`Synthetic replay unavailable: ${syntheticResult.reason.message}`);
  }

  status.textContent = messages.join(" ");
  if (!state.realReady || !state.syntheticReady) {
    status.classList.add("error");
  } else {
    status.classList.add("ready");
  }
}

function configureStaticControls() {
  configureMotion();
  configureRealControls();
  configurePlannerTabs();
  configureStrategyControls();
  byId("reveal-button").addEventListener("click", revealTruth);
}

if (globalThis.__DIAGNOSIS_TEST_HOOKS__) {
  Object.assign(globalThis.__DIAGNOSIS_TEST_HOOKS__, {
    reconcileLedger: diagnosisReconcileLedger,
    reconcileTransition: diagnosisReconcileTransition,
    validateEvent: diagnosisValidateEvent,
    validateEnvelopeStatus: diagnosisValidateEnvelopeStatus,
    validateGetIdentity: diagnosisValidateGetIdentity,
    validatePreparedIdentity: diagnosisValidatePreparedIdentity,
  });
}

document.addEventListener("DOMContentLoaded", () => {
  configureDiagnosis();
  configureStaticControls();
  loadDiagnosis();
  loadArtifacts();
});
