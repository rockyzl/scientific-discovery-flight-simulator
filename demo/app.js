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

document.addEventListener("DOMContentLoaded", () => {
  configureStaticControls();
  loadArtifacts();
});
